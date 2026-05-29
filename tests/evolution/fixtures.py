#!/usr/bin/env python3
"""Evolution Loop v0-minimal acceptance fixtures.

These fixtures are intentionally synthetic and local-only. They exercise the
runtime primitives from decisions/vepol-evolution-loop-v0.md without touching a
live knowledge base or external connectors.
"""
from __future__ import annotations

import json
import multiprocessing as mp
import pathlib
import shutil
import sys
import tempfile


REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "bin"))

from _kb_evolution import ledger, policy, proposals, scaffold, signals, tier0  # noqa: E402


def write(path: pathlib.Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.strip() + "\n", encoding="utf-8")


def assert_(cond: bool, msg: str) -> None:
    if not cond:
        print(f"  ✘ {msg}", file=sys.stderr)
        sys.exit(1)
    print(f"  ✓ {msg}")


def make_knowledge() -> pathlib.Path:
    root = pathlib.Path(tempfile.mkdtemp(prefix="kb-evolution-"))
    knowledge = root / "knowledge"
    knowledge.mkdir()
    write(knowledge / "log.md", "# log\n\nNarrative recieve typo only.\n")
    write(knowledge / "incidents.md", "# Incidents\n\n## Prevention rules\n")
    write(knowledge / "agents" / "agent-card.md", "# Agent\n\n## Self-introduction\n\nI help.\n")
    return knowledge


def valid_proposal(knowledge: pathlib.Path, *, proposal_id: str = "prop-prompt-2026-05-23-001", risk_tier: int = 1,
                   target: str = "agents/agent-card.md", author: str = "codex",
                   input_origins: list[str] | None = None) -> pathlib.Path:
    input_origins = input_origins or ["runtime-generated"]
    path = knowledge / "evolution" / "proposals" / f"{proposal_id}.md"
    write(path, f"""---
proposal_id: {proposal_id}
type: mutation-proposal
status: pending
created: 2026-05-23T18:00:00Z
author:
  type: orchestrator
  identity: {author}
surface_type: prompt
surface_target: {target}
scope:
  affected_section: Self-introduction
  unit_of_mutation: markdown-block
  blast_radius:
    files: 1
    bytes: 32
    runtimes_affected: [codex]
mutation_diff: inline
rationale:
  observation_signal: sig-2026-05-23-001
  hypothesis: Make the introduction clearer.
  expected_metric: accepted on next three tasks
  metric_objectivity: objective
risk_tier: {risk_tier}
risk_justification: bounded wording change
reversibility:
  type: kb-revert
  atomicity_unit: markdown-block
  test_executed: true
  test_evidence: evolution/replay-fixtures/reference.txt
input_origins: {json.dumps(input_origins)}
public_safe: false
evaluation_plan:
  reviewer_orchestrators: [claude-code]
  conflict_check: pass
  shadow_replay_tasks: null
  measure_on_next_real_tasks: 3
  regression_check: manual reference
  drift_check: pass
  invariant_check: pass
  hitl_required: false
  ambiguity_flags: []
related:
  parent_proposals: []
  related_signals: []
  affects_promoted_capability: null
---

# Reference proposal

Synthetic proposal body.
""")
    return path


def mutation_entry(entry_id: str, proposal_id: str, target: str = "agents/agent-card.md") -> dict:
    return {
        "entry_id": entry_id,
        "type": "mutation",
        "proposal_id": proposal_id,
        "surface_type": "prompt",
        "surface_target": target,
        "date": "2026-05-23T18:10:00Z",
        "expires": None,
        "risk_tier": 1,
        "evaluation": {
            "reviewer_orchestrators": ["claude-code"],
            "conflict_check": "pass",
            "shadow_replay_result": None,
            "measure_result": "evolution/replay-fixtures/reference.txt",
            "sahoo": {
                "drift_check": "pass",
                "invariant_check": "pass",
                "regression_check": "pass",
            },
        },
        "hitl_approval": {
            "required": False,
            "granted_by": None,
            "granted_at": None,
        },
        "git_commit": None,
        "parent_entries": [],
        "ambiguity_flags": [],
        "public_safe": False,
        "written_by": [{"reviewer_capability": "claude-code"}],
        "signature": None,
    }


