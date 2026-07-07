"""Citation-DOI consistency guard for the base ontologies.

Invariant: every DOI embedded in an iao:0000119 definition-source string must
appear as a dcterms:source or dcterms:references IRI on the same subject
(https://doi.org/<doi>). The two fields are deliberately redundant: the string
is the human citation, the IRI is the machine identifier. The 2026-06-30 and
2026-07-01 citation audits caught real errors exactly where the two disagreed
(Taddeo and Prem carried the right DOI in the source tier and a wrong one in
the 119 string), so agreement is enforced here as a standing invariant instead
of being left to manual review. Decision record: the 2026-07-06 DOI-policy
question (keep both fields plus this guard, rather than dropping the DOIs).

Structural check (default, offline):
  FAIL on any 119-embedded DOI missing from the subject's dcterms IRIs.
  FAIL on any malformed doi.org IRI in dcterms:source / dcterms:references.

Resolution check (--resolve, hits api.crossref.org):
  For each unique DOI, compare the registered title and year against the
  citation strings that embed it. Advisory (WARN, does not affect the exit
  code): titles legitimately differ in case and punctuation, and issue years
  differ from online-first years (Segun: online 2020, issue 2021).

Usage:
  python validation/citation_doi_guard.py                      # core + intermediate
  python validation/citation_doi_guard.py path/to/file.ttl ...
  python validation/citation_doi_guard.py --resolve
"""

import json
import re
import sys
import urllib.request
from pathlib import Path

import rdflib
from rdflib.namespace import DCTERMS

ONTSERVE_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FILES = [
    ONTSERVE_ROOT / "ontologies" / "proethica-core.ttl",
    ONTSERVE_ROOT / "ontologies" / "proethica-intermediate.ttl",
    ONTSERVE_ROOT / "ontologies" / "engineering-ethics.ttl",
]

IAO119 = rdflib.URIRef("http://purl.obolibrary.org/obo/IAO_0000119")

# DOI embedded in a citation string: "... (doi:10.1007/s43681-023-00258-9)."
# ')' is allowed inside the capture because Elsevier DOIs contain parenthesized
# year segments (10.1016/S0004-3702(03)00135-8); _trim_doi strips the trailing
# punctuation and any unbalanced close-parens from the enclosing "(doi:...)".
STRING_DOI_RE = re.compile(r"doi:\s*(10\.[^\s\"']+)")


def _trim_doi(doi):
    """A captured DOI without trailing sentence punctuation or the unbalanced
    close-paren of an enclosing '(doi:...)' wrapper."""
    doi = doi.rstrip(".,;")
    while doi.endswith(")") and doi.count(")") > doi.count("("):
        doi = doi[:-1].rstrip(".,;")
    return doi
# Registrant-suffix shape a DOI must have.
DOI_SHAPE_RE = re.compile(r"^10\.\d{4,9}/\S+$")
# Citation-string year: "Author (2023)." or "Author et al. (2023)."
STRING_YEAR_RE = re.compile(r"\(((?:19|20)\d\d)\)")


def _iri_doi(value):
    """The bare DOI of a doi.org IRI, or None for a non-DOI IRI."""
    s = str(value)
    for prefix in ("https://doi.org/", "http://doi.org/", "https://dx.doi.org/", "http://dx.doi.org/"):
        if s.startswith(prefix):
            return s[len(prefix):]
    return None


def collect(path):
    """Per-subject citation data for one TTL file: 119 strings, dcterms DOI IRIs."""
    g = rdflib.Graph()
    g.parse(str(path), format="turtle")
    subjects = {}
    for s, o in g.subject_objects(IAO119):
        subjects.setdefault(s, {"strings": [], "iris": set(), "bad_iris": []})["strings"].append(str(o))
    for pred in (DCTERMS.source, DCTERMS.references):
        for s, o in g.subject_objects(pred):
            if not isinstance(o, rdflib.URIRef):
                continue  # literal sources (NSPE code strings) are not DOIs
            doi = _iri_doi(o)
            if doi is None:
                continue  # non-DOI IRI (case IRIs, justia links) is out of scope
            entry = subjects.setdefault(s, {"strings": [], "iris": set(), "bad_iris": []})
            if DOI_SHAPE_RE.match(doi):
                entry["iris"].add(doi)
            else:
                entry["bad_iris"].append(str(o))
    return subjects


def structural_check(files):
    failures = []
    all_pairs = []  # (doi, citation_string) for --resolve
    for path in files:
        for subj, data in collect(path).items():
            local = str(subj).split("#")[-1]
            for bad in data["bad_iris"]:
                failures.append(f"{path.name} :: {local}: malformed doi.org IRI {bad}")
            for text in data["strings"]:
                for doi in STRING_DOI_RE.findall(text):
                    doi = _trim_doi(doi)
                    all_pairs.append((doi, text))
                    if doi not in data["iris"]:
                        failures.append(
                            f"{path.name} :: {local}: iao:0000119 embeds doi:{doi} "
                            f"but no dcterms:source/references IRI on the subject carries it")
    return failures, all_pairs


def _norm(s):
    return re.sub(r"[^a-z0-9 ]", "", s.lower())


def resolve_check(pairs):
    """Advisory Crossref comparison of each unique DOI against its citation strings."""
    warnings = []
    by_doi = {}
    for doi, text in pairs:
        by_doi.setdefault(doi, []).append(text)
    for doi, texts in sorted(by_doi.items()):
        try:
            req = urllib.request.Request(
                f"https://api.crossref.org/works/{doi}",
                headers={"User-Agent": "OntServe citation guard"})
            with urllib.request.urlopen(req, timeout=20) as r:
                work = json.load(r)["message"]
        except Exception as e:
            warnings.append(f"doi:{doi}: Crossref lookup failed ({e})")
            continue
        reg_title = _norm((work.get("title") or [""])[0])
        issued = (work.get("issued", {}).get("date-parts") or [[None]])[0][0]
        for text in texts:
            # The first four significant registered-title words must appear in the string.
            probe = " ".join(reg_title.split()[:4])
            if probe and probe not in _norm(text):
                warnings.append(
                    f"doi:{doi}: registered title starts '{probe}...' "
                    f"but the citation string reads: {text[:100]}")
            m = STRING_YEAR_RE.search(text)
            if m and issued and abs(int(m.group(1)) - int(issued)) > 1:
                warnings.append(
                    f"doi:{doi}: registered year {issued} vs citation year {m.group(1)}: {text[:80]}")
    return warnings


def main(argv):
    resolve = "--resolve" in argv
    paths = [Path(a) for a in argv if not a.startswith("--")]
    files = paths or DEFAULT_FILES
    failures, pairs = structural_check(files)
    print(f"checked {len(files)} file(s), {len(pairs)} embedded DOI reference(s)")
    for f in failures:
        print(f"FAIL {f}")
    if resolve:
        for w in resolve_check(pairs):
            print(f"WARN {w}")
    if failures:
        print(f"{len(failures)} structural failure(s)")
        return 1
    print("structural check PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
