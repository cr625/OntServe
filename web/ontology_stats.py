"""
Helper functions for computing ontology statistics.

Provides the stats of the generic ontology page: counts from the entity rows
or, when an ontology has none, from its TTL, and the axioms of the Axioms tab.
"""

from rdflib import Graph, RDF, RDFS, OWL, BNode
from rdflib.collection import Collection

from web.level_views import GROUNDING_LABELS as _GROUNDING_LABELS, framework_grid


def compute_stats_from_ttl(ttl_content: str) -> dict:
    """Compute ontology statistics directly from TTL content.

    Used as fallback when OntologyEntity records aren't populated.

    Args:
        ttl_content: Raw TTL string

    Returns:
        Dict with entity counts and relationship info
    """
    if not ttl_content:
        return {
            'classes': [],
            'object_properties': [],
            'datatype_properties': [],
            'individuals': [],
            'relationships': {
                'hierarchical': 0,
                'domain': 0,
                'range': 0,
                'total': 0
            },
            'from_ttl': True
        }

    g = Graph()
    try:
        g.parse(data=ttl_content, format='turtle')
    except Exception as e:
        return {
            'error': str(e),
            'classes': [],
            'object_properties': [],
            'datatype_properties': [],
            'individuals': [],
            'relationships': {'hierarchical': 0, 'domain': 0, 'range': 0, 'total': 0},
            'from_ttl': True
        }

    # Count classes
    classes = []
    for s in g.subjects(RDF.type, OWL.Class):
        if isinstance(s, BNode):
            continue  # anonymous class expression (owl:unionOf / owl:Restriction), not a named class
        label = g.value(s, RDFS.label)
        comment = g.value(s, RDFS.comment)
        # D-tuple framework marker (proeth-core:dtupleComponent, matched by local
        # name): lets the Schema tab group the nine framework components ahead of
        # supporting classes on the core ontology page.
        dtuple = None
        for p_, o_ in g.predicate_objects(s):
            if str(p_).rsplit('#', 1)[-1].rsplit('/', 1)[-1] == 'dtupleComponent':
                dtuple = str(o_)
                break
        classes.append({
            'uri': str(s),
            'label': str(label) if label else extract_local_name(str(s)),
            'comment': str(comment) if comment else None,
            'dtuple': dtuple
        })

    # Also check for rdfs:Class
    for s in g.subjects(RDF.type, RDFS.Class):
        if isinstance(s, BNode):
            continue
        if s not in [c['uri'] for c in classes]:
            label = g.value(s, RDFS.label)
            comment = g.value(s, RDFS.comment)
            classes.append({
                'uri': str(s),
                'label': str(label) if label else extract_local_name(str(s)),
                'comment': str(comment) if comment else None
            })

    # Count object properties
    object_properties = []
    for s in g.subjects(RDF.type, OWL.ObjectProperty):
        label = g.value(s, RDFS.label)
        comment = g.value(s, RDFS.comment)
        domain = g.value(s, RDFS.domain)
        range_val = g.value(s, RDFS.range)
        object_properties.append({
            'uri': str(s),
            'label': str(label) if label else extract_local_name(str(s)),
            'comment': str(comment) if comment else None,
            'domain': humanize_domain_range(g, domain),
            'range': humanize_domain_range(g, range_val)
        })

    # Count datatype properties
    datatype_properties = []
    for s in g.subjects(RDF.type, OWL.DatatypeProperty):
        label = g.value(s, RDFS.label)
        comment = g.value(s, RDFS.comment)
        datatype_properties.append({
            'uri': str(s),
            'label': str(label) if label else extract_local_name(str(s)),
            'comment': str(comment) if comment else None
        })

    # Count named individuals
    individuals = []
    for s in g.subjects(RDF.type, OWL.NamedIndividual):
        label = g.value(s, RDFS.label)
        comment = g.value(s, RDFS.comment)
        individuals.append({
            'uri': str(s),
            'label': str(label) if label else extract_local_name(str(s)),
            'comment': str(comment) if comment else None
        })

    # Count relationships
    hierarchical = len(list(g.triples((None, RDFS.subClassOf, None))))
    domain_count = len(list(g.triples((None, RDFS.domain, None))))
    range_count = len(list(g.triples((None, RDFS.range, None))))

    return {
        'classes': classes,
        'object_properties': object_properties,
        'datatype_properties': datatype_properties,
        'individuals': individuals,
        'relationships': {
            'hierarchical': hierarchical,
            'domain': domain_count,
            'range': range_count,
            'total': hierarchical + domain_count + range_count
        },
        'from_ttl': True
    }


