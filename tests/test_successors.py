"""Tests for E4: Expected-Successor Testing.

Tests successor existence checking, missing-claim detection, delayed-claim
detection, and filing-deadline classification.
"""

from datetime import datetime, timedelta, timezone

import pytest

from waterfall_guard.models.claim import ClaimStatus, RelationshipEvidence, RelationshipState, TransactionRelationship
from waterfall_guard.successors import (
    ActionableState,
    MissingSuccessorFinding,
    SuccessorExpectation,
    SuccessorMatcher,
)


class TestSuccessorExpectation:
    """Tests for SuccessorExpectation model."""

    def test_successor_expectation_created(self):
        exp = SuccessorExpectation(
            from_status=ClaimStatus.SUBMITTED,
            to_status=ClaimStatus.ACKNOWLEDGED,
            expected_days=3,
            payer_sla="immediate_ack",
        )
        assert exp.from_status == ClaimStatus.SUBMITTED
        assert exp.to_status == ClaimStatus.ACKNOWLEDGED
        assert exp.expected_days == 3
        assert exp.payer_sla == "immediate_ack"


class TestSuccessorMatcherDefaults:
    """Tests for SuccessorMatcher with default expectations."""

    def test_default_expectations_include_submitted_to_acknowledged(self):
        matcher = SuccessorMatcher()
        assert len(matcher.expectations) >= 3
        # Check SUBMITTED → ACKNOWLEDGED exists
        submitted_exps = matcher._expectations_by_from.get(ClaimStatus.SUBMITTED, [])
        assert len(submitted_exps) > 0
        assert any(e.to_status == ClaimStatus.ACKNOWLEDGED for e in submitted_exps)

    def test_expectations_indexed_by_from_status(self):
        matcher = SuccessorMatcher()
        assert ClaimStatus.SUBMITTED in matcher._expectations_by_from
        assert ClaimStatus.ACKNOWLEDGED in matcher._expectations_by_from


class TestMissingSuccessors:
    """Tests for missing successor detection (E4)."""

    def test_check_missing_successors_with_no_change_in_expected_days(self):
        """Claim stuck in SUBMITTED for 5+ days without ACKNOWLEDGED (E4)."""
        matcher = SuccessorMatcher()
        now = datetime.now(timezone.utc)
        five_days_ago = now - timedelta(days=5)

        claim = {
            "token_id": "tok_claim1",
            "status": "submitted",
            "last_status_change_at": five_days_ago,
            "relationships": [],
        }

        findings = matcher.check_missing_successors(claim)
        assert len(findings) > 0
        assert findings[0].current_status == ClaimStatus.SUBMITTED
        assert findings[0].expected_status == ClaimStatus.ACKNOWLEDGED
        assert findings[0].days_since_transition >= 5

    def test_check_missing_successors_with_accepted_successor_not_flagged(self):
        """Claim with ACCEPTED relationship to successor is not flagged (E4)."""
        matcher = SuccessorMatcher()
        now = datetime.now(timezone.utc)
        five_days_ago = now - timedelta(days=5)

        # Create a relationship showing ACCEPTED transition
        rel = TransactionRelationship(
            from_type="claim",
            from_id="claim1",
            to_type="claim",
            to_id="claim1_ack",
            state=RelationshipState.ACCEPTED,
            evidence=[
                RelationshipEvidence(
                    evidence_type="matching_id",
                    evidence_value="claim_id matches",
                    source="epic_claim_id",
                    confidence_score=0.99,
                )
            ],
        )

        claim = {
            "token_id": "tok_claim1",
            "status": "submitted",
            "last_status_change_at": five_days_ago,
            "relationships": [rel],  # ACCEPTED relationship exists
        }

        findings = matcher.check_missing_successors(claim)
        # Should be empty or contain no missing findings for this successor
        # since ACCEPTED relationship indicates progress
        assert len(findings) == 0 or all(
            f.expected_status != ClaimStatus.ACKNOWLEDGED for f in findings
        )

    def test_check_missing_successors_less_than_threshold_not_flagged(self):
        """Claim stalled for 1 day not flagged (threshold=3 days) (E4)."""
        matcher = SuccessorMatcher()
        now = datetime.now(timezone.utc)
        one_day_ago = now - timedelta(days=1)

        claim = {
            "token_id": "tok_claim1",
            "status": "submitted",
            "last_status_change_at": one_day_ago,
            "relationships": [],
        }

        findings = matcher.check_missing_successors(claim)
        # Should be empty because stall is only 1 day, threshold is 3
        assert len(findings) == 0

    def test_check_missing_successors_with_invalid_status(self):
        """Claim with invalid status string returns empty findings (E4)."""
        matcher = SuccessorMatcher()
        claim = {
            "token_id": "tok_claim1",
            "status": "invalid_status",
            "last_status_change_at": datetime.now(timezone.utc),
            "relationships": [],
        }

        findings = matcher.check_missing_successors(claim)
        assert findings == []

    def test_check_missing_successors_with_missing_fields(self):
        """Claim with missing required fields returns empty findings (E4)."""
        matcher = SuccessorMatcher()
        claim = {"status": "submitted"}  # Missing token_id and last_status_change_at

        findings = matcher.check_missing_successors(claim)
        assert findings == []

    def test_missing_successor_finding_contains_reason(self):
        """MissingSuccessorFinding includes clear reason text (E4)."""
        now = datetime.now(timezone.utc)
        five_days_ago = now - timedelta(days=5)

        matcher = SuccessorMatcher()
        claim = {
            "token_id": "tok_claim1",
            "status": "submitted",
            "last_status_change_at": five_days_ago,
            "relationships": [],
        }

        findings = matcher.check_missing_successors(claim)
        assert len(findings) > 0
        assert findings[0].reason
        assert "submitted" in findings[0].reason.lower()
        assert "5" in findings[0].reason  # Days


