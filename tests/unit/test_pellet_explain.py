"""Unit tests for validation/pellet_explain.py (Pellet CLI justification wrapper)."""

import pytest

from validation import pellet_explain as pe


SAMPLE_INSTANCE_OUTPUT = """\
Axiom: BER_Case_67-10 type Resource

Explanation(s):
1)   citedByAgent domain Resource
     BER_Case_67-10 citedByAgent Agent_Board_of_Ethical_Review

"""

SAMPLE_SUBCLASS_OUTPUT = """\
Axiom: ForensicExpertWitnessEngineerRole subClassOf ProviderClientRole

Explanation(s):
1)   ForensicExpertWitnessEngineerRole subClassOf EngineerRole
     ProviderClientRole equivalentTo Role
                                     and hasClient some Role
     ForensicExpertWitnessEngineerRole subClassOf hasClient some Role
     EngineerRole subClassOf ProfessionalRole
     ProfessionalRole subClassOf Role

2)   ForensicExpertWitnessEngineerRole subClassOf hasClient some Role
     ProviderClientRole equivalentTo Role
                                     and hasClient some Role
     ForensicExpertWitnessEngineerRole subClassOf Role
"""


class TestParseExplainOutput:

    def test_single_explanation(self):
        parsed = pe._parse_explain_output(SAMPLE_INSTANCE_OUTPUT)
        assert parsed["axiom"] == "BER_Case_67-10 type Resource"
        assert len(parsed["explanations"]) == 1
        assert parsed["explanations"][0] == [
            "citedByAgent domain Resource",
            "BER_Case_67-10 citedByAgent Agent_Board_of_Ethical_Review",
        ]

    def test_multiple_explanations_and_continuation_lines(self):
        parsed = pe._parse_explain_output(SAMPLE_SUBCLASS_OUTPUT)
        assert parsed["axiom"].startswith("ForensicExpertWitnessEngineerRole subClassOf")
        assert len(parsed["explanations"]) == 2
        # The wrapped "and hasClient some Role" continuation rejoins its axiom line.
        assert len(parsed["explanations"][0]) == 5
        assert ("ProviderClientRole equivalentTo Role and hasClient some Role"
                in parsed["explanations"][0])
        assert parsed["explanations"][1][0].startswith(
            "ForensicExpertWitnessEngineerRole subClassOf hasClient")

    def test_empty_output(self):
        parsed = pe._parse_explain_output("")
        assert parsed["axiom"] is None
        assert parsed["explanations"] == []


class TestExplainEntailments:

    def test_targets_types_first_and_caps(self, monkeypatch):
        calls = []

        def fake_run(cli_args, nt_path):
            calls.append(cli_args)
            return {"axiom": "x", "explanations": [["a"]]}

        monkeypatch.setattr(pe, "_run_explain", fake_run)
        types = [{"individual": f"http://x#i{n}", "type": "http://x#T"} for n in range(3)]
        subs = [{"child": f"http://x#c{n}", "parent": "http://x#P"} for n in range(3)]
        out = pe.explain_entailments("/tmp/g.nt", types, subs, cap=4)

        assert len(out) == 4
        assert [e["kind"] for e in out] == ["instance"] * 3 + ["subclass"]
        assert calls[0][0] == "--instance"
        assert calls[3][0] == "--subclass"

    def test_cli_error_carried_per_entry(self, monkeypatch):
        monkeypatch.setattr(
            pe, "_run_explain",
            lambda cli_args, nt_path: {"axiom": None, "explanations": [],
                                       "error": "explain-timeout"})
        out = pe.explain_entailments(
            "/tmp/g.nt", [{"individual": "http://x#i", "type": "http://x#T"}], [])
        assert out[0]["error"] == "explain-timeout"
        assert out[0]["explanations"] == []


class TestAdapterPassthrough:
    """execute_reasoning forwards the explain flag and surfaces explanations."""

    def test_explanations_in_response_dict(self, monkeypatch):
        import servers.reasoning_tools as rt
        from editor.reasoning_service import ReasoningRequest, execute_reasoning

        seen = {}

        def fake_detail(name, content=None, explain=False, scope='merged'):
            seen["explain"] = explain
            return {
                "ontology_name": name, "consistent": True,
                "inferred_subclasses": [], "inferred_types": [],
                "nothing_entities": [], "inferred_subclass_count": 0,
                "inferred_type_count": 0, "truncated": False, "error": None,
                "explanations": [{"kind": "instance", "subject": "http://x#i",
                                  "object": "http://x#T", "axiom": "i type T",
                                  "explanations": [["p domain T", "i p j"]]}],
            }

        monkeypatch.setattr(rt, "reason_detailed", fake_detail)
        r = execute_reasoning(
            ReasoningRequest("x", explain=True),
            _content_loader=lambda n: "@prefix : <http://example.org/> .")
        assert seen["explain"] is True
        d = r.to_response_dict()
        assert d["explanations"][0]["axiom"] == "i type T"
        assert d["inconsistency_explanation"] is None
