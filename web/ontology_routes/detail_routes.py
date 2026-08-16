"""register_detail_routes."""
import logging
import re
from datetime import datetime, timezone

from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for, current_app
from flask_login import login_required, current_user
from sqlalchemy import select, func
import rdflib

from web.models import db, Ontology, OntologyEntity, OntologyVersion
from web.ontology_stats import build_stats_context
from web.entity_extraction import extract_entities_from_content
from web.ontology_routes.helpers import (
    entity_semantic_links,
    entity_using_cases,
    categorize_entity_properties,
    find_entity_by_fragment,
    uri_ends_with_fragment,
    get_entity_children,
    generate_entity_ttl_display,
    extract_entity_from_ttl,
    class_property_schema,
    class_hierarchy,
    entity_disjoint_classes,
    entity_secondary_parents,
    entity_equivalent_class,
    entity_incoming_edges,
    entity_case_provenance,
)


def register_detail_routes(bp):
    @bp.route('/ontology/<ontology_name>')
    def ontology_detail_or_uri_resolution(ontology_name):
        """
    Unified endpoint for ontology detail view and URI resolution.

    - Browser requests (Accept: text/html) -> Detail page
    - Semantic web clients (Accept: text/turtle, etc.) -> Ontology content
    """
        # Check Accept header to determine response type
        accept_header = request.headers.get('Accept', '')
        user_agent = request.headers.get('User-Agent', '')

        # Determine if this is a semantic web client request
        semantic_formats = [
            'text/turtle', 'application/rdf+xml', 'application/ld+json',
            'application/n-triples', 'text/n3', 'application/rdf+json'
        ]

        is_semantic_request = any(fmt in accept_header for fmt in semantic_formats)
        is_browser = 'Mozilla' in user_agent and 'text/html' in accept_header and not is_semantic_request

        stmt = select(Ontology).where(Ontology.name == ontology_name)
        ontology = db.one_or_404(stmt)

        # Handle semantic web client requests (content negotiation)
        if is_semantic_request or (not is_browser and not 'text/html' in accept_header):
            current_app.logger.info(f"URI resolution request for {ontology_name}: Accept={accept_header}")

            # Check if merged ontology is requested
            include_derived = request.args.get('include_derived', 'false').lower() == 'true'
            include_drafts = request.args.get('include_drafts', 'false').lower() == 'true'

            if include_derived and ontology.has_children:
                try:
                    # Use merger service to get combined ontology
                    merged_content, merge_metadata = current_app.ontology_merger.merge_ontology_with_children(
                        ontology, include_drafts=include_drafts
                    )
                    content = merged_content

                    current_app.logger.info(f"Serving merged ontology {ontology_name} with {len(merge_metadata['merged_children'])} children")
                except Exception as e:
                    current_app.logger.error(f"Failed to merge ontology {ontology_name}: {e}")
                    # Fallback to base ontology only
                    content = ontology.current_content
            else:
                content = ontology.current_content

            if content is None:
                return jsonify({
                    'error': 'No content available for this ontology',
                    'ontology': ontology_name,
                    'uri': ontology.base_uri
                }), 404

            # Determine response format based on Accept header
            if 'application/rdf+xml' in accept_header or 'application/xml' in accept_header:
                try:
                    from rdflib import Graph
                    g = Graph()
                    g.parse(data=content, format='turtle')
                    rdf_xml_content = g.serialize(format='xml')

                    response = current_app.response_class(
                        rdf_xml_content,
                        mimetype='application/rdf+xml',
                        headers={
                            'Content-Disposition': f'inline; filename="{ontology_name}.rdf"',
                            'Link': f'<{ontology.base_uri}>; rel="canonical"',
                            'Access-Control-Allow-Origin': '*'
                        }
                    )
                    current_app.logger.info(f"Served ontology {ontology_name} as RDF/XML")
                    return response
                except Exception as e:
                    current_app.logger.error(f"Error converting to RDF/XML: {e}")

            elif 'application/ld+json' in accept_header or 'application/json' in accept_header:
                try:
                    from rdflib import Graph
                    g = Graph()
                    g.parse(data=content, format='turtle')
                    jsonld_content = g.serialize(format='json-ld')

                    response = current_app.response_class(
                        jsonld_content,
                        mimetype='application/ld+json',
                        headers={
                            'Content-Disposition': f'inline; filename="{ontology_name}.jsonld"',
                            'Link': f'<{ontology.base_uri}>; rel="canonical"',
                            'Access-Control-Allow-Origin': '*'
                        }
                    )
                    current_app.logger.info(f"Served ontology {ontology_name} as JSON-LD")
                    return response
                except Exception as e:
                    current_app.logger.error(f"Error converting to JSON-LD: {e}")

            elif 'application/n-triples' in accept_header:
                try:
                    from rdflib import Graph
                    g = Graph()
                    g.parse(data=content, format='turtle')
                    nt_content = g.serialize(format='nt')

                    response = current_app.response_class(
                        nt_content,
                        mimetype='application/n-triples',
                        headers={
                            'Content-Disposition': f'inline; filename="{ontology_name}.nt"',
                            'Link': f'<{ontology.base_uri}>; rel="canonical"',
                            'Access-Control-Allow-Origin': '*'
                        }
                    )
                    current_app.logger.info(f"Served ontology {ontology_name} as N-Triples")
                    return response
                except Exception as e:
                    current_app.logger.error(f"Error converting to N-Triples: {e}")

            # Default to Turtle format for semantic web clients
            response = current_app.response_class(
                content,
                mimetype='text/turtle',
                headers={
                    'Content-Disposition': f'inline; filename="{ontology_name}.ttl"',
                    'Link': f'<{ontology.base_uri}>; rel="canonical"',
                    'Access-Control-Allow-Origin': '*',
                    'Vary': 'Accept'
                }
            )

            current_app.logger.info(f"Served ontology {ontology_name} as Turtle to semantic web client")
            return response

        # Browser request - show detail page
        current_app.logger.info(f"Browser request for {ontology_name}, showing detail page")

        # Get all entities for this ontology
        stmt = select(OntologyEntity).where(
            OntologyEntity.ontology_id == ontology.id
        )
        all_entities = db.session.execute(stmt).scalars().all()

        # Check if user explicitly requested standard view
        view_mode = request.args.get('view', 'auto')

        # Check if this is a case ontology (use case view by default for cases)
        from web.case_display import is_case_ontology, organize_entities_for_case, get_domain_from_ontology

        if view_mode != 'standard' and is_case_ontology(ontology_name, all_entities):
            # Use case view
            current_app.logger.info(f"Using case view for {ontology_name}")
            domain = get_domain_from_ontology(ontology_name)
            case_data = organize_entities_for_case(all_entities, domain)

            # Obligation-competition view model (defeasibility + R->P->O edges grouped
            # per obligation). Read-only; degrades to has_edges=False when absent.
            from web.case_competition import build_competition_clusters
            competition = build_competition_clusters(ontology.current_content)

            # NSPE citation chain: conclusion -> citesProvision -> provision -> establishes
            # -> concept. Joins the case TTL with the NSPE Code of Ethics ontology.
            from web.case_citations import build_citation_chain, build_conclusions
            nspe_ont = db.session.execute(
                select(Ontology).where(Ontology.name == 'NSPE Code of Ethics')
            ).scalars().first()
            citations = build_citation_chain(
                ontology.current_content,
                nspe_ont.current_content if nspe_ont else None,
            )
            # Synthesized conclusions (the "cited by" chip targets) -- gives the chips
            # an on-page anchor + readable text instead of an opaque IRI.
            conclusions = build_conclusions(ontology.current_content)

            # Single ordered block list shared by the sidebar nav and the body so
            # the two render in identical order (and the redundant YAML conclusions
            # section is dropped in favor of the richer conclusions panel).
            from web.case_display import build_ordered_blocks
            page_blocks = build_ordered_blocks(
                case_data['sections'], competition, citations, conclusions)

            # Back-link to the ProEthica case page (the source of this ontology)
            case_id_match = re.fullmatch(r'proethica-case-(\d+)', ontology.name)
            proethica_case_url = (
                f"{current_app.config.get('PROETHICA_BASE_URL', '').rstrip('/')}/cases/{case_id_match.group(1)}"
                if case_id_match and current_app.config.get('PROETHICA_BASE_URL') else None)

            return render_template('ontology_case.html',
                                 ontology=ontology,
                                 proethica_case_url=proethica_case_url,
                                 case_sections=case_data['sections'],
                                 page_blocks=page_blocks,
                                 stats=case_data['stats'],
                                 competition=competition,
                                 citations=citations,
                                 conclusions=conclusions)

        # Optional case filter: ?case=7 filters classes/individuals by discoveredInCase property
        case_filter = request.args.get('case', type=int)

        if case_filter:
            def matches_case(entity):
                if not entity.properties:
                    return False
                disc = entity.properties.get('discoveredincase') or entity.properties.get('discoveredInCase')
                if disc is None:
                    return False
                if isinstance(disc, list):
                    return str(case_filter) in [str(v) for v in disc]
                return str(disc) == str(case_filter)

            filtered = [e for e in all_entities if matches_case(e) or e.entity_type == 'property']
            all_entities = filtered

        # Standard ontology view - group entities by type
        classes = [e for e in all_entities if e.entity_type == 'class']
        # Label-sorted so the template's per-kind grouping lists alphabetically
        # rather than in DB insertion (extractor-pass) order.
        properties = sorted(
            (e for e in all_entities if e.entity_type == 'property'),
            key=lambda e: (e.label or e.uri or '').lower())
        # SKOS concepts (borrowed vocabulary terms) are listed alongside individuals so
        # they stay browsable; the entity page labels them "Concept", not "Individual".
        individuals = [e for e in all_entities if e.entity_type in ('individual', 'concept')]

        entities = {
            'classes': classes,
            'properties': properties,
            'individuals': individuals
        }

        # Count relationship instances
        stmt = select(func.count()).select_from(OntologyEntity).where(
            OntologyEntity.ontology_id == ontology.id,
            OntologyEntity.entity_type == 'class',
            OntologyEntity.parent_uri.isnot(None)
        )
        hierarchical_count = db.session.execute(stmt).scalar()

        stmt = select(func.count()).select_from(OntologyEntity).where(
            OntologyEntity.ontology_id == ontology.id,
            OntologyEntity.entity_type == 'property',
            OntologyEntity.domain.isnot(None)
        )
        domain_count = db.session.execute(stmt).scalar()

        stmt = select(func.count()).select_from(OntologyEntity).where(
            OntologyEntity.ontology_id == ontology.id,
            OntologyEntity.entity_type == 'property',
            OntologyEntity.range.isnot(None)
        )
        range_count = db.session.execute(stmt).scalar()

        relationships = {
            'hierarchical': hierarchical_count,
            'domain': domain_count,
            'range': range_count
        }
        relationships['total'] = relationships['hierarchical'] + relationships['domain'] + relationships['range']

        # Get versions
        stmt = select(OntologyVersion).where(
            OntologyVersion.ontology_id == ontology.id
        ).order_by(OntologyVersion.created_at.desc())
        versions = db.session.execute(stmt).scalars().all()

        # Build enhanced stats context with display_config support
        stats = build_stats_context(ontology, entities, relationships)

        return render_template('ontology_detail.html',
                             ontology=ontology,
                             entities=entities,
                             relationships=relationships,
                             versions=versions,
                             stats=stats,
                             case_filter=case_filter)


    @bp.route('/ontology/<ontology_name>/content')
    def ontology_content(ontology_name):
        """Return raw TTL content of an ontology."""
        stmt = select(Ontology).where(Ontology.name == ontology_name)
        ontology = db.one_or_404(stmt)
        content = ontology.current_content
        if content is None:
            return "No content available for this ontology", 404
        return content, 200, {'Content-Type': 'text/plain; charset=utf-8'}


    @bp.route('/entity/<ontology_name>/<fragment>')
    def entity_detail(ontology_name, fragment):
        """Entity detail page showing current state of an entity."""
        stmt = select(Ontology).where(Ontology.name == ontology_name)
        ontology = db.session.execute(stmt).scalar_one_or_none()

        entity = find_entity_by_fragment(ontology, fragment) if ontology else None

        # Cross-ontology fallback: entity may be in a related ontology
        # (e.g., classes targeted to proethica-intermediate are in proethica-intermediate-extended).
        # A shared class exists both in the definitional ontology (intermediate / extended,
        # which carries the provenance) and in each case ontology that uses it. Prefer the
        # definitional copy so the page lands on the one holding firstDiscoveredInCase etc.
        if not entity:
            candidates = db.session.execute(
                select(OntologyEntity).where(uri_ends_with_fragment(fragment))
            ).scalars().all()
            if candidates:
                entity = next(
                    (e for e in candidates
                     if e.ontology and not e.ontology.name.startswith('proethica-case-')),
                    candidates[0])
                ontology = entity.ontology
            else:
                from flask import abort
                abort(404)

        children = get_entity_children(ontology, entity)
        ttl_content = generate_entity_ttl_display(entity, ontology)
        prop_groups = categorize_entity_properties(entity)
        semantic_links = entity_semantic_links(entity, ontology)
        using_cases = entity_using_cases(entity)
        class_schema = class_property_schema(entity)
        hierarchy = class_hierarchy(entity)
        disjoint_classes = entity_disjoint_classes(entity, ontology)
        secondary_parents = entity_secondary_parents(entity)
        equivalent_class = entity_equivalent_class(entity, ontology)
        # Incoming edges for INDIVIDUALS only (classes have the class-page
        # Referenced By section; parsing the full version content per request
        # is reserved for the case-individual pages that need it).
        incoming_edges = (entity_incoming_edges(entity, ontology)
                          if entity.entity_type in ('individual', 'concept') else [])
        # Case citations for case-discovered classes (extended store): the
        # discoveredInCase markers resolved to linked, titled case ontologies.
        case_provenance = entity_case_provenance(entity)
        # SHACL node shapes: their sh:property rows are blank nodes (the raw
        # ids used to leak onto the page); render the parsed field contract
        # instead via the same cached parser the class pages use.
        shape_fields = []
        if str(entity.parent_uri or '').endswith('shacl#NodeShape'):
            from web.ontology_routes.helpers import shape_attr_schema
            shape_fields = shape_attr_schema(fragment)

        return render_template('entity_detail.html',
                             ontology=ontology,
                             entity=entity,
                             fragment=fragment,
                             children=children,
                             hierarchy=hierarchy,
                             disjoint_classes=disjoint_classes,
                             secondary_parents=secondary_parents,
                             equivalent_class=equivalent_class,
                             incoming_edges=incoming_edges,
                             case_provenance=case_provenance,
                             shape_fields=shape_fields,
                             ttl_content=ttl_content,
                             prop_groups=prop_groups,
                             semantic_links=semantic_links,
                             using_cases=using_cases,
                             class_schema=class_schema,
                             version_tag=None,
                             version_date=None)


    @bp.route('/entity/<ontology_name>/version/<version_tag>/<fragment>')
    def entity_detail_versioned(ontology_name, version_tag, fragment):
        """Entity detail page showing entity at a specific tagged version."""
        stmt = select(Ontology).where(Ontology.name == ontology_name)
        ontology = db.one_or_404(stmt)

        # Find the tagged version
        version_stmt = select(OntologyVersion).where(
            OntologyVersion.ontology_id == ontology.id,
            OntologyVersion.version_tag == version_tag
        )
        version = db.session.execute(version_stmt).scalar_one_or_none()
        if not version:
            from flask import abort
            abort(404)

        # Parse entity from the version's TTL content
        entity_data = extract_entity_from_ttl(version.content, ontology, fragment)
        if not entity_data:
            from flask import abort
            abort(404)

        version_date = version.created_at.strftime('%Y-%m-%d') if version.created_at else None

        return render_template('entity_detail.html',
                             ontology=ontology,
                             entity=entity_data,
                             fragment=fragment,
                             children=[],
                             ttl_content=entity_data.get('_ttl', ''),
                             version_tag=version_tag,
                             version_date=version_date)
    @bp.route('/ontology/<ontology_name>.<format_ext>')
    def ontology_format_specific(ontology_name, format_ext):
        """
    Format-specific ontology endpoints for explicit format requests.

    Examples:
    - /ontology/w3c-prov-o.ttl -> Turtle
    - /ontology/w3c-prov-o.rdf -> RDF/XML
    - /ontology/w3c-prov-o.jsonld -> JSON-LD
    """
        stmt = select(Ontology).where(Ontology.name == ontology_name)
        ontology = db.one_or_404(stmt)
        content = ontology.current_content

        if content is None:
            return jsonify({
                'error': 'No content available for this ontology',
                'ontology': ontology_name
            }), 404

        # Format mapping
        format_mapping = {
            'ttl': ('turtle', 'text/turtle'),
            'rdf': ('xml', 'application/rdf+xml'),
            'xml': ('xml', 'application/rdf+xml'),
            'jsonld': ('json-ld', 'application/ld+json'),
            'json': ('json-ld', 'application/ld+json'),
            'nt': ('nt', 'application/n-triples'),
            'n3': ('n3', 'text/n3')
        }

        if format_ext not in format_mapping:
            return jsonify({'error': f'Unsupported format: {format_ext}'}), 400

        rdf_format, mime_type = format_mapping[format_ext]

        try:
            from rdflib import Graph
            g = Graph()
            g.parse(data=content, format='turtle')

            if rdf_format == 'turtle':
                output_content = content  # Already in turtle
            else:
                output_content = g.serialize(format=rdf_format)

            response = current_app.response_class(
                output_content,
                mimetype=mime_type,
                headers={
                    'Content-Disposition': f'attachment; filename="{ontology_name}.{format_ext}"',
                    'Link': f'<{ontology.base_uri}>; rel="canonical"',
                    'Access-Control-Allow-Origin': '*'
                }
            )

            current_app.logger.info(f"Served ontology {ontology_name} as {format_ext} format")
            return response

        except Exception as e:
            current_app.logger.error(f"Error converting ontology to {format_ext}: {e}")
            return jsonify({
                'error': f'Error converting to {format_ext} format',
                'details': str(e)
            }), 500
    @bp.route('/ontology/<ontology_name>/version/<version_id>')
    def get_ontology_version(ontology_name, version_id):
        """Get a specific version of an ontology."""
        version = db.get_or_404(OntologyVersion, version_id)

        return jsonify({
            'content': version.content,
            'version': version.version_number,
            'commit_message': version.change_summary,
            'created_at': version.created_at.isoformat() if version.created_at else None
        })


    @bp.route('/ontology/<ontology_name>/settings')
    @login_required
    def ontology_settings(ontology_name):
        """Ontology settings page."""
        if not current_user.can_perform_action('edit'):
            flash('You do not have permission to edit ontology settings', 'error')
            return redirect(url_for('ontology.ontology_detail_or_uri_resolution', ontology_name=ontology_name))

        stmt = select(Ontology).where(Ontology.name == ontology_name)
        ontology = db.one_or_404(stmt)
        from services import ontology_categories as categories
        md = ontology.meta_data or {}
        # Subcategory suggestions: every value already in use, so labels stay consistent
        used_subs = sorted({
            (o.meta_data or {}).get(categories.SUBCATEGORY_KEY)
            for o in db.session.execute(select(Ontology)).scalars()
            if (o.meta_data or {}).get(categories.SUBCATEGORY_KEY)
        })
        return render_template('ontology_settings.html', ontology=ontology,
                               explicit_category=md.get(categories.CATEGORY_KEY),
                               explicit_subcategory=md.get(categories.SUBCATEGORY_KEY),
                               category_options=categories.known_category_keys(),
                               subcategory_options=used_subs)
