"""Mine the committed case corpus for overflow-bag terms and rank promotion candidates (human-gated).

The extraction overflow bag stages terms the controlled vocabulary does not yet cover on the single declared
predicate proeth:otherAttribute:
  - bearer attributes as     "<key>: <value>"           (e.g. "yearsAtFirm: 12")
  - relationships as         "rel:<type> -> <target>"   (e.g. "rel:mentors -> Junior Engineer")

This scans every committed case TTL, aggregates each overflow key by the number of DISTINCT cases it appears
in, and prints a human-review report. A key recurring in >= MIN_CASES cases is a promotion candidate: declare
a real proeth: property (object property for a relationship, datatype property for an attribute) with
domain/range and a literature-grounded rdfs:comment; the prompt then RE-DERIVES it on the next build
(_role_relationships_block / _role_schema_block read the ontology), so the next batch emits the promoted
predicate natively and the overflow tail shrinks.

This is the mining surface only -- it does NOT promote. Promotion is human + literature gated by design
(frequency alone does not mint a property, and never a Kong-style defined class). It operationalises
McLaren's extensional definition: a term earns controlled status by recurring across processed cases.

Run:  python tools/promotion_candidates.py [--min-cases K] [--ontologies DIR] [--all]
"""
import argparse
import re
from collections import defaultdict
from pathlib import Path

import rdflib

PROETHICA = rdflib.Namespace('http://proethica.org/ontology/intermediate#')
_OTHER_ATTRIBUTE = PROETHICA['otherAttribute']
_REL_PREFIX = 'rel:'


def _normalise(key: str) -> str:
    """Fold a free-form key to its comparison form: lowercase, separators stripped. So 'years_at_firm',
    'Years At Firm', 'yearsAtFirm' all aggregate as one candidate."""
    return re.sub(r'[ _-]', '', key.strip().lower())


def _scan_case(ttl_path: Path):
    """Yield (kind, normalised_key, raw_key, example_value) for each overflow literal in one case TTL.
    kind is 'relationship' for the 'rel:' prefixed values, else 'attribute'."""
    g = rdflib.Graph()
    g.parse(str(ttl_path), format='turtle')
    for _subj, _pred, obj in g.triples((None, _OTHER_ATTRIBUTE, None)):
        val = str(obj).strip()
        if val.startswith(_REL_PREFIX):
            body = val[len(_REL_PREFIX):].strip()             # "<type> -> <target>"
            rtype = body.split('->', 1)[0].strip()
            if rtype:
                yield 'relationship', _normalise(rtype), rtype, body
        elif ':' in val:
            raw_key, example = val.split(':', 1)
            raw_key = raw_key.strip()
            if raw_key:
                yield 'attribute', _normalise(raw_key), raw_key, example.strip()


def collect(ontologies_dir: Path):
    """Aggregate overflow candidates across the case corpus.
    Returns {kind: {norm_key: {'cases': set, 'labels': Counter-like dict, 'examples': [..]}}}."""
    agg = {'attribute': defaultdict(lambda: {'cases': set(), 'labels': defaultdict(int), 'examples': []}),
           'relationship': defaultdict(lambda: {'cases': set(), 'labels': defaultdict(int), 'examples': []})}
    case_files = sorted(ontologies_dir.glob('proethica-case-*.ttl'))
    for ttl in case_files:
        case_id = ttl.stem
        for kind, norm, raw, example in _scan_case(ttl):
            slot = agg[kind][norm]
            slot['cases'].add(case_id)
            slot['labels'][raw] += 1
            if len(slot['examples']) < 3 and example:
                slot['examples'].append(example)
    return agg, len(case_files)


def _report_section(title, rows, min_cases):
    print(f"\n=== {title} (>= {min_cases} distinct cases = promotion candidate) ===")
    if not rows:
        print("  (none)")
        return
    ranked = sorted(rows.items(), key=lambda kv: (-len(kv[1]['cases']), kv[0]))
    print(f"  {'cases':>5}  {'label':28}  examples")
    for norm, slot in ranked:
        n = len(slot['cases'])
        marker = ' *' if n >= min_cases else '  '
        label = max(slot['labels'], key=slot['labels'].get)        # most common surface form
        examples = '; '.join(slot['examples'][:2])
        print(f"{marker}{n:>5}  {label[:28]:28}  {examples[:60]}")
    n_cand = sum(1 for _n, s in rows.items() if len(s['cases']) >= min_cases)
    print(f"  -> {n_cand} candidate(s) at threshold {min_cases}")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--min-cases', type=int, default=3, help='distinct-case threshold for a candidate (default 3)')
    ap.add_argument('--ontologies', default=str(Path(__file__).parent.parent / 'ontologies'),
                    help='directory of committed case TTLs')
    ap.add_argument('--all', action='store_true', help='list every overflow key, not just candidates')
    args = ap.parse_args()

    agg, n_cases = collect(Path(args.ontologies))
    print(f"Scanned {n_cases} committed case TTL(s) in {args.ontologies}")
    for kind, title in (('relationship', 'RELATIONSHIP overflow (rel:<type>)'),
                        ('attribute', 'ATTRIBUTE overflow (<key>: <value>)')):
        rows = agg[kind] if args.all else {k: v for k, v in agg[kind].items()
                                           if len(v['cases']) >= args.min_cases or args.all}
        _report_section(title, agg[kind] if args.all else rows, args.min_cases)
    print("\nPromote a candidate (*): declare a real proeth: property (object for a relationship, datatype "
          "for an attribute) with domain/range + a literature-grounded rdfs:comment, then reload the "
          "intermediate ontology -- the prompt re-derives it and the next batch emits it natively. "
          "Human + literature gate; frequency alone does not promote.")


if __name__ == '__main__':
    main()
