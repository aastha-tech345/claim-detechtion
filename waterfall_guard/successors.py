"""Expected-Successor Testing — E4.

Determines which downstream events should exist based on accepted lifecycle
relationships and claim status. Identifies:
- Missing expected successors (claim should have progressed but hasn't)
- Delayed successors (claim progressed but late)
- Actionable claims (can still be remedied before deadline)
- Expired claims (filing deadline past, no recovery option)

All operations are read-only analysis; no writes to external systems.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from waterfall_guard.models.claim import ClaimStatus, RelationshipState


class SuccessorState(str, Enum):
    """Successor event classification (E4)."""
    PRESENT = "present"
    MISSING = "missing"
    DELAYED = "delayed"


class ActionableState(str, Enum):
    """Claim actionability based on filing deadline (E4)."""
    ACTIONABLE = "actionable"  # Can be remedied (deadline future)
    ESCALATION_REQUIRED = "escalation_required"  # Deadline imminent (< 7 days)
    EXPIRED = "expired"  # Deadline past, requires audit
    UNKNOWN = "unknown"  # No deadline available


@dataclass
class SuccessorExpectation:
    """Defines expected downstream transitions between claim statuses (E4)."""
    from_status: ClaimStatus
    to_status: ClaimStatus
    expected_days: int  # Maximum days to transition
    payer_sla: Optional[str] = None  # E.g., "UB04_30_days", "X12_45_days"


@dataclass
class MissingSuccessorFinding:
    """A claim missing an expected downstream successor (E4)."""
    token_id: str  # De-identified claim ID
    current_status: ClaimStatus
    expected_status: ClaimStatus
    expected_days: int
    days_since_transition: int  # Days since last status change
    reason: str  # Why successor is missing (e.g., "No claim progress in 30 days despite ACK")


@dataclass
class ActionableFinding:
    """Claim classification relative to filing deadline (E4)."""
    token_id: str
    state: ActionableState
    filing_deadline: Optional[datetime]
    days_until_deadline: Optional[int]  # Positive if future, negative if past
    reason: str


class SuccessorMatcher:
    """Matches claims to expected downstream successors and classifies actionability (E4)."""

    def __init__(self, successor_expectations: Optional[List[SuccessorExpectation]] = None):
        """Initialize with default or custom successor expectations.

        Args:
            successor_expectations: List of SuccessorExpectation rules. If None, uses defaults.
        """
        self.expectations = successor_expectations or self._default_expectations()
        self._expectations_by_from = self._index_expectations()

    def _default_expectations(self) -> List[SuccessorExpectation]:
        """Default successor expectations for common claim lifecycle."""
        return [
            SuccessorExpectation(
                from_status=ClaimStatus.SUBMITTED,
                to_status=ClaimStatus.ACKNOWLEDGED,
                expected_days=3,
                payer_sla="immediate_ack",
            ),
            SuccessorExpectation(
                from_status=ClaimStatus.ACKNOWLEDGED,
                to_status=ClaimStatus.IN_ADJUDICATION,
                expected_days=7,
                payer_sla="ub04_7_days",
            ),
            SuccessorExpectation(
                from_status=ClaimStatus.IN_ADJUDICATION,
                to_status=ClaimStatus.PAID,
                expected_days=30,
                payer_sla="ub04_30_days",
            ),
        ]

    def _index_expectations(self) -> Dict[ClaimStatus, List[SuccessorExpectation]]:
        """Build a dict mapping from_status → List[SuccessorExpectation] for fast lookup."""
        by_from = {}
        for expectation in self.expectations:
            if expectation.from_status not in by_from:
                by_from[expectation.from_status] = []
            by_from[expectation.from_status].append(expectation)
        return by_from

    def check_missing_successors(
        self,
        claim: Dict[str, Any],
    ) -> List[MissingSuccessorFinding]:
        """Check if a claim is missing expected downstream successors (E4).

        Args:
            claim: Claim dict with token_id, status, last_status_change_at, relationships[]

        Returns:
            List of MissingSuccessorFinding for each unmet expectation.
        """
        findings = []
        token_id = claim.get("token_id")
        current_status_str = claim.get("status")
        last_change_at = claim.get("last_status_change_at")

        if not token_id or not current_status_str or not last_change_at:
            return []

        try:
            current_status = ClaimStatus(current_status_str)
        except ValueError:
            return []

        # Check if this status has any expected successors
        expectations = self._expectations_by_from.get(current_status, [])
        if not expectations:
            return []

        now = datetime.now(timezone.utc)
        if isinstance(last_change_at, str):
            try:
                last_change_at = datetime.fromisoformat(last_change_at.replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                return []

        days_since_transition = (now - last_change_at).days

        # For each expected successor, check if any related claim has that status
        for expectation in expectations:
            # Check if any ACCEPTED relationship to a claim with expected_status exists
            has_successor = self._has_accepted_successor(
                claim, expectation.to_status
            )

            if not has_successor and days_since_transition >= expectation.expected_days:
                reason = (
                    f"Claim in {current_status.value} for {days_since_transition} days "
                    f"(expected to reach {expectation.to_status.value} within {expectation.expected_days} days)"
                )
                findings.append(
                    MissingSuccessorFinding(
                        token_id=token_id,
                        current_status=current_status,
                        expected_status=expectation.to_status,
                        expected_days=expectation.expected_days,
                        days_since_transition=days_since_transition,
                        reason=reason,
                    )
                )

        return findings

    def _has_accepted_successor(self, claim: Dict[str, Any], target_status: ClaimStatus) -> bool:
        """Check if claim has an ACCEPTED relationship to a successor with target_status.

        Args:
            claim: Claim dict with relationships[]
            target_status: Status we're looking for in successor

        Returns:
            True if at least one ACCEPTED relationship to a successor exists.
        """
        relationships = claim.get("relationships", [])
        if not relationships:
            return False

        for rel in relationships:
            # Relationships should be dicts or RelationshipState objects
            rel_state = rel.get("state") if isinstance(rel, dict) else getattr(rel, "state", None)
            if rel_state == RelationshipState.ACCEPTED or rel_state == "accepted":
                # TODO: Check if to_id references a claim/status in successors list
                # For now, just presence of ACCEPTED relationship to a later transaction implies progress
                return True

        return False

    def classify_actionability(
        self,
        claim: Dict[str, Any],
        escalation_threshold_days: int = 7,
    ) -> ActionableFinding:
        """Classify claim as actionable/expired based on filing deadline (E4).

        Args:
            claim: Claim dict with token_id, filing_deadline
            escalation_threshold_days: Days before deadline to flag for escalation (default 7)

        Returns:
            ActionableFinding with state and reason.
        """
        token_id = claim.get("token_id", "unknown")
        filing_deadline_str = claim.get("filing_deadline")

        if not filing_deadline_str:
            return ActionableFinding(
                token_id=token_id,
                state=ActionableState.UNKNOWN,
                filing_deadline=None,
                days_until_deadline=None,
                reason="No filing deadline available in claim data",
            )

        try:
            if isinstance(filing_deadline_str, str):
                filing_deadline = datetime.fromisoformat(
                    filing_deadline_str.replace("Z", "+00:00")
                )
            else:
                filing_deadline = filing_deadline_str
        except (ValueError, AttributeError, TypeError):
            return ActionableFinding(
                token_id=token_id,
                state=ActionableState.UNKNOWN,
                filing_deadline=None,
                days_until_deadline=None,
                reason="Filing deadline malformed or unparseable",
            )

        now = datetime.now(timezone.utc)
        days_until = (filing_deadline - now).days

        if days_until < 0:
            reason = f"Filing deadline expired {abs(days_until)} days ago; claim requires audit/remediation"
            return ActionableFinding(
                token_id=token_id,
                state=ActionableState.EXPIRED,
                filing_deadline=filing_deadline,
                days_until_deadline=days_until,
                reason=reason,
            )

        if days_until < escalation_threshold_days:
            reason = f"Filing deadline in {days_until} days; escalation required"
            return ActionableFinding(
                token_id=token_id,
                state=ActionableState.ESCALATION_REQUIRED,
                filing_deadline=filing_deadline,
                days_until_deadline=days_until,
                reason=reason,
            )

        reason = f"Filing deadline in {days_until} days; claim can be remedied"
        return ActionableFinding(
            token_id=token_id,
            state=ActionableState.ACTIONABLE,
            filing_deadline=filing_deadline,
            days_until_deadline=days_until,
            reason=reason,
        )

    def classify_delayed_successor(
        self,
        claim: Dict[str, Any],
    ) -> Optional[str]:
        """Check if claim's last transition was delayed relative to expected (E4).

        Args:
            claim: Claim dict with status, last_status_change_at

        Returns:
            Reason string if delayed, None if on-time or unknown.
        """
        current_status_str = claim.get("status")
        expected_response_by = claim.get("expected_response_by")
        last_change_at = claim.get("last_status_change_at")

        if not all([current_status_str, expected_response_by, last_change_at]):
            return None

        try:
            current_status = ClaimStatus(current_status_str)
            if isinstance(expected_response_by, str):
                expected_response_by = datetime.fromisoformat(
                    expected_response_by.replace("Z", "+00:00")
                )
            if isinstance(last_change_at, str):
                last_change_at = datetime.fromisoformat(last_change_at.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            return None

        if last_change_at > expected_response_by:
            delay_days = (last_change_at - expected_response_by).days
            return f"Claim transitioned to {current_status.value} {delay_days} days after expected deadline"

        return None