def extract_local_name(uri: str) -> str:
    """Extract local name from URI."""
    if '#' in uri:
        return uri.split('#')[-1]
    elif '/' in uri:
        return uri.split('/')[-1]
    return uri


def humanize_domain_range(graph, node, full_uri=False):
    """Readable label for a property's domain or range node.

    Resolves an anonymous owl:unionOf / owl:intersectionOf class expression to a
    readable label (e.g. "Action or Event") instead of the raw blank-node id that
    extract_local_name would otherwise emit. For a named class, returns its full
    URI when full_uri is True (callers that store the URI or build links) or its
    local name otherwise. Returns None for an anonymous node that is neither a
    union nor an intersection -- better hidden than shown as a blank-node id.
    """
    if node is None:
        return None
    if isinstance(node, BNode):
        for prop, sep in ((OWL.unionOf, ' or '), (OWL.intersectionOf, ' and ')):
            collection = graph.value(node, prop)
            if collection is not None:
                try:
                    members = [extract_local_name(str(m))
                               for m in Collection(graph, collection)]
                except Exception:
                    members = []
                if members:
                    return sep.join(members)
        return None
    return str(node) if full_uri else extract_local_name(str(node))


def compute_axioms(ttl_content: str) -> dict:
    """Extract axioms from ontology for the Axioms tab.

    Args:
        ttl_content: Raw TTL string

    Returns:
        Dict with subclass_axioms, property_axioms, etc.
    """
    if not ttl_content:
        return {'subclass': [], 'equivalent': [], 'disjoint': [], 'all_disjoint': [], 'property_constraints': []}

    g = Graph()
    try:
        g.parse(data=ttl_content, format='turtle')
    except Exception:
        return {'subclass': [], 'equivalent': [], 'disjoint': [], 'all_disjoint': [], 'property_constraints': []}

    # SubClassOf axioms
    subclass_axioms = []
    for s, p, o in g.triples((None, RDFS.subClassOf, None)):
        # Skip blank nodes
        # str(BNode) is the bare id (no '_:'), so an anonymous endpoint (e.g. a
        # class equivalentTo/subClassOf an owl:unionOf) must be caught by type.
        if isinstance(s, BNode) or isinstance(o, BNode):
            continue
        obj_local = extract_local_name(str(o))
        subclass_axioms.append({
            'subject': extract_local_name(str(s)),
            'subject_uri': str(s),
            # Humanize upper-ontology IDs (BFO_0000015 -> 'BFO process') so the
            # Subsumption table reads as ontology, not opaque identifiers.
            'object': _GROUNDING_LABELS.get(obj_local, obj_local),
            'object_uri': str(o)
        })

    # EquivalentClass axioms
    equivalent_axioms = []
    for s, p, o in g.triples((None, OWL.equivalentClass, None)):
        # str(BNode) is the bare id (no '_:'), so an anonymous endpoint (e.g. a
        # class equivalentTo/subClassOf an owl:unionOf) must be caught by type.
        if isinstance(s, BNode) or isinstance(o, BNode):
            continue
        equivalent_axioms.append({
            'class1': extract_local_name(str(s)),
            'class1_uri': str(s),
            'class2': extract_local_name(str(o)),
            'class2_uri': str(o)
        })

    # DisjointWith axioms, grouped by subject: a class disjoint from many others
    # (e.g. Agent vs the nine components + CodeProvision + Guideline) renders as
    # ONE row listing its partners rather than N scattered pair rows.
    disjoint_by_subject = {}
    for s, p, o in g.triples((None, OWL.disjointWith, None)):
        # str(BNode) is the bare id (no '_:'), so an anonymous endpoint (e.g. a
        # class equivalentTo/subClassOf an owl:unionOf) must be caught by type.
        if isinstance(s, BNode) or isinstance(o, BNode):
            continue
        disjoint_by_subject.setdefault(str(s), set()).add(str(o))
    disjoint_axioms = [
        {
            'class1': extract_local_name(subject),
            'class1_uri': subject,
            'partners': sorted(extract_local_name(u) for u in objects),
            'partner_uris': sorted(objects),
        }
        for subject, objects in sorted(disjoint_by_subject.items())
    ]

    # owl:AllDisjointClasses sets (bnode axiom + owl:members list). Previously
    # invisible: the nine-way component disjointness -- the signature axiom of
    # proethica-core -- never appeared in the Axioms tab, which extracted only
    # pairwise owl:disjointWith.
    all_disjoint_sets = []
    from rdflib.collection import Collection
    for ax in g.subjects(RDF.type, OWL.AllDisjointClasses):
        members_node = g.value(ax, OWL.members)
        if members_node is None:
            continue
        try:
            members = [m for m in Collection(g, members_node) if not isinstance(m, BNode)]
        except Exception:
            continue
        if members:
            all_disjoint_sets.append({
                'members': [extract_local_name(str(m)) for m in members],
                'member_uris': [str(m) for m in members],
            })

    # Property constraints (domain/range)
    property_constraints = []
    for s in g.subjects(RDF.type, OWL.ObjectProperty):
        domain = g.value(s, RDFS.domain)
        range_val = g.value(s, RDFS.range)
        if domain or range_val:
            property_constraints.append({
                'property': extract_local_name(str(s)),
                'property_uri': str(s),
                'domain': humanize_domain_range(g, domain),
                'domain_uri': str(domain) if domain and not isinstance(domain, BNode) else None,
                'range': humanize_domain_range(g, range_val),
                'range_uri': str(range_val) if range_val and not isinstance(range_val, BNode) else None
            })

    return {
        'subclass': sorted(subclass_axioms, key=lambda x: x['subject']),
        'equivalent': equivalent_axioms,
        'disjoint': disjoint_axioms,
        'all_disjoint': all_disjoint_sets,
        'property_constraints': sorted(property_constraints, key=lambda x: x['property'])
    }


