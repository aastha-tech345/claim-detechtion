"""Tests for E3: Transaction-Specific Lifecycle Reconstruction.

Tests relationship models, state tracking, evidence collection, and
quarantine of ambiguous matches.
"""

from datetime import datetime

import pytest

from waterfall_guard.models.claim import (
    Claim,
    ClaimStatus,
    RelationshipEvidence,
    RelationshipState,
    TransactionRelationship,
)


class TestRelationshipEvidence:
    """Tests for RelationshipEvidence model (E3)."""

    def test_relationship_evidence_matching_id(self):
        """Create evidence for matching ID (E3)."""
        evidence = RelationshipEvidence(
            evidence_type="matching_id",
            evidence_value="claim_id matches",
            source="epic_claim_id",
            confidence_score=0.99,
        )
        assert evidence.evidence_type == "matching_id"
        assert evidence.confidence_score == 0.99

    def test_relationship_evidence_date_proximity(self):
        """Create evidence for date proximity (E3)."""
        evidence = RelationshipEvidence(
            evidence_type="date_proximity",
            evidence_value="7 days apart",
            source="claim_submitted_date vs ack_receipt_date",
            confidence_score=0.85,
        )
        assert evidence.evidence_type == "date_proximity"

    def test_relationship_evidence_conflicting_id(self):
        """Create evidence for conflicting ID (E3)."""
        evidence = RelationshipEvidence(
            evidence_type="conflicting_id",
            evidence_value="claim_id mismatch",
            source="epic_claim_id field",
            confidence_score=0.0,  # No confidence
        )
        assert evidence.confidence_score == 0.0


class TestTransactionRelationship:
    """Tests for TransactionRelationship model (E3)."""

    def test_transaction_relationship_accepted(self):
        """Create an ACCEPTED relationship (E3)."""
        evidence = RelationshipEvidence(
            evidence_type="matching_id",
            evidence_value="claim_id matches",
            source="epic_claim_id",
            confidence_score=0.99,
        )
        relationship = TransactionRelationship(
            from_type="claim",
            from_id="claim-123",
            to_type="acknowledgment",
            to_id="ack-456",
            state=RelationshipState.ACCEPTED,
            evidence=[evidence],
        )
        assert relationship.state == RelationshipState.ACCEPTED
        assert len(relationship.evidence) == 1

    def test_transaction_relationship_rejected(self):
        """Create a REJECTED relationship (E3)."""
        evidence = RelationshipEvidence(
            evidence_type="conflicting_id",
            evidence_value="claim_id mismatch",
            source="epic_claim_id",
            confidence_score=0.0,
        )
        relationship = TransactionRelationship(
            from_type="claim",
            from_id="claim-123",
            to_type="acknowledgment",
            to_id="ack-789",
            state=RelationshipState.REJECTED,
            evidence=[evidence],
        )
        assert relationship.state == RelationshipState.REJECTED

    def test_transaction_relationship_unresolved(self):
        """Create an UNRESOLVED relationship (E3)."""
        evidence = RelationshipEvidence(
            evidence_type="ambiguous_match",
            evidence_value="multiple candidates, confidence 0.5",
            source="date and amount matching",
            confidence_score=0.5,
        )
        relationship = TransactionRelationship(
            from_type="claim",
            from_id="claim-123",
            to_type="acknowledgment",
            to_id="ack-multiple",
            state=RelationshipState.UNRESOLVED,
            evidence=[evidence],
        )
        assert relationship.state == RelationshipState.UNRESOLVED

    def test_transaction_relationship_encounter_to_charge(self):
        """Create encounter-to-charge relationship (E3)."""
        relationship = TransactionRelationship(
            from_type="encounter",
            from_id="encounter-100",
            to_type="charge",
            to_id="charge-200",
            state=RelationshipState.ACCEPTED,
            evidence=[
                RelationshipEvidence(
                    evidence_type="matching_patient_id",
                    evidence_value="patient_id matches",
                    source="PAT_ID field",
                    confidence_score=1.0,
                )
            ],
        )
        assert relationship.from_type == "encounter"
        assert relationship.to_type == "charge"

    def test_transaction_relationship_charge_to_claim(self):
        """Create charge-to-claim relationship (E3)."""
        relationship = TransactionRelationship(
            from_type="charge",
            from_id="charge-200",
            to_type="claim",
            to_id="claim-123",
            state=RelationshipState.ACCEPTED,
            evidence=[
                RelationshipEvidence(
                    evidence_type="encounter_grouping",
                    evidence_value="grouped by encounter_id",
                    source="billing_engine",
                    confidence_score=0.95,
                )
            ],
        )
        assert relationship.from_type == "charge"
        assert relationship.to_type == "claim"

    def test_transaction_relationship_claim_to_ack(self):
        """Create claim-to-acknowledgment relationship (E3)."""
        relationship = TransactionRelationship(
            from_type="claim",
            from_id="claim-123",
            to_type="acknowledgment",
            to_id="ack-456",
            state=RelationshipState.ACCEPTED,
            evidence=[
                RelationshipEvidence(
                    evidence_type="matching_id",
                    evidence_value="claim_id in payer response",
                    source="X12_claim_id",
                    confidence_score=0.99,
                )
            ],
        )
        assert relationship.from_type == "claim"
        assert relationship.to_type == "acknowledgment"

    def test_transaction_relationship_ack_to_remittance(self):
        """Create acknowledgment-to-remittance relationship (E3)."""
        relationship = TransactionRelationship(
            from_type="acknowledgment",
            from_id="ack-456",
            to_type="remittance",
            to_id="remit-789",
            state=RelationshipState.ACCEPTED,
            evidence=[
                RelationshipEvidence(
                    evidence_type="sequential_flow",
                    evidence_value="remit_date after ack_date",
                    source="timestamp ordering",
                    confidence_score=0.95,
                )
            ],
        )
        assert relationship.from_type == "acknowledgment"
        assert relationship.to_type == "remittance"

    def test_transaction_relationship_created_at_set(self):
        """TransactionRelationship can have created_at set (E3)."""
        now = datetime.utcnow()
        relationship = TransactionRelationship(
            from_type="claim",
            from_id="claim-123",
            to_type="acknowledgment",
            to_id="ack-456",
            state=RelationshipState.ACCEPTED,
            evidence=[],
            created_at=now,
        )
        assert relationship.created_at == now

    def test_transaction_relationship_multiple_evidence(self):
        """TransactionRelationship supports multiple evidence items (E3)."""
        relationship = TransactionRelationship(
            from_type="claim",
            from_id="claim-123",
            to_type="acknowledgment",
            to_id="ack-456",
            state=RelationshipState.ACCEPTED,
            evidence=[
                RelationshipEvidence(
                    evidence_type="matching_id",
                    evidence_value="claim_id matches",
                    source="X12_claim_id",
                    confidence_score=0.99,
                ),
                RelationshipEvidence(
                    evidence_type="date_proximity",
                    evidence_value="3 days apart",
                    source="ack_receipt_date vs claim_submitted_date",
                    confidence_score=0.9,
                ),
            ],
        )
        assert len(relationship.evidence) == 2


