#!/usr/bin/env python3
"""Contract tests for the single-source markdown kb-board.

Phase 1 intentionally runs RED: `_kb_board` and `bin/kb-board` are not
implemented yet. The important invariant is that these tests encode the future
contract without mutating the live `knowledge/backlog.md` and without wiring
the RED suite into the existing all-tests runner.
"""
from __future__ import annotations

import dataclasses
import importlib
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
from typing import Any, Callable

ROOT = pathlib.Path(__file__).resolve().parents[2]
BIN_DIR = ROOT / "bin"
FIXTURES = pathlib.Path(__file__).resolve().parent / "fixtures"
KB_BOARD = BIN_DIR / "kb-board"


class ContractFailure(AssertionError):
    pass


class ExpectedBoardError(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _as_dict(value: Any) -> dict[str, Any]:
    if dataclasses.is_dataclass(value):
        return dataclasses.asdict(value)
    if isinstance(value, dict):
        return value
    if hasattr(value, "__dict__"):
        return dict(value.__dict__)
    raise ContractFailure(f"Object is not dict-like: {value!r}")


def _field(task: Any, name: str) -> Any:
    if isinstance(task, dict):
        if name in task:
            return task[name]
        return task.get("fields", {}).get(name)
    if hasattr(task, name):
        return getattr(task, name)
    fields = getattr(task, "fields", None)
    if isinstance(fields, dict):
        return fields.get(name)
    raise ContractFailure(f"Task has no accessible field {name!r}: {task!r}")


def _status(task: Any) -> str:
    if isinstance(task, dict):
        return task.get("status") or task.get("section")
    return getattr(task, "status", getattr(task, "section", None))


def _tasks(board: Any) -> list[Any]:
    if isinstance(board, dict):
        if isinstance(board.get("tasks"), list):
            return board["tasks"]
        sections = board.get("sections", {})
        if isinstance(sections, dict):
            out: list[Any] = []
            for items in sections.values():
                out.extend(items)
            return out
    if hasattr(board, "tasks"):
        tasks = getattr(board, "tasks")
        if isinstance(tasks, list):
            return tasks
        if callable(tasks):
            return list(tasks())
    if hasattr(board, "sections"):
        sections = getattr(board, "sections")
        out: list[Any] = []
        if isinstance(sections, dict):
            for items in sections.values():
                out.extend(items)
        else:
            for section in sections:
                out.extend(getattr(section, "tasks", []))
        return out
    raise ContractFailure(f"Board has no accessible tasks: {board!r}")


def _task(board: Any, plan_item_id: str) -> Any:
    for task in _tasks(board):
        if _field(task, "plan_item_id") == plan_item_id:
            return task
    raise ContractFailure(f"Task {plan_item_id!r} not found")


def _module(name: str):
    if str(BIN_DIR) not in sys.path:
        sys.path.insert(0, str(BIN_DIR))
    try:
        return importlib.import_module(f"_kb_board.{name}")
    except ModuleNotFoundError as exc:
        raise ContractFailure(f"RED: _kb_board.{name} is not implemented") from exc


def _cli() -> pathlib.Path:
    if not KB_BOARD.exists():
        raise ContractFailure(f"RED: kb-board CLI is not implemented at {KB_BOARD}")
    return KB_BOARD


def _read_fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def _copy_fixture(tmp: pathlib.Path, name: str) -> pathlib.Path:
    dst = tmp / name
    shutil.copyfile(FIXTURES / name, dst)
    return dst


def _parse(text: str):
    parsing = _module("parsing")
    return parsing.parse_board(text)


def _format(text: str) -> str:
    fmt = _module("fmt")
    return fmt.format_board_text(text)


def _check(text: str, *, ok: bool = True, code: str | None = None):
    check = _module("check")
    result = check.check_board_text(text)
    data = _as_dict(result)
    if ok and not data.get("ok"):
        raise ContractFailure(f"Expected check ok, got {data!r}")
    if not ok:
        if data.get("ok"):
            raise ContractFailure("Expected check failure, got ok")
        errors = data.get("errors", [])
        if code and code not in json.dumps(errors, ensure_ascii=False):
            raise ContractFailure(f"Expected error code {code}, got {errors!r}")
    return result


def _content_hash(task: Any) -> str:
    hashing = _module("hashing")
    value = hashing.content_hash(task)
    if not isinstance(value, str) or len(value) < 32:
        raise ContractFailure(f"content_hash must be a stable hex string, got {value!r}")
    return value


def _mutate(path: pathlib.Path, **kwargs: Any):
    mutation = _module("mutation")
    try:
        return mutation.mutate_file(path=path, **kwargs)
    except Exception as exc:  # implementation should expose `.code`
        code = getattr(exc, "code", None)
        if code:
            raise ExpectedBoardError(code) from exc
        raise


def _expect_error(code: str, fn: Callable[[], Any]) -> None:
    try:
        fn()
    except ExpectedBoardError as exc:
        if exc.code != code:
            raise ContractFailure(f"Expected {code}, got {exc.code}") from exc
        return
    raise ContractFailure(f"Expected {code}, mutation succeeded")


def mutation_happy_path() -> None:
    with tempfile.TemporaryDirectory() as d:
        path = _copy_fixture(pathlib.Path(d), "valid_board.md")
        before = path.read_text(encoding="utf-8")
        board = _parse(before)
        expected = _content_hash(_task(board, "pi-ready"))
        _mutate(
            path,
            op="claim",
            plan_item_id="pi-ready",
            actor="codex",
            expected_content_hash=expected,
            now="2026-05-29T10:00:00Z",
        )
        after = _parse(path.read_text(encoding="utf-8"))
        task = _task(after, "pi-ready")
        assert _status(task) == "In Progress"
        assert _field(task, "claim_owner") == "codex"
        assert _field(task, "claim_id")
        assert _field(task, "claim_expires_at") == "2026-05-29T10:15:00Z"
        _check(path.read_text(encoding="utf-8"))


def cas_conflict() -> None:
    with tempfile.TemporaryDirectory() as d:
        path = _copy_fixture(pathlib.Path(d), "valid_board.md")
        before = path.read_text(encoding="utf-8")
        _expect_error(
            "EHASH",
            lambda: _mutate(
                path,
                op="claim",
                plan_item_id="pi-ready",
                actor="codex",
                expected_content_hash="0" * 64,
                now="2026-05-29T10:00:00Z",
            ),
        )
        assert path.read_text(encoding="utf-8") == before


def illegal_transition() -> None:
    with tempfile.TemporaryDirectory() as d:
        path = _copy_fixture(pathlib.Path(d), "valid_board.md")
        before = path.read_text(encoding="utf-8")
        done_hash = _content_hash(_task(_parse(before), "pi-done"))
        _expect_error(
            "ETRANSITION",
            lambda: _mutate(
                path,
                op="claim",
                plan_item_id="pi-done",
                actor="codex",
                expected_content_hash=done_hash,
                now="2026-05-29T10:00:00Z",
            ),
        )
        assert path.read_text(encoding="utf-8") == before


def ready_transition() -> None:
    with tempfile.TemporaryDirectory() as d:
        path = _copy_fixture(pathlib.Path(d), "valid_board.md")
        board = _parse(path.read_text(encoding="utf-8"))
        _mutate(
            path,
            op="ready",
            plan_item_id="pi-backlog",
            actor="codex",
            reason="triaged for rollout",
            expected_content_hash=_content_hash(_task(board, "pi-backlog")),
            now="2026-05-29T10:00:00Z",
        )
        after = _parse(path.read_text(encoding="utf-8"))
        task = _task(after, "pi-backlog")
        assert _status(task) == "Ready"
        assert "triaged for rollout" in (_field(task, "ready_reason") or "")
        _check(path.read_text(encoding="utf-8"))


def reopen_transition() -> None:
    with tempfile.TemporaryDirectory() as d:
        path = _copy_fixture(pathlib.Path(d), "valid_board.md")
        board = _parse(path.read_text(encoding="utf-8"))
        _mutate(
            path,
            op="reopen",
            plan_item_id="pi-done",
            target_status="Ready",
            actor="codex",
            reason="follow-up needed",
            expected_content_hash=_content_hash(_task(board, "pi-done")),
            now="2026-05-29T10:00:00Z",
        )
        _mutate(
            path,
            op="reopen",
            plan_item_id="pi-cancelled",
            target_status="Backlog",
            actor="codex",
            reason="owner changed",
            expected_content_hash=_content_hash(_task(board, "pi-cancelled")),
            now="2026-05-29T10:01:00Z",
        )
        after = _parse(path.read_text(encoding="utf-8"))
        assert _status(_task(after, "pi-done")) == "Ready"
        assert _status(_task(after, "pi-cancelled")) == "Backlog"
        assert "reopen" in path.read_text(encoding="utf-8").lower()
        _check(path.read_text(encoding="utf-8"))


def no_status_field() -> None:
    _check(_read_fixture("invalid_status_field.md"), ok=False, code="ESTATUS_FIELD")


def task_boundary_hash_heading_safe() -> None:
    board = _parse(_read_fixture("body_boundaries.md"))
    task = _task(board, "pi-boundary")
    assert "### Not a task boundary" in (_field(task, "body") or "")
    assert len(_tasks(board)) == 2
    _check(_read_fixture("body_boundaries.md"))


def task_boundary_tasklike_line_in_body_safe() -> None:
    board = _parse(_read_fixture("body_boundaries.md"))
    task = _task(board, "pi-boundary")
    assert "- [ ] indented body checklist item" in (_field(task, "body") or "")
    assert { _field(t, "plan_item_id") for t in _tasks(board) } == {"pi-boundary", "pi-after-boundary"}


def dynamic_fields_do_not_change_content_hash() -> None:
    board_a = _parse(_read_fixture("hash_equivalent_a.md"))
    board_b = _parse(_read_fixture("hash_equivalent_b.md"))
    assert _content_hash(_task(board_a, "pi-hash")) == _content_hash(_task(board_b, "pi-hash"))
    changed = _read_fixture("hash_equivalent_b.md").replace("Acceptance text.", "Different acceptance.")
    board_c = _parse(changed)
    assert _content_hash(_task(board_a, "pi-hash")) != _content_hash(_task(board_c, "pi-hash"))


def lock_contention() -> None:
    locks = _module("locks")
    with tempfile.TemporaryDirectory() as d:
        lock_path = pathlib.Path(d) / "board.lock"
        with locks.acquire_file_lock(lock_path, timeout_s=1.0):
            code = (
                "import pathlib, sys; "
                f"sys.path.insert(0, {str(BIN_DIR)!r}); "
                "from _kb_board import locks; "
                f"p=pathlib.Path({str(lock_path)!r}); "
                "locks.acquire_file_lock(p, timeout_s=0.05).__enter__()"
            )
            proc = subprocess.run([sys.executable, "-c", code], text=True, capture_output=True)
        assert proc.returncode != 0
        assert "ELOCK" in (proc.stderr + proc.stdout)


def claim_lease_expiry() -> None:
    with tempfile.TemporaryDirectory() as d:
        path = _copy_fixture(pathlib.Path(d), "valid_board.md")
        lease = _module("lease")
        lease.sweep_expired_file(path=path, actor="sweeper", now="2026-05-29T10:00:00Z")
        board = _parse(path.read_text(encoding="utf-8"))
        task = _task(board, "pi-expired")
        assert _status(task) == "Ready"
        assert not _field(task, "claim_owner")
        assert not _field(task, "claim_id")
        assert not _field(task, "claim_expires_at")


def heartbeat_extends() -> None:
    with tempfile.TemporaryDirectory() as d:
        path = _copy_fixture(pathlib.Path(d), "valid_board.md")
        before_board = _parse(path.read_text(encoding="utf-8"))
        before_hash = _content_hash(_task(before_board, "pi-active"))
        _mutate(
            path,
            op="heartbeat",
            plan_item_id="pi-active",
            actor="codex",
            claim_id="clm-active",
            now="2026-05-29T10:05:00Z",
        )
        after = _parse(path.read_text(encoding="utf-8"))
        task = _task(after, "pi-active")
        assert _field(task, "claim_expires_at") == "2026-05-29T10:20:00Z"
        assert _content_hash(task) == before_hash


def review_claim_provenance() -> None:
    with tempfile.TemporaryDirectory() as d:
        path = _copy_fixture(pathlib.Path(d), "valid_board.md")
        before = _parse(path.read_text(encoding="utf-8"))
        _mutate(
            path,
            op="request-review",
            plan_item_id="pi-active",
            actor="codex",
            claim_id="clm-active",
            expected_content_hash=_content_hash(_task(before, "pi-active")),
            now="2026-05-29T10:00:00Z",
        )
        in_review = _task(_parse(path.read_text(encoding="utf-8")), "pi-active")
        assert _status(in_review) == "Review"
        assert _field(in_review, "claim_owner") == "codex"
        assert _field(in_review, "claim_id") == "clm-active"
        _mutate(
            path,
            op="close",
            plan_item_id="pi-active",
            actor="codex",
            claim_id="clm-active",
            expected_content_hash=_content_hash(in_review),
            outcome="closed",
            now="2026-05-29T10:01:00Z",
        )
        closed = _task(_parse(path.read_text(encoding="utf-8")), "pi-active")
        assert _status(closed) == "Done"
        assert not _field(closed, "claim_owner")
        assert not _field(closed, "claim_id")


def provenance_mismatch_rejected() -> None:
    with tempfile.TemporaryDirectory() as d:
        path = _copy_fixture(pathlib.Path(d), "valid_board.md")
        before = path.read_text(encoding="utf-8")
        review = _task(_parse(before), "pi-review")
        _expect_error(
            "ECLAIM",
            lambda: _mutate(
                path,
                op="close",
                plan_item_id="pi-review",
                actor="codex",
                claim_id="wrong",
                expected_content_hash=_content_hash(review),
                outcome="closed",
                now="2026-05-29T10:00:00Z",
            ),
        )
        assert path.read_text(encoding="utf-8") == before


def return_from_review_mints_new_lease() -> None:
    with tempfile.TemporaryDirectory() as d:
        path = _copy_fixture(pathlib.Path(d), "valid_board.md")
        before = _parse(path.read_text(encoding="utf-8"))
        review = _task(before, "pi-review")
        _mutate(
            path,
            op="return-from-review",
            plan_item_id="pi-review",
            actor="codex",
            claim_id="clm-review",
            expected_content_hash=_content_hash(review),
            now="2026-05-29T10:00:00Z",
        )
        after = _task(_parse(path.read_text(encoding="utf-8")), "pi-review")
        assert _status(after) == "In Progress"
        assert _field(after, "claim_owner") == "codex"
        assert _field(after, "claim_id") != "clm-review"
        assert _field(after, "claim_expires_at") == "2026-05-29T10:15:00Z"


def fmt_checkbox_mapping() -> None:
    formatted = _format(_read_fixture("messy_markers.md"))
    by_id = { _field(t, "plan_item_id"): t for t in _tasks(_parse(formatted)) }
    assert _field(by_id["pi-fmt-backlog"], "marker") == "[ ]"
    assert _field(by_id["pi-fmt-ready"], "marker") == "[ ]"
    assert _field(by_id["pi-fmt-blocked"], "marker") == "[ ]"
    assert _field(by_id["pi-fmt-progress"], "marker") == "[>]"
    assert _field(by_id["pi-fmt-review"], "marker") == "[>]"
    assert _field(by_id["pi-fmt-done"], "marker") == "[x]"
    assert _field(by_id["pi-fmt-cancelled"], "marker") == "[~]"


def fmt_idempotent() -> None:
    once = _format(_read_fixture("messy_markers.md"))
    twice = _format(once)
    assert once == twice


def check_rejects_missing_field() -> None:
    _check(_read_fixture("missing_required.md"), ok=False, code="EREQUIRED")


def depends_on_cycle_rejected() -> None:
    _check(_read_fixture("depends_cycle.md"), ok=False, code="EDEPENDS_CYCLE")


def invalid_mutation_not_published() -> None:
    with tempfile.TemporaryDirectory() as d:
        path = _copy_fixture(pathlib.Path(d), "valid_board.md")
        before = path.read_text(encoding="utf-8")
        ready = _task(_parse(before), "pi-ready")
        _expect_error(
            "ECHECK",
            lambda: _mutate(
                path,
                op="progress",
                plan_item_id="pi-ready",
                actor="codex",
                claim_id=None,
                expected_content_hash=_content_hash(ready),
                updates={"depends_on": ["pi-ready"]},
                now="2026-05-29T10:00:00Z",
            ),
        )
        assert path.read_text(encoding="utf-8") == before


def atomic_rename_crash() -> None:
    with tempfile.TemporaryDirectory() as d:
        path = _copy_fixture(pathlib.Path(d), "valid_board.md")
        before = path.read_text(encoding="utf-8")
        board = _parse(before)
        _expect_error(
            "ECRASH_SIMULATED",
            lambda: _mutate(
                path,
                op="claim",
                plan_item_id="pi-ready",
                actor="codex",
                expected_content_hash=_content_hash(_task(board, "pi-ready")),
                now="2026-05-29T10:00:00Z",
                simulate_crash_at="before_rename",
            ),
        )
        assert path.read_text(encoding="utf-8") == before


def migration_roundtrip() -> None:
    migrate = _module("migrate")
    migrated = migrate.migrate_text(
        _read_fixture("legacy_oneline.md"),
        owner="unassigned",
        now="2026-05-29T10:00:00Z",
    )
    _check(migrated)
    board = _parse(migrated)
    assert _status(_task(board, "legacy-open")) == "Backlog"
    assert _status(_task(board, "legacy-progress")) == "In Progress"
    assert _status(_task(board, "legacy-done")) == "Done"
    assert "- [ ] Legacy open task —" not in migrated


def legacy_writer_fail_fast() -> None:
    _cli()
    migrate = _module("migrate")
    source = migrate.fail_fast_stub_source()
    assert "kb-board" in source
    assert "fail" in source.lower()
    assert "legacy" in source.lower()


def depends_on_terminal_allowed() -> None:
    _check(_read_fixture("depends_terminal.md"))


def content_hash_normalized_field_order() -> None:
    board_a = _parse(_read_fixture("hash_equivalent_a.md"))
    board_b = _parse(_read_fixture("hash_equivalent_b.md"))
    assert _content_hash(_task(board_a, "pi-hash")) == _content_hash(_task(board_b, "pi-hash"))


def lock_backend_import_safe() -> None:
    locks = _module("locks")
    backend = locks.select_backend(os_name="unsupported-os", modules={})
    assert _as_dict(backend).get("supported") is False
    assert _as_dict(backend).get("error_code") == "ELOCK_UNSUPPORTED"


def cutover_no_old_writer_gap() -> None:
    migrate = _module("migrate")
    plan = migrate.plan_cutover(
        board_path="knowledge/backlog.md",
        old_writer_paths=["bin/kb-backlog"],
        candidate_path="knowledge/backlog.md.migrated",
    )
    steps = [_as_dict(step).get("action") for step in plan.steps]
    assert steps.index("install_old_writer_fail_fast") < steps.index("migrate_live_board")
    assert steps.index("verify_old_writer_fail_fast") < steps.index("migrate_live_board")


def cli_progress_updates_metadata() -> None:
    with tempfile.TemporaryDirectory() as d:
        path = _copy_fixture(pathlib.Path(d), "valid_board.md")
        proc = subprocess.run(
            [
                str(_cli()),
                "progress",
                str(path),
                "--plan-item-id",
                "pi-backlog",
                "--field",
                "priority=P0",
                "--field",
                "owner=example-project",
                "--json",
            ],
            text=True,
            capture_output=True,
        )
        if proc.returncode != 0:
            raise ContractFailure(f"kb-board progress failed: {proc.stderr or proc.stdout}")
        board = _parse(path.read_text(encoding="utf-8"))
        task = _task(board, "pi-backlog")
        assert _field(task, "priority") == "P0"
        assert _field(task, "owner") == "example-project"
        _check(path.read_text(encoding="utf-8"))


def cli_multi_writer_append_stress() -> None:
    with tempfile.TemporaryDirectory() as d:
        path = _copy_fixture(pathlib.Path(d), "valid_board.md")
        workers = 4
        per_worker = 12
        child = r"""
import pathlib
import subprocess
import sys

kb = pathlib.Path(sys.argv[1])
board = pathlib.Path(sys.argv[2])
worker = sys.argv[3]
count = int(sys.argv[4])
for i in range(count):
    tid = f"stress-{worker}-{i}"
    proc = subprocess.run(
        [
            str(kb),
            "append",
            str(board),
            f"Stress task {worker}-{i}",
            "--plan-item-id",
            tid,
            "--priority",
            "P2",
            "--owner",
            "stress",
            "--status",
            "Backlog",
            "--actor",
            f"worker-{worker}",
            "--json",
        ],
        text=True,
        capture_output=True,
    )
    if proc.returncode not in (0, 5):
        print(proc.stderr or proc.stdout, file=sys.stderr)
        sys.exit(proc.returncode)
"""
        procs = [
            subprocess.Popen(
                [sys.executable, "-c", child, str(_cli()), str(path), str(worker), str(per_worker)],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            for worker in range(workers)
        ]
        for proc in procs:
            stdout, stderr = proc.communicate(timeout=30)
            if proc.returncode != 0:
                raise ContractFailure(f"stress worker failed: {stderr or stdout}")
        board = _parse(path.read_text(encoding="utf-8"))
        ids = {_field(task, "plan_item_id") for task in _tasks(board)}
        expected = {f"stress-{worker}-{i}" for worker in range(workers) for i in range(per_worker)}
        missing = sorted(expected - ids)
        if missing:
            raise ContractFailure(f"lost concurrent append updates: {missing[:8]} of {len(missing)} missing")
        _check(path.read_text(encoding="utf-8"))


TESTS: list[Callable[[], None]] = [
    mutation_happy_path,
    cas_conflict,
    illegal_transition,
    ready_transition,
    reopen_transition,
    no_status_field,
    task_boundary_hash_heading_safe,
    task_boundary_tasklike_line_in_body_safe,
    dynamic_fields_do_not_change_content_hash,
    lock_contention,
    claim_lease_expiry,
    heartbeat_extends,
    review_claim_provenance,
    provenance_mismatch_rejected,
    return_from_review_mints_new_lease,
    fmt_checkbox_mapping,
    fmt_idempotent,
    check_rejects_missing_field,
    depends_on_cycle_rejected,
    invalid_mutation_not_published,
    atomic_rename_crash,
    migration_roundtrip,
    legacy_writer_fail_fast,
    depends_on_terminal_allowed,
    content_hash_normalized_field_order,
    lock_backend_import_safe,
    cutover_no_old_writer_gap,
    cli_progress_updates_metadata,
    cli_multi_writer_append_stress,
]


def main() -> int:
    failures: list[tuple[str, str]] = []
    for test in TESTS:
        try:
            test()
        except Exception as exc:
            failures.append((test.__name__, str(exc)))
            print(f"not ok - {test.__name__}: {exc}", file=sys.stderr)
        else:
            print(f"ok - {test.__name__}")
    print(f"kb-board contract: {len(TESTS) - len(failures)}/{len(TESTS)} passed")
    if failures:
        print("RED: kb-board contract is not implemented yet", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