def build_stats_context(ontology, entities: dict, relationships: dict, level=None) -> dict:
    """Build the stats context of the generic ontology page.

    Counts come from the OntologyEntity rows, with a TTL fallback when the
    ontology has none. ``level`` (services.proethica_stack.Level) is set when
    the page renders a ProEthica level; the core level adds the D-tuple grid,
    built from the class rows.

    Args:
        ontology: Ontology model instance
        entities: Dict from route handler (classes, properties, individuals)
        relationships: Dict from route handler
        level: the stack level the page renders, or None

    Returns:
        Stats context dict
    """
    has_entities = bool(entities.get('classes') or entities.get('properties') or entities.get('individuals'))
    stats = {'has_entities': has_entities}

    # If no entities but we have TTL content, compute from TTL
    if not has_entities and ontology.current_content:
        ttl_stats = compute_stats_from_ttl(ontology.current_content)
        stats['from_ttl'] = True
        stats['ttl_classes'] = ttl_stats['classes']
        stats['ttl_object_properties'] = ttl_stats['object_properties']
        stats['ttl_datatype_properties'] = ttl_stats['datatype_properties']
        stats['ttl_individuals'] = ttl_stats['individuals']
        stats['ttl_relationships'] = ttl_stats['relationships']
        stats['class_count'] = len(ttl_stats['classes'])
        stats['property_count'] = len(ttl_stats['object_properties']) + len(ttl_stats['datatype_properties'])
        stats['individual_count'] = len(ttl_stats['individuals'])
    else:
        stats['from_ttl'] = False
        stats['class_count'] = len(entities.get('classes', []))
        stats['property_count'] = len(entities.get('properties', []))
        stats['individual_count'] = len(entities.get('individuals', []))

    # Axioms (subClassOf, equivalentClass, disjointWith, property constraints)
    if ontology.current_content:
        stats['axioms'] = compute_axioms(ontology.current_content)
    else:
        stats['axioms'] = {'subclass': [], 'equivalent': [], 'disjoint': [], 'all_disjoint': [], 'property_constraints': []}

    # Core: the nine components above the schema tabs
    if level is not None and level.view == 'framework':
        stats['framework'] = framework_grid(entities.get('classes', []))
    else:
        stats['framework'] = []

    return stats