class TestClaimWithRelationships:
    """Tests for Claim model with relationships (E3)."""

    def test_claim_with_encounter_id(self):
        """Claim stores encounter_id (E3)."""
        claim = Claim(
            claim_id="claim-123",
            patient_id="pat-456",
            payer="aetna",
            status=ClaimStatus.SUBMITTED,
            amount=1000.0,
            submitted_at=datetime.utcnow(),
            last_status_change_at=datetime.utcnow(),
            encounter_id="encounter-100",
        )
        assert claim.encounter_id == "encounter-100"

    def test_claim_with_charge_ids(self):
        """Claim stores list of charge_ids (E3)."""
        claim = Claim(
            claim_id="claim-123",
            patient_id="pat-456",
            payer="aetna",
            status=ClaimStatus.SUBMITTED,
            amount=1000.0,
            submitted_at=datetime.utcnow(),
            last_status_change_at=datetime.utcnow(),
            charge_ids=["charge-200", "charge-201", "charge-202"],
        )
        assert len(claim.charge_ids) == 3

    def test_claim_with_acknowledgment_id(self):
        """Claim stores acknowledgment_id (E3)."""
        claim = Claim(
            claim_id="claim-123",
            patient_id="pat-456",
            payer="aetna",
            status=ClaimStatus.ACKNOWLEDGED,
            amount=1000.0,
            submitted_at=datetime.utcnow(),
            last_status_change_at=datetime.utcnow(),
            acknowledgment_id="ack-456",
        )
        assert claim.acknowledgment_id == "ack-456"

    def test_claim_with_remittance_id(self):
        """Claim stores remittance_id (E3)."""
        claim = Claim(
            claim_id="claim-123",
            patient_id="pat-456",
            payer="aetna",
            status=ClaimStatus.PAID,
            amount=1000.0,
            submitted_at=datetime.utcnow(),
            last_status_change_at=datetime.utcnow(),
            remittance_id="remit-789",
        )
        assert claim.remittance_id == "remit-789"

    def test_claim_with_relationships(self):
        """Claim stores list of TransactionRelationship (E3)."""
        rel1 = TransactionRelationship(
            from_type="encounter",
            from_id="encounter-100",
            to_type="charge",
            to_id="charge-200",
            state=RelationshipState.ACCEPTED,
            evidence=[],
        )
        rel2 = TransactionRelationship(
            from_type="charge",
            from_id="charge-200",
            to_type="claim",
            to_id="claim-123",
            state=RelationshipState.ACCEPTED,
            evidence=[],
        )
        claim = Claim(
            claim_id="claim-123",
            patient_id="pat-456",
            payer="aetna",
            status=ClaimStatus.SUBMITTED,
            amount=1000.0,
            submitted_at=datetime.utcnow(),
            last_status_change_at=datetime.utcnow(),
            relationships=[rel1, rel2],
        )
        assert len(claim.relationships) == 2

    def test_claim_full_lifecycle_with_all_relationships(self):
        """Claim with all transaction IDs and relationships (E3)."""
        claim = Claim(
            claim_id="claim-123",
            patient_id="pat-456",
            payer="aetna",
            status=ClaimStatus.PAID,
            amount=1000.0,
            submitted_at=datetime.utcnow(),
            last_status_change_at=datetime.utcnow(),
            encounter_id="encounter-100",
            charge_ids=["charge-200", "charge-201"],
            acknowledgment_id="ack-456",
            remittance_id="remit-789",
            relationships=[
                TransactionRelationship(
                    from_type="encounter",
                    from_id="encounter-100",
                    to_type="charge",
                    to_id="charge-200",
                    state=RelationshipState.ACCEPTED,
                    evidence=[],
                ),
                TransactionRelationship(
                    from_type="charge",
                    from_id="charge-200",
                    to_type="claim",
                    to_id="claim-123",
                    state=RelationshipState.ACCEPTED,
                    evidence=[],
                ),
                TransactionRelationship(
                    from_type="claim",
                    from_id="claim-123",
                    to_type="acknowledgment",
                    to_id="ack-456",
                    state=RelationshipState.ACCEPTED,
                    evidence=[],
                ),
                TransactionRelationship(
                    from_type="acknowledgment",
                    from_id="ack-456",
                    to_type="remittance",
                    to_id="remit-789",
                    state=RelationshipState.ACCEPTED,
                    evidence=[],
                ),
            ],
        )
        assert claim.encounter_id == "encounter-100"
        assert len(claim.charge_ids) == 2
        assert claim.acknowledgment_id == "ack-456"
        assert claim.remittance_id == "remit-789"
        assert len(claim.relationships) == 4
        # All relationships should be ACCEPTED
        assert all(r.state == RelationshipState.ACCEPTED for r in claim.relationships)

    def test_claim_with_unresolved_relationship(self):
        """Claim can have UNRESOLVED relationships (E3 quarantine)."""
        claim = Claim(
            claim_id="claim-123",
            patient_id="pat-456",
            payer="aetna",
            status=ClaimStatus.SUBMITTED,
            amount=1000.0,
            submitted_at=datetime.utcnow(),
            last_status_change_at=datetime.utcnow(),
            relationships=[
                TransactionRelationship(
                    from_type="claim",
                    from_id="claim-123",
                    to_type="acknowledgment",
                    to_id="ack-ambiguous",
                    state=RelationshipState.UNRESOLVED,  # Quarantined
                    evidence=[
                        RelationshipEvidence(
                            evidence_type="ambiguous_match",
                            evidence_value="2 candidate ACKs, confidence 0.4",
                            source="date and amount matching",
                            confidence_score=0.4,
                        )
                    ],
                )
            ],
        )
        assert len(claim.relationships) == 1
        assert claim.relationships[0].state == RelationshipState.UNRESOLVED

    def test_claim_with_rejected_relationship(self):
        """Claim can have REJECTED relationships (E3)."""
        claim = Claim(
            claim_id="claim-123",
            patient_id="pat-456",
            payer="aetna",
            status=ClaimStatus.SUBMITTED,
            amount=1000.0,
            submitted_at=datetime.utcnow(),
            last_status_change_at=datetime.utcnow(),
            relationships=[
                TransactionRelationship(
                    from_type="claim",
                    from_id="claim-123",
                    to_type="acknowledgment",
                    to_id="ack-999",
                    state=RelationshipState.REJECTED,
                    evidence=[
                        RelationshipEvidence(
                            evidence_type="conflicting_payer",
                            evidence_value="ACK payer is UnitedHealth, claim payer is Aetna",
                            source="payer_id field",
                            confidence_score=0.0,
                        )
                    ],
                )
            ],
        )
        assert claim.relationships[0].state == RelationshipState.REJECTED
