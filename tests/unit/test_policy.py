"""Политика риска как чистое решение."""

from ai_department.domain.risk import RiskLevel
from ai_department.domain.states import PolicyDecision
from ai_department.tools.hashing import args_hash
from ai_department.tools.policy import PolicyCall, PolicyContext, decide


def _context(
    *,
    bound: frozenset[str] | None = None,
    role: RiskLevel = RiskLevel.ACT,
    platform: RiskLevel = RiskLevel.ACT,
) -> PolicyContext:
    return PolicyContext(
        run_id="run-1",
        role_id="clerk",
        bound_tools=bound if bound is not None else frozenset({"read_note", "commit_note"}),
        role_ceiling=role,
        platform_ceiling=platform,
    )


def test_unknown_tool_is_denied_by_rule_one() -> None:
    result = decide(PolicyCall("foreign", RiskLevel.READ, False), _context())
    assert result.decision is PolicyDecision.DENY
    assert result.rule == 1


def test_above_role_ceiling_is_denied_by_rule_two() -> None:
    result = decide(
        PolicyCall("commit_note", RiskLevel.ACT, False),
        _context(role=RiskLevel.DRAFT),
    )
    assert result.decision is PolicyDecision.DENY
    assert result.rule == 2


def test_destructive_above_platform_ceiling_is_rule_two() -> None:
    result = decide(PolicyCall("commit_note", RiskLevel.DESTRUCTIVE, True), _context())
    assert result.decision is PolicyDecision.DENY
    assert result.rule == 2


def test_destructive_stays_denied_even_if_ceiling_is_open() -> None:
    result = decide(
        PolicyCall("wipe", RiskLevel.DESTRUCTIVE, True),
        _context(
            bound=frozenset({"wipe"}), role=RiskLevel.DESTRUCTIVE, platform=RiskLevel.DESTRUCTIVE
        ),
    )
    assert result.decision is PolicyDecision.DENY
    assert result.rule == 3


def test_read_and_draft_are_allowed() -> None:
    assert (
        decide(PolicyCall("read_note", RiskLevel.READ, False), _context()).decision
        is PolicyDecision.ALLOW
    )
    draft = decide(
        PolicyCall("draft_note", RiskLevel.DRAFT, False),
        _context(bound=frozenset({"draft_note"})),
    )
    assert draft.decision is PolicyDecision.ALLOW
    assert draft.rule == 4


def test_act_without_grant_confirms_and_with_grant_allows() -> None:
    waiting = decide(PolicyCall("commit_note", RiskLevel.ACT, False), _context())
    allowed = decide(PolicyCall("commit_note", RiskLevel.ACT, True), _context())
    assert waiting.decision is PolicyDecision.CONFIRM
    assert allowed.decision is PolicyDecision.ALLOW
    assert allowed.rule == 5


def test_hash_ignores_insignificant_field_and_changes_with_text() -> None:
    left = args_hash({"key": "a", "text": "one", "trace_id": "x"}, frozenset({"trace_id"}))
    right = args_hash({"text": "one", "key": "a", "trace_id": "y"}, frozenset({"trace_id"}))
    other = args_hash({"key": "a", "text": "two", "trace_id": "x"}, frozenset({"trace_id"}))
    assert left == right
    assert left != other