def test_scaffold_schema_and_signal() -> None:
    knowledge = make_knowledge()
    try:
        scaffold.ensure_evolution_tree(knowledge)
        assert_((knowledge / "evolution" / "proposals").is_dir(), "proposals dir created")
        assert_((knowledge / "evolution" / "archive").is_dir(), "archive dir created")
        assert_((knowledge / "evolution" / "replay-fixtures").is_dir(), "replay-fixtures dir created")
        assert_((knowledge / "evolution" / "mutations.md").is_file(), "mutations.md created")
        assert_((knowledge / "evolution" / "pending-signals.md").is_file(), "pending-signals.md created")

        sig = signals.append_signal(
            knowledge,
            signal_id="sig-2026-05-23-001",
            source="test",
            surface="prompt",
            summary="user corrected wording",
        )
        assert_(sig["signal_id"] == "sig-2026-05-23-001", "pending signal appended")

        proposal_path = valid_proposal(knowledge)
        proposal = proposals.validate_proposal_file(proposal_path)
        assert_(proposal["proposal_id"] == "prop-prompt-2026-05-23-001", "valid proposal passes schema")

        bad = knowledge / "evolution" / "proposals" / "bad.md"
        write(bad, "---\ntype: mutation-proposal\n---\n")
        try:
            proposals.validate_proposal_file(bad)
        except proposals.ProposalError as exc:
            assert_("proposal_id" in str(exc), "malformed proposal rejected with specific key")
        else:
            raise AssertionError("malformed proposal unexpectedly passed")
    finally:
        shutil.rmtree(knowledge.parent)


def _append_worker(args: tuple[str, str, str]) -> None:
    knowledge_s, entry_id, proposal_id = args
    knowledge = pathlib.Path(knowledge_s)
    ledger.append_entry(knowledge, mutation_entry(entry_id, proposal_id), actor="reviewer-capability")


def test_ledger_parse_cancel_and_locking() -> None:
    knowledge = make_knowledge()
    try:
        scaffold.ensure_evolution_tree(knowledge)
        proposal_id = "prop-prompt-2026-05-23-001"
        ledger.append_entry(knowledge, mutation_entry("mut-a-2026-05-23-001", proposal_id), actor="reviewer-capability")
        cancel = {
            "entry_id": "cancel-mut-a-2026-05-23-001",
            "type": "cancel-mutation",
            "cancels_entry_id": "mut-a-2026-05-23-001",
            "date": "2026-05-23T18:10:00Z",
            "trigger": "regression",
            "incident": "incidents.md#synthetic",
            "git_revert_commit": None,
            "written_by": [{"runtime": "reviewer-capability"}],
        }
        ledger.append_entry(knowledge, cancel, actor="reviewer-capability")
        entries = ledger.parse_ledger(knowledge / "evolution" / "mutations.md")
        assert_(len(entries) == 2, "ledger parses two YAML entries")
        state = ledger.current_state(entries, proposal_id=proposal_id)
        assert_(state["state"] == "cancelled", "cancel-mutation overrides same-timestamp mutation")

        # Concurrent appends should not corrupt YAML blocks.
        args = [
            (str(knowledge), "mut-b-2026-05-23-001", "prop-b"),
            (str(knowledge), "mut-c-2026-05-23-001", "prop-c"),
        ]
        with mp.Pool(2) as pool:
            pool.map(_append_worker, args)
        entries = ledger.parse_ledger(knowledge / "evolution" / "mutations.md")
        ids = {entry["entry_id"] for entry in entries}
        assert_({"mut-b-2026-05-23-001", "mut-c-2026-05-23-001"} <= ids, "fcntl appends preserve both concurrent entries")

        write(knowledge / "evolution" / "mutations.md", "## bad\n\n```yaml\nentry_id: broken\n```\n")
        try:
            ledger.parse_ledger(knowledge / "evolution" / "mutations.md")
        except ledger.LedgerError as exc:
            assert_("date" in str(exc), "fail-closed parser rejects missing date")
        else:
            raise AssertionError("corrupt ledger unexpectedly parsed")
    finally:
        shutil.rmtree(knowledge.parent)


def test_tier0_validator() -> None:
    path = pathlib.Path("sources/example.md")
    before = "# Note\n\nI recieve updates.\n"
    after = "# Note\n\nI receive updates.\n"
    assert_(tier0.validate_tier0_typo(before, after, path, public_safe="reviewed").ok, "known typo accepted as Tier 0")

    result = tier0.validate_tier0_typo("# Rule\n\nAgents must ask.\n", "# Rule\n\nAgents may ask.\n", path, public_safe="reviewed")
    assert_(not result.ok and "high-impact" in result.reason, "semantic must→may change rejected")

    result = tier0.validate_tier0_typo("# Metric\n\n5% threshold\n", "# Metric\n\n50% threshold\n", path, public_safe="reviewed")
    assert_(not result.ok and "identifier" in result.reason, "number change rejected")

    result = tier0.validate_tier0_typo("---\na: 1\n---\n\nBody recieve.\n", "---\na: 2\n---\n\nBody receive.\n", path, public_safe="reviewed")
    assert_(not result.ok and "frontmatter" in result.reason, "frontmatter touch rejected")
    assert_(not tier0.validate_tier0_typo(before, after, path, public_safe="false").ok, "public-bound unreviewed Tier 0 rejected")


