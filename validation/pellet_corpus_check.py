#!/usr/bin/env python3
"""
Run Pellet validation on all proethica-case-* ontologies.

For each case:
  - Merges core + intermediate + case content (with missing subClassOf added)
  - Runs Pellet
  - Records: consistent, runtime, inferred_type, inferred_subclass, disjointness_violations

Results written to:
  docs-internal/KI2026/pellet_corpus_report.json   (full per-case detail)
  docs-internal/KI2026/pellet_corpus_report.md      (summary for the paper)
"""
import json
import logging
import os
import sys
import time
from collections import Counter
from dataclasses import asdict
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
ONTSERVE_ROOT = SCRIPT_DIR.parent
WEB_DIR = ONTSERVE_ROOT / "web"
sys.path.insert(0, str(ONTSERVE_ROOT))
sys.path.insert(0, str(WEB_DIR))
sys.path.insert(0, str(SCRIPT_DIR))

from config.config_loader import load_ontserve_config
load_ontserve_config()

from flask import Flask
from web.app_config import config as flask_config
from web.models import db, init_db, Ontology, OntologyVersion

from pellet_validate import validate_case_from_content

OUT_DIR = ONTSERVE_ROOT / "docs-internal" / "KI2026"


def main():
    logging.basicConfig(level=logging.WARNING, format="%(message)s")

    app = Flask(__name__)
    app.config.from_object(flask_config[os.environ.get("FLASK_CONFIG", "development")])
    init_db(app)

    results = []
    with app.app_context():
        ontologies = (
            Ontology.query
            .filter(Ontology.name.like("proethica-case-%"))
            .order_by(Ontology.name)
            .all()
        )
        total = len(ontologies)
        print(f"Running Pellet on {total} case ontologies...\n")

        for i, ont in enumerate(ontologies, 1):
            ver = OntologyVersion.query.filter_by(
                ontology_id=ont.id, is_current=True
            ).first()
            if not ver:
                print(f"[{i}/{total}] {ont.name}: SKIP (no current version)")
                continue

            r = validate_case_from_content(ont.name, ver.content)
            results.append(asdict(r))

            status = "OK" if r.consistent else "INCONSISTENT"
            print(
                f"[{i}/{total}] {ont.name}: {status} "
                f"(+{r.inferred_type_assertions}t +{r.inferred_subclass_assertions}s "
                f"{r.runtime_seconds:.1f}s)"
            )

    # Write JSON report
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    json_path = OUT_DIR / "pellet_corpus_report.json"
    with open(json_path, "w") as f:
        json.dump(results, f, indent=2)

    # Compute summary
    n = len(results)
    consistent = sum(1 for r in results if r["consistent"])
    inconsistent = n - consistent
    total_time = sum(r["runtime_seconds"] for r in results)
    mean_time = total_time / n if n else 0
    total_inferred_type = sum(r["inferred_type_assertions"] for r in results)
    total_inferred_sub = sum(r["inferred_subclass_assertions"] for r in results)
    mean_type = total_inferred_type / n if n else 0
    mean_sub = total_inferred_sub / n if n else 0
    total_disjointness = sum(r["disjointness_violations"] for r in results)

    inconsistent_names = [r["ontology_name"] for r in results if not r["consistent"]]

    md = f"""# Pellet Corpus Validation Report

Generated: {time.strftime('%Y-%m-%d %H:%M')}

## Summary

| Metric | Value |
|--------|-------|
| Cases validated | {n} |
| Consistent | {consistent} |
| Inconsistent | {inconsistent} |
| Total runtime | {total_time:.1f}s |
| Mean runtime/case | {mean_time:.2f}s |
| Total inferred type assertions | {total_inferred_type} |
| Mean inferred type assertions/case | {mean_type:.1f} |
| Total inferred subclass assertions | {total_inferred_sub} |
| Mean inferred subclass assertions/case | {mean_sub:.1f} |
| Disjointness violations | {total_disjointness} |
"""
    if inconsistent_names:
        md += "\n## Inconsistent Cases\n\n"
        for name in inconsistent_names:
            r = next(x for x in results if x["ontology_name"] == name)
            md += f"- **{name}**: {r.get('error', 'unknown')}\n"
            if r.get("error_explanation"):
                md += f"  {r['error_explanation'][:200]}\n"

    md_path = OUT_DIR / "pellet_corpus_report.md"
    with open(md_path, "w") as f:
        f.write(md)

    print(f"\n{'='*60}")
    print(f"Consistent: {consistent}/{n}   Inconsistent: {inconsistent}/{n}")
    print(f"Total runtime: {total_time:.1f}s   Mean: {mean_time:.2f}s/case")
    print(f"Inferred type assertions: {total_inferred_type} total, {mean_type:.1f}/case")
    print(f"Inferred subclass assertions: {total_inferred_sub} total, {mean_sub:.1f}/case")
    print(f"\nReports: {json_path}, {md_path}")


if __name__ == "__main__":
    main()
