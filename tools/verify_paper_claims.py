#!/usr/bin/env python3
"""
Verify that the paper's structural claims are honored by the live OntServe
deployment at https://ontserve.ontorealm.net.

The KI2026 paper makes several claims a reviewer can spot-check by
visiting the live site. This script does those checks from the command
line and prints a pass/fail table so any drift between the paper and
the live deployment is visible in CI or ad-hoc.

Usage
-----

    python tools/verify_paper_claims.py
    python tools/verify_paper_claims.py --base-url https://ontserve.ontorealm.net
    python tools/verify_paper_claims.py --json  # machine-readable output

What it checks
--------------

1. The core, intermediate, cases, provenance, and engineering-ethics
   ontologies are each reachable at /ontology/<name>.
2. The three NSPE-tradition code-of-ethics ontologies (ASCE, ASME, IEEE)
   the live site hosts are reachable.
3. The three foundation ontologies (BFO, IAO, Relations Ontology 2015)
   are reachable.
4. A spot-check of NSPE BER Case 72 is reachable at
   /ontology/proethica-case-72 so the Figure 1 example can be inspected
   in the browser.
5. The SPARQL endpoint at /sparql accepts a minimal query and returns
   a well-formed SPARQL JSON result.

Exit codes
----------

0: all checks passed.
1: at least one check failed.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import List, Optional


DEFAULT_BASE_URL = "https://ontserve.ontorealm.net"

# Ontologies the paper enumerates or implies, with their live-site slugs.
# Slugs come from the live homepage listing; some use URL-encoded spaces
# because that is how the Flask route registers them.
EXPECTED_ONTOLOGIES: List[tuple[str, str]] = [
    # Core / intermediate / cases / provenance / domain (paper §4)
    ("proethica-core", "proethica-core"),
    ("proethica-intermediate", "proethica-intermediate"),
    ("proethica-cases", "proethica-cases"),
    ("proethica-provenance", "proethica-provenance"),
    ("engineering-ethics", "engineering-ethics"),
    # Foundation ontologies the paper names as external imports
    ("BFO", "bfo"),
    ("IAO", "iao"),
    ("Relations Ontology", "Relations Ontology 2015"),
    # Three professional codes of ethics (paper §4 count of 11 externals)
    ("ASCE Code of Ethics", "ASCE Code of Ethics"),
    ("ASME Code of Ethics", "ASME Code of Ethics"),
    ("IEEE Code of Ethics", "IEEE Code of Ethics"),
    # Worked example referenced by Figure 1
    ("Case 72 (Figure 1 example)", "proethica-case-72"),
]


@dataclass
class CheckResult:
    name: str
    url: str
    ok: bool
    detail: str = ""


@dataclass
class VerificationReport:
    base_url: str
    checks: List[CheckResult] = field(default_factory=list)

    @property
    def all_ok(self) -> bool:
        return all(c.ok for c in self.checks)

    def to_json(self) -> str:
        return json.dumps(
            {
                "base_url": self.base_url,
                "all_ok": self.all_ok,
                "checks": [
                    {"name": c.name, "url": c.url, "ok": c.ok, "detail": c.detail}
                    for c in self.checks
                ],
            },
            indent=2,
        )


def _head_or_get(url: str, timeout: float = 15.0) -> tuple[int, str]:
    """Issue a GET (some Flask routes don't implement HEAD) and return (status, error).

    Returns (status_code, "") on success; (0, detail) on error.
    """
    try:
        req = urllib.request.Request(url, headers={"Accept": "text/html"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, ""
    except urllib.error.HTTPError as exc:
        return exc.code, f"HTTP {exc.code} {exc.reason}"
    except urllib.error.URLError as exc:
        return 0, f"URL error: {exc.reason}"
    except Exception as exc:  # noqa: BLE001 -- best-effort probe
        return 0, f"{type(exc).__name__}: {exc}"


def _check_ontology(base_url: str, display_name: str, slug: str) -> CheckResult:
    url = f"{base_url.rstrip('/')}/ontology/{urllib.parse.quote(slug)}"
    status, detail = _head_or_get(url)
    ok = status == 200
    return CheckResult(name=display_name, url=url, ok=ok, detail=detail or f"status {status}")


def _check_sparql_endpoint(base_url: str) -> CheckResult:
    """POST a minimal SPARQL query and verify a SPARQL JSON response comes back."""
    url = f"{base_url.rstrip('/')}/sparql"
    query = (
        "PREFIX core: <http://proethica.org/ontology/core#>\n"
        "PREFIX owl: <http://www.w3.org/2002/07/owl#>\n"
        "ASK { core:competesWith a owl:ObjectProperty }"
    )
    body = json.dumps({"query": query}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            raw = resp.read().decode("utf-8")
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError as exc:
                return CheckResult(
                    name="SPARQL endpoint",
                    url=url,
                    ok=False,
                    detail=f"non-JSON response: {exc}",
                )
            # Either a SELECT/ASK JSON result with a 'boolean' or 'results' key
            ok = "boolean" in parsed or "results" in parsed or "head" in parsed
            detail = "accepts SPARQL, returned JSON" if ok else f"unexpected keys: {list(parsed)[:5]}"
            return CheckResult(name="SPARQL endpoint", url=url, ok=ok, detail=detail)
    except urllib.error.HTTPError as exc:
        return CheckResult(
            name="SPARQL endpoint",
            url=url,
            ok=False,
            detail=f"HTTP {exc.code} {exc.reason}",
        )
    except Exception as exc:  # noqa: BLE001
        return CheckResult(
            name="SPARQL endpoint",
            url=url,
            ok=False,
            detail=f"{type(exc).__name__}: {exc}",
        )


def run(base_url: str = DEFAULT_BASE_URL) -> VerificationReport:
    report = VerificationReport(base_url=base_url)
    for display_name, slug in EXPECTED_ONTOLOGIES:
        report.checks.append(_check_ontology(base_url, display_name, slug))
    report.checks.append(_check_sparql_endpoint(base_url))
    return report


def _format_table(report: VerificationReport) -> str:
    width = max((len(c.name) for c in report.checks), default=10)
    lines = [f"OntServe paper-claim verification against {report.base_url}", ""]
    for c in report.checks:
        status = "PASS" if c.ok else "FAIL"
        lines.append(f"  [{status}] {c.name.ljust(width)}  {c.detail}")
    lines.append("")
    passed = sum(1 for c in report.checks if c.ok)
    total = len(report.checks)
    lines.append(f"Result: {passed}/{total} checks passed.")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base-url",
        default=DEFAULT_BASE_URL,
        help=f"Base URL of the OntServe deployment (default: {DEFAULT_BASE_URL})",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit a machine-readable JSON report instead of the text table.",
    )
    args = parser.parse_args()

    report = run(args.base_url)
    if args.json:
        print(report.to_json())
    else:
        print(_format_table(report))
    return 0 if report.all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