def test_policy_refusals() -> None:
    knowledge = make_knowledge()
    try:
        scaffold.ensure_evolution_tree(knowledge)
        tier1 = proposals.validate_proposal_file(valid_proposal(knowledge, risk_tier=1))
        evaluator = {
            "identity": "claude-code",
            "sahoo": {"drift_check": "pass", "invariant_check": "pass", "regression_check": "pass"},
            "conflict_check": "pass",
        }
        assert_(policy.validate_apply_request(knowledge, tier1, evaluator=evaluator).allowed, "Tier 1 non-conflict request allowed")

        coi = dict(evaluator)
        coi["identity"] = "codex"
        res = policy.validate_apply_request(knowledge, tier1, evaluator=coi)
        assert_(not res.allowed and res.hitl_required and "conflict" in res.reason, "author-as-sole-evaluator escalates")

        tier2 = proposals.validate_proposal_file(valid_proposal(knowledge, proposal_id="prop-workflow-2026-05-23-001", risk_tier=2))
        res = policy.validate_apply_request(knowledge, tier2, evaluator=evaluator, hitl_approved=True)
        assert_(not res.allowed and "v0.1" in res.reason, "Tier 2 apply refused in v0-minimal")

        banned = proposals.validate_proposal_file(
            valid_proposal(knowledge, proposal_id="prop-policy-2026-05-23-001", risk_tier=1,
                           target="decisions/autonomy-mode.md")
        )
        res = policy.validate_apply_request(knowledge, banned, evaluator=evaluator)
        assert_(not res.allowed and "ban-list" in res.reason, "constitutional ban-list path refused")

        external = proposals.validate_proposal_file(
            valid_proposal(knowledge, proposal_id="prop-ext-2026-05-23-001", risk_tier=1,
                           input_origins=["user-typed-here"])
        )
        res = policy.validate_apply_request(knowledge, external, evaluator=evaluator, scanner_available=False)
        assert_(not res.allowed and "scanner" in res.reason, "human/user-typed input still requires scanner")

        hub_target = proposals.validate_proposal_file(
            valid_proposal(knowledge, proposal_id="prop-hub-2026-05-23-001", risk_tier=1,
                           target="/Users/macbook/knowledge/log.md")
        )
        res = policy.validate_apply_request(knowledge, hub_target, evaluator=evaluator, scanner_available=False)
        assert_(not res.allowed and "hub-writer" in res.reason, "hub-writer never exempt from scanner")
    finally:
        shutil.rmtree(knowledge.parent)


def test_reference_lifecycle() -> None:
    knowledge = make_knowledge()
    try:
        scaffold.ensure_evolution_tree(knowledge)
        signals.append_signal(knowledge, signal_id="sig-2026-05-23-001", source="retro", surface="prompt", summary="reference")
        proposal = proposals.validate_proposal_file(valid_proposal(knowledge))
        evaluator = {
            "identity": "claude-code",
            "sahoo": {"drift_check": "pass", "invariant_check": "pass", "regression_check": "pass"},
            "conflict_check": "pass",
        }
        res = policy.validate_apply_request(knowledge, proposal, evaluator=evaluator)
        assert_(res.allowed, "reference proposal evaluates")
        ledger.append_entry(knowledge, mutation_entry("mut-reference-2026-05-23-001", proposal["proposal_id"]), actor="reviewer-capability")
        entries = ledger.parse_ledger(knowledge / "evolution" / "mutations.md")
        assert_(ledger.current_state(entries, proposal_id=proposal["proposal_id"])["state"] == "applied", "reference mutation promoted")
        cancel = {
            "entry_id": "cancel-mut-reference-2026-05-23-001",
            "type": "cancel-mutation",
            "cancels_entry_id": "mut-reference-2026-05-23-001",
            "date": "2026-05-23T18:20:00Z",
            "trigger": "regression",
            "incident": None,
            "git_revert_commit": None,
            "written_by": [{"runtime": "reviewer-capability"}],
        }
        ledger.append_entry(knowledge, cancel, actor="reviewer-capability")
        entries = ledger.parse_ledger(knowledge / "evolution" / "mutations.md")
        assert_(ledger.current_state(entries, proposal_id=proposal["proposal_id"])["state"] == "cancelled", "reference mutation rolls back")
    finally:
        shutil.rmtree(knowledge.parent)


def main() -> None:
    print("Evolution Loop v0-minimal fixtures")
    test_scaffold_schema_and_signal()
    test_ledger_parse_cancel_and_locking()
    test_tier0_validator()
    test_policy_refusals()
    test_reference_lifecycle()
    print("\nEvolution Loop v0-minimal fixtures passed")


if __name__ == "__main__":
    main()
