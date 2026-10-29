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
    """Matches claims to expected downstream successors and classifies actionability (E4).
    
    Validates successor existence by:
    1. Checking for ACCEPTED E3 relationships pointing to expected successor status
    2. Resolving relationship to_id against available claims
    3. Confirming target claim exists and has expected status
    4. Rejecting REJECTED/UNRESOLVED relationships (not confirmed links)
    """

    def __init__(
        self,
        successor_expectations: Optional[List[SuccessorExpectation]] = None,
        all_claims: Optional[List[Dict[str, Any]]] = None,
    ):
        """Initialize with default or custom successor expectations.

        Args:
            successor_expectations: List of SuccessorExpectation rules. If None, uses defaults.
            all_claims: All claims in current batch for resolving relationships. If None, single-claim mode.
        """
        self.expectations = successor_expectations or self._default_expectations()
        self._expectations_by_from = self._index_expectations()
        self.all_claims = all_claims or []
        # Build lookup: token_id → (status, record)
        self._claims_by_token_id = self._build_claims_index()

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

    def _build_claims_index(self) -> Dict[str, tuple]:
        """Build lookup from token_id → (status, record) for resolving relationship targets.
        
        Returns:
            Dict mapping token_id → (status_str, record_dict) for O(1) successor validation.
        """
        index = {}
        for claim in self.all_claims:
            token_id = claim.get("token_id")
            status = claim.get("status") or claim.get("claim_status") or claim.get("waterfall_stage")
            if token_id and status:
                index[token_id] = (status, claim)
        return index

    def _parse_datetime(self, dt_input: Any) -> Optional[datetime]:
        """Parse and normalize datetime to UTC (E4).

        Supports:
        - Timezone-aware ISO-8601 strings (e.g., "2026-10-28T10:30:00Z", "2026-10-28T10:30:00-05:00")
        - Timezone-naive ISO-8601 strings (interpreted as UTC)
        - datetime objects (converted to UTC if aware, assumed UTC if naive)

        Args:
            dt_input: String or datetime object

        Returns:
            Timezone-aware datetime in UTC, or None if parsing fails
        """
        if dt_input is None:
            return None

        try:
            # If already a datetime object
            if isinstance(dt_input, datetime):
                if dt_input.tzinfo is None:
                    # Naive datetime: assume UTC
                    return dt_input.replace(tzinfo=timezone.utc)
                else:
                    # Aware datetime: convert to UTC
                    return dt_input.astimezone(timezone.utc)

            # Parse string
            if isinstance(dt_input, str):
                # Handle Z suffix by replacing with UTC offset
                if dt_input.endswith("Z"):
                    dt_input = dt_input.replace("Z", "+00:00")

                # Use fromisoformat
                dt = datetime.fromisoformat(dt_input)

                # Normalize to UTC
                if dt.tzinfo is None:
                    # Naive: assume UTC
                    return dt.replace(tzinfo=timezone.utc)
                else:
                    # Aware: convert to UTC
                    return dt.astimezone(timezone.utc)

        except (ValueError, AttributeError, TypeError):
            # Parsing failed
            return None

        return None

    def _days_until_deadline(self, deadline: Optional[datetime]) -> Optional[int]:
        """Calculate days from now until deadline (E4).

        Deadline boundary semantics:
        - Deadline 2026-10-31T23:59:59Z: fully expired at 2026-11-01T00:00:00Z
        - 1 day until deadline: deadline is tomorrow
        - 0 days until deadline: deadline is today (use escalation threshold)
        - Negative: deadline past

        Args:
            deadline: Timezone-aware datetime in UTC

        Returns:
            Integer days until deadline (can be negative), or None if deadline is None
        """
        if deadline is None:
            return None

        now = datetime.now(timezone.utc)
        delta = deadline - now
        # Use integer division to get days; fractional days round down
        # This means "6.5 days" becomes 6 days (more urgent)
        return delta.days

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
        current_status_str = claim.get("status") or claim.get("claim_status") or claim.get("waterfall_stage")
        last_change_at_input = claim.get("last_status_change_at") or claim.get("created_date")

        # Require minimum fields
        if not token_id or not current_status_str or not last_change_at_input:
            return []

        # Validate status
        try:
            current_status = ClaimStatus(current_status_str)
        except ValueError:
            return []

        # Parse and normalize datetime
        last_change_at = self._parse_datetime(last_change_at_input)
        if last_change_at is None:
            return []

        # Check if this status has any expected successors
        expectations = self._expectations_by_from.get(current_status, [])
        if not expectations:
            return []

        now = datetime.now(timezone.utc)
        days_since_transition = (now - last_change_at).days

        # For each expected successor, check if present
        for expectation in expectations:
            has_successor = self._has_accepted_successor(claim, expectation.to_status)

            # Only flag as missing if:
            # 1. No accepted successor found, AND
            # 2. Threshold period has elapsed (conservative: only flag overdue claims)
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

    def _has_accepted_successor(
        self, claim: Dict[str, Any], target_status: ClaimStatus
    ) -> bool:
        """Check if claim has an ACCEPTED relationship to a successor with target_status (E4).

        Validates that:
        1. Relationship state is ACCEPTED (not REJECTED/UNRESOLVED)
        2. Relationship target (to_id) resolves to an actual claim
        3. Target claim has the expected successor status

        Args:
            claim: Claim dict with relationships[]
            target_status: Status we're looking for in successor (e.g., ACKNOWLEDGED)

        Returns:
            True only if a valid ACCEPTED relationship to a claim with target_status exists.
        """
        relationships = claim.get("relationships", [])
        if not relationships:
            return False

        for rel in relationships:
            # Extract relationship state
            rel_state = rel.get("state") if isinstance(rel, dict) else getattr(rel, "state", None)

            # Only ACCEPTED relationships count as confirmed links (E4)
            # REJECTED and UNRESOLVED are not treated as confirmed successors
            if rel_state != RelationshipState.ACCEPTED and rel_state != "accepted":
                continue

            # In single-claim mode (all_claims empty), accept presence of ACCEPTED relationship
            # This is conservative: presence of accepted relationship implies some progress
            if not self.all_claims:
                return True

            # In multi-claim mode, resolve target and validate status
            to_id = rel.get("to_id") if isinstance(rel, dict) else getattr(rel, "to_id", None)
            if not to_id:
                continue  # Skip relationships with missing target IDs

            # Look up target claim
            target_info = self._claims_by_token_id.get(to_id)
            if not target_info:
                # Target not in current batch; conservatively accept the relationship
                # (target may be in separate system or pending processing)
                continue

            target_status_str, _ = target_info
            try:
                target_claim_status = ClaimStatus(target_status_str)
                if target_claim_status == target_status:
                    return True  # Found a confirmed successor with expected status
            except ValueError:
                continue  # Target status not recognized; skip this relationship

        return False

    def classify_actionability(
        self,
        claim: Dict[str, Any],
        escalation_threshold_days: int = 7,
    ) -> ActionableFinding:
        """Classify claim as actionable/expired based on filing deadline (E4).

        Classification rules:
        - UNKNOWN: No filing deadline available or unparseable
        - EXPIRED: Filing deadline has passed (days_until < 0)
        - ESCALATION_REQUIRED: Filing deadline imminent (0 <= days_until < escalation_threshold)
        - ACTIONABLE: Filing deadline far enough away (days_until >= escalation_threshold)

        Args:
            claim: Claim dict with token_id, filing_deadline
            escalation_threshold_days: Days before deadline to flag for escalation (default 7)

        Returns:
            ActionableFinding with state and reason.
        """
        token_id = claim.get("token_id", "unknown")
        filing_deadline_input = claim.get("filing_deadline")

        # Parse and normalize deadline
        filing_deadline = self._parse_datetime(filing_deadline_input)
        if filing_deadline is None:
            return ActionableFinding(
                token_id=token_id,
                state=ActionableState.UNKNOWN,
                filing_deadline=None,
                days_until_deadline=None,
                reason="No filing deadline available in claim data" if not filing_deadline_input else "Filing deadline malformed or unparseable",
            )

        # Calculate days until deadline (now in UTC, deadline in UTC)
        days_until = self._days_until_deadline(filing_deadline)
        if days_until is None:
            return ActionableFinding(
                token_id=token_id,
                state=ActionableState.UNKNOWN,
                filing_deadline=filing_deadline,
                days_until_deadline=None,
                reason="Could not calculate days until filing deadline",
            )

        # Classify based on deadline boundary
        if days_until < 0:
            # Deadline has passed
            reason = f"Filing deadline expired {abs(days_until)} days ago; claim requires audit/remediation"
            return ActionableFinding(
                token_id=token_id,
                state=ActionableState.EXPIRED,
                filing_deadline=filing_deadline,
                days_until_deadline=days_until,
                reason=reason,
            )

        if days_until < escalation_threshold_days:
            # Deadline imminent (today through N days away)
            reason = f"Filing deadline in {days_until} days; escalation required"
            return ActionableFinding(
                token_id=token_id,
                state=ActionableState.ESCALATION_REQUIRED,
                filing_deadline=filing_deadline,
                days_until_deadline=days_until,
                reason=reason,
            )

        # Deadline far enough away
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
            claim: Claim dict with status, expected_response_by, last_status_change_at

        Returns:
            Reason string if delayed (transition happened after expected date), None if on-time or unknown.
        """
        current_status_str = claim.get("status") or claim.get("claim_status")
        expected_response_by_input = claim.get("expected_response_by")
        last_change_at_input = claim.get("last_status_change_at") or claim.get("created_date")

        # All three fields required
        if not all([current_status_str, expected_response_by_input, last_change_at_input]):
            return None

        # Validate status
        try:
            current_status = ClaimStatus(current_status_str)
        except ValueError:
            return None

        # Parse both datetimes
        expected_response_by = self._parse_datetime(expected_response_by_input)
        last_change_at = self._parse_datetime(last_change_at_input)

        if expected_response_by is None or last_change_at is None:
            return None

        # Check if transition was late
        if last_change_at > expected_response_by:
            delay_delta = last_change_at - expected_response_by
            delay_days = delay_delta.days
            return f"Claim transitioned to {current_status.value} {delay_days} days after expected deadline"

        return None
