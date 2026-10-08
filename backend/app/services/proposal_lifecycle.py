"""Small, storage-agnostic lifecycle rules for explicit change proposals.

The product has more than one proposal table, but they all need to make the
same decision *before* an apply/reject/undo handler touches its target asset:
either execute the transition, return an idempotent receipt, or fail without
performing a side effect.  Keeping that decision here avoids relying on a
late database status update as the concurrency guard.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.errors import ConflictError


@dataclass(frozen=True)
class ProposalTransition:
    """Legal source states for one user-visible proposal action.

    ``replayable_from`` describes a completed action whose stored receipt can
    be returned again without reapplying the underlying change.
    """

    name: str
    executable_from: frozenset[str]
    replayable_from: frozenset[str]


APPLY = ProposalTransition(
    name="apply",
    executable_from=frozenset({"pending"}),
    replayable_from=frozenset({"applied"}),
)
REJECT = ProposalTransition(
    name="reject",
    executable_from=frozenset({"pending"}),
    replayable_from=frozenset({"rejected"}),
)
UNDO = ProposalTransition(
    name="undo",
    executable_from=frozenset({"applied"}),
    replayable_from=frozenset({"undone"}),
)


def should_execute_transition(
    status: str,
    transition: ProposalTransition,
    *,
    conflict_message: str,
) -> bool:
    """Return whether the caller may perform a proposal side effect.

    Call this immediately after loading the proposal and before writing the
    target asset.  ``False`` means the operation was already completed and
    the caller should return its existing receipt unchanged.
    """

    if status in transition.executable_from:
        return True
    if status in transition.replayable_from:
        return False
    raise ConflictError(conflict_message)
