"""Justifications for Pellet entailments via the bundled Pellet 2.3.1 CLI.

`owlready2.sync_reasoner_pellet` reports WHAT is entailed but not WHY. The
Pellet jar owlready2 ships also carries the `pellet.Pellet explain` command,
which emits the minimal axiom set(s) supporting a single entailment
(`--instance i,C` / `--subclass C,D`) or the ontology inconsistency
(`--inconsistent`). This module wraps that CLI over the same serialized
merged graph the reasoning run used, so the justification is computed
against exactly the asserted axioms that produced the entailment.

Output lines keep Pellet's own rendering (local names, one axiom per line,
e.g. "citedByAgent domain Resource") -- already human-readable and shown
verbatim in the UI.
"""
from __future__ import annotations

import logging
import os
import re
import subprocess
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_CLI_TIMEOUT_SECONDS = 45


def _pellet_classpath() -> str:
    """Classpath wildcard for owlready2's bundled Pellet jars.

    The JVM expands the trailing `*` itself, so this works with shell=False.
    """
    import owlready2
    return os.path.join(os.path.dirname(owlready2.__file__), "pellet", "*")


def _parse_explain_output(text: str) -> Dict[str, Any]:
    """Parse `pellet explain` stdout into {axiom, explanations}.

    Format observed (Pellet 2.3.1):

        Axiom: BER_Case_67-10 type Resource

        Explanation(s):
        1)   citedByAgent domain Resource
             BER_Case_67-10 citedByAgent Agent_Board_of_Ethical_Review

        2)   ...
    """
    axiom = None
    explanations: List[List[str]] = []
    current: Optional[List[str]] = None
    in_explanations = False

    for raw in text.splitlines():
        line = raw.rstrip()
        if not line.strip():
            continue
        if line.startswith("Axiom:"):
            axiom = line[len("Axiom:"):].strip()
            continue
        if line.strip().startswith("Explanation"):
            in_explanations = True
            continue
        if not in_explanations:
            continue
        numbered = re.match(r"^\s*\d+\)\s*(.*)$", line)
        if numbered:
            current = [numbered.group(1).strip()]
            explanations.append(current)
        elif current is not None:
            current.append(line.strip())

    return {"axiom": axiom, "explanations": explanations}


def _run_explain(cli_args: List[str], nt_path: str) -> Dict[str, Any]:
    cmd = [
        "java", "-cp", _pellet_classpath(), "pellet.Pellet", "explain",
        *cli_args, f"file://{nt_path}",
    ]
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=_CLI_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return {"axiom": None, "explanations": [], "error": "explain-timeout"}
    except OSError as exc:
        return {"axiom": None, "explanations": [],
                "error": f"explain-exec-failed: {exc}"}

    parsed = _parse_explain_output(proc.stdout)
    if proc.returncode != 0 and not parsed["explanations"]:
        stderr_tail = (proc.stderr or "").strip().splitlines()[-1:] or [""]
        parsed["error"] = f"explain-exit-{proc.returncode}: {stderr_tail[0][:200]}"
    return parsed


def explain_instance(nt_path: str, individual: str, type_iri: str) -> Dict[str, Any]:
    """Why is `individual` an instance of `type_iri` in the graph at nt_path?"""
    return _run_explain(["--instance", f"{individual},{type_iri}"], nt_path)


def explain_subclass(nt_path: str, child: str, parent: str) -> Dict[str, Any]:
    """Why is `child` a subclass of `parent` in the graph at nt_path?"""
    return _run_explain(["--subclass", f"{child},{parent}"], nt_path)


def explain_inconsistency(nt_path: str) -> Dict[str, Any]:
    """Which axiom set makes the graph at nt_path inconsistent?"""
    return _run_explain(["--inconsistent"], nt_path)


def explain_entailments(
    nt_path: str,
    inferred_types: List[Dict[str, str]],
    inferred_subclasses: List[Dict[str, str]],
    cap: int = 8,
) -> List[Dict[str, Any]]:
    """Justify up to `cap` inferred statements (types first: on case graphs the
    individual-level entailments are the ones grounded in case data).

    Returns [{kind, subject, object, axiom, explanations}]; entries whose CLI
    call failed carry an `error` field instead of explanations.
    """
    results: List[Dict[str, Any]] = []
    targets = (
        [("instance", e["individual"], e["type"]) for e in inferred_types]
        + [("subclass", e["child"], e["parent"]) for e in inferred_subclasses]
    )[:cap]

    for kind, subject, obj in targets:
        if kind == "instance":
            parsed = explain_instance(nt_path, subject, obj)
        else:
            parsed = explain_subclass(nt_path, subject, obj)
        entry: Dict[str, Any] = {
            "kind": kind, "subject": subject, "object": obj,
            "axiom": parsed.get("axiom"),
            "explanations": parsed.get("explanations", []),
        }
        if parsed.get("error"):
            entry["error"] = parsed["error"]
            logger.warning(
                "pellet explain failed for %s(%s, %s): %s",
                kind, subject, obj, parsed["error"],
            )
        results.append(entry)
    return results
