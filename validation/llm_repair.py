#!/usr/bin/env python3
"""
Phase D3: the LLM repair TIERS for the conformance loop (Tier 1 Haiku -> Tier 2 Sonnet
-> one Opus attempt). Plugs into `conformance_loop.repair_loop` via its `llm_repair`
callback; Tier 0 (deterministic, no model) runs first and the LLM tier only sees what
Tier 0 could not fix.

Separation of concerns (so the loop stays domain-general and the model wiring stays out
of OntServe, which has no LLM SDK / key):
  - the REPAIR MECHANISM, the prompt-context assembly, the JSON parse, the tier
    escalation, and the deterministic APPLIER all live here / in conformance_loop;
  - the raw model call is INJECTED by the caller (ProEthica owns the Anthropic client and
    key) as `call_model(model, system, user) -> str`.

The LLM is a PROPOSER only: it chooses ONE core category for a clashing individual. The
code applies that choice deterministically (retype_individual_to_category) and the SYMBOLIC
SHACL+OWL-RL gate (conformance.py) re-validates. The model never judges conformance and
never writes raw triples -- this is the safety property of the evaluator-optimizer design.

Usage (the caller, e.g. ProEthica, injects call_model):
    from llm_repair import make_llm_repair
    from conformance_loop import repair_loop
    repair = make_llm_repair(call_model=my_anthropic_call)
    r = repair_loop(case_ttl, llm_repair=repair)
"""
import json
import re
from typing import Callable, List, Optional, Sequence

from rdflib import Graph, URIRef

from conformance_loop import (
    CORE9, OntologyContext, individual_repair_context, retype_individual_to_category,
)

# Default model ladder: Tier 1 Haiku, Tier 2 Sonnet, then one Opus attempt.
DEFAULT_MODELS = ("claude-haiku-4-5", "claude-sonnet-4-6", "claude-opus-4-8")

# The LLM tier owns only violations that reduce to "pick the single correct core
# category". owl:Nothing (NoOwlNothingShape) has no single-category repair and is left to
# escalate/report; disjoint-core is the repairable case.
_REPAIRABLE_SHAPES = {"DisjointCoreCategoryShape"}

_SYSTEM = (
    "You repair an OWL ontology individual that the reasoner found to reach two or more "
    "mutually disjoint core categories. The nine disjoint categories are: "
    + ", ".join(CORE9) + ". Choose the ONE category the individual actually belongs to, "
    "using its label, its asserted type classes, and the categories implied by the "
    "properties it carries. Respond with ONLY a JSON object: "
    '{"category": "<one of the nine>", "reason": "<short>"}. No prose outside the JSON.'
)


def _parse_category(text: str) -> Optional[str]:
    """Extract a valid core category from the model response (tolerant of prose around
    the JSON). Returns None if no valid category is found."""
    if not text:
        return None
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if m:
        try:
            cat = (json.loads(m.group(0)) or {}).get("category")
            if isinstance(cat, str) and cat.strip() in CORE9:
                return cat.strip()
        except Exception:
            pass
    # Fallback: a bare category token somewhere in the text.
    for c in CORE9:
        if re.search(rf"\b{c}\b", text):
            return c
    return None


def make_llm_repair(
    call_model: Callable[[str, str, str], str],
    models: Sequence[str] = DEFAULT_MODELS,
) -> Callable[[Graph, List, OntologyContext], int]:
    """Build an `llm_repair` callback for repair_loop.

    `call_model(model, system, user) -> str` is the injected raw model call (the caller
    supplies the Anthropic client + key). `models` is the escalation ladder, walked WITHIN a
    single invocation per clashing individual: Tier 1 (Haiku) is tried first, and only if it
    returns no parseable category is Tier 2 (Sonnet) tried, then one Opus attempt. Escalating
    within the call (rather than across loop rounds) is required because repair_loop early-
    stops a round that applies zero repairs; it is also strictly better, since any valid
    category choice collapses a pure disjoint-core clash, so the only reason to escalate is an
    unparseable lower-tier response.
    """
    def llm_repair(case_g: Graph, violations: List, ctx: OntologyContext) -> int:
        # One repair per clashing individual per round (dedupe focus nodes).
        focus_nodes, seen = [], set()
        for v in violations:
            if v.source_shape not in _REPAIRABLE_SHAPES or not v.focus_node:
                continue
            if v.focus_node in seen:
                continue
            seen.add(v.focus_node)
            focus_nodes.append(v.focus_node)

        repaired = 0
        for fn in focus_nodes:
            ind = URIRef(fn)
            context = individual_repair_context(case_g, ind, ctx)
            user = (
                "Individual to repair:\n" + json.dumps(context, indent=2)
                + "\n\nPick the ONE correct core category."
            )
            category = None
            for model in models:  # Tier 1 -> Tier 2 -> Opus, escalate on unparseable only
                try:
                    raw = call_model(model, _SYSTEM, user)
                except Exception:
                    continue
                category = _parse_category(raw)
                if category:
                    break
            if category and retype_individual_to_category(case_g, ind, category, ctx):
                repaired += 1
        return repaired

    return llm_repair