class TestActionableClassification:
    """Tests for actionability classification based on filing deadline (E4)."""

    def test_classify_actionable_future_deadline(self):
        """Claim with future deadline classified as ACTIONABLE (E4)."""
        matcher = SuccessorMatcher()
        now = datetime.now(timezone.utc)
        ten_days_future = now + timedelta(days=10)

        claim = {
            "token_id": "tok_claim1",
            "filing_deadline": ten_days_future.isoformat(),
        }

        finding = matcher.classify_actionability(claim)
        assert finding.state == ActionableState.ACTIONABLE
        assert finding.days_until_deadline >= 9  # Allow for timing variation

    def test_classify_escalation_required_near_deadline(self):
        """Claim with deadline < 7 days classified as ESCALATION_REQUIRED (E4)."""
        matcher = SuccessorMatcher()
        now = datetime.now(timezone.utc)
        five_days_future = now + timedelta(days=5)

        claim = {
            "token_id": "tok_claim1",
            "filing_deadline": five_days_future.isoformat(),
        }

        finding = matcher.classify_actionability(claim, escalation_threshold_days=7)
        assert finding.state == ActionableState.ESCALATION_REQUIRED
        assert finding.days_until_deadline >= 4  # Allow for timing variation

    def test_classify_expired_past_deadline(self):
        """Claim with past deadline classified as EXPIRED (E4)."""
        matcher = SuccessorMatcher()
        now = datetime.now(timezone.utc)
        five_days_past = now - timedelta(days=5)

        claim = {
            "token_id": "tok_claim1",
            "filing_deadline": five_days_past.isoformat(),
        }

        finding = matcher.classify_actionability(claim)
        assert finding.state == ActionableState.EXPIRED
        assert finding.days_until_deadline < 0
        assert abs(finding.days_until_deadline) >= 5

    def test_classify_unknown_no_deadline(self):
        """Claim without filing deadline classified as UNKNOWN (E4)."""
        matcher = SuccessorMatcher()
        claim = {"token_id": "tok_claim1"}

        finding = matcher.classify_actionability(claim)
        assert finding.state == ActionableState.UNKNOWN
        assert finding.filing_deadline is None

    def test_classify_unknown_malformed_deadline(self):
        """Claim with malformed deadline classified as UNKNOWN (E4)."""
        matcher = SuccessorMatcher()
        claim = {"token_id": "tok_claim1", "filing_deadline": "not-a-date"}

        finding = matcher.classify_actionability(claim)
        assert finding.state == ActionableState.UNKNOWN

    def test_actionable_finding_reason_includes_days(self):
        """ActionableFinding reason includes days until/past deadline (E4)."""
        matcher = SuccessorMatcher()
        now = datetime.now(timezone.utc)
        ten_days_future = now + timedelta(days=10)

        claim = {
            "token_id": "tok_claim1",
            "filing_deadline": ten_days_future.isoformat(),
        }

        finding = matcher.classify_actionability(claim)
        assert any(str(d) in finding.reason for d in range(9, 11))  # 9 or 10


class TestDelayedSuccessor:
    """Tests for delayed successor detection (E4)."""

    def test_classify_delayed_successor_past_expected_date(self):
        """Claim transitioned after expected_response_by is flagged as delayed (E4)."""
        matcher = SuccessorMatcher()
        now = datetime.now(timezone.utc)
        expected_date = now - timedelta(days=7)
        actual_date = now - timedelta(days=5)

        claim = {
            "status": "acknowledged",
            "expected_response_by": expected_date.isoformat(),
            "last_status_change_at": actual_date.isoformat(),
        }

        reason = matcher.classify_delayed_successor(claim)
        assert reason is not None
        assert "delayed" in reason.lower() or "after" in reason.lower()

    def test_classify_delayed_successor_on_time(self):
        """Claim transitioned before expected_response_by is not flagged (E4)."""
        matcher = SuccessorMatcher()
        now = datetime.now(timezone.utc)
        expected_date = now - timedelta(days=2)
        actual_date = now - timedelta(days=7)

        claim = {
            "status": "acknowledged",
            "expected_response_by": expected_date.isoformat(),
            "last_status_change_at": actual_date.isoformat(),
        }

        reason = matcher.classify_delayed_successor(claim)
        assert reason is None

    def test_classify_delayed_successor_missing_fields(self):
        """Claim with missing fields returns None (E4)."""
        matcher = SuccessorMatcher()
        claim = {"status": "acknowledged"}  # Missing expected_response_by and last_status_change_at

        reason = matcher.classify_delayed_successor(claim)
        assert reason is None


class TestCustomExpectations:
    """Tests for custom successor expectations."""

    def test_custom_expectations_override_defaults(self):
        """SuccessorMatcher accepts custom expectations (E4)."""
        custom_exp = SuccessorExpectation(
            from_status=ClaimStatus.PAID,
            to_status=ClaimStatus.REJECTED,
            expected_days=0,
        )
        matcher = SuccessorMatcher(successor_expectations=[custom_exp])
        assert len(matcher.expectations) == 1
        assert matcher.expectations[0] == custom_exp

    def test_check_missing_successors_with_custom_expectations(self):
        """Missing successor check uses custom expectations (E4)."""
        custom_exp = SuccessorExpectation(
            from_status=ClaimStatus.SUBMITTED,
            to_status=ClaimStatus.PAID,
            expected_days=1,  # Very aggressive
        )
        matcher = SuccessorMatcher(successor_expectations=[custom_exp])

        now = datetime.now(timezone.utc)
        two_days_ago = now - timedelta(days=2)

        claim = {
            "token_id": "tok_claim1",
            "status": "submitted",
            "last_status_change_at": two_days_ago,
            "relationships": [],
        }

        findings = matcher.check_missing_successors(claim)
        assert len(findings) > 0
        assert findings[0].expected_status == ClaimStatus.PAID
        assert findings[0].expected_days == 1
