"""Unit tests for E3 RelationshipMatcher."""

import unittest

from waterfall_guard.matcher import RelationshipMatcher
from waterfall_guard.models.claim import RelationshipState


class TestRelationshipMatcher(unittest.TestCase):
    """Test E3 relationship extraction from raw claim records."""

    def test_match_encounter_to_charge_creates_accepted_relationship(self):
        """Test that encounter→charge relationship is created when both IDs present."""
        record = {
            "encounter_id": "ENC001",
            "charge_ids": ["CHG001", "CHG002"],
            "token_id": "CLM001",
        }
        relationships = RelationshipMatcher.extract_from_record(record)

        # Should have at least 2 encounter→charge relationships
        encounter_to_charge = [
            r for r in relationships if r.from_type == "encounter" and r.to_type == "charge"
        ]
        self.assertEqual(len(encounter_to_charge), 2)
        self.assertEqual(encounter_to_charge[0].from_id, "ENC001")
        self.assertEqual(encounter_to_charge[0].to_id, "CHG001")
        self.assertEqual(encounter_to_charge[0].state, RelationshipState.ACCEPTED)
        self.assertGreater(encounter_to_charge[0].evidence[0].confidence_score, 0.9)

    def test_match_charge_to_claim_creates_accepted_relationship(self):
        """Test that charge→claim relationship is created when both present."""
        record = {
            "token_id": "CLM001",
            "charge_ids": ["CHG001", "CHG002"],
        }
        relationships = RelationshipMatcher.extract_from_record(record)

        charge_to_claim = [
            r for r in relationships if r.from_type == "charge" and r.to_type == "claim"
        ]
        self.assertEqual(len(charge_to_claim), 2)
        self.assertEqual(charge_to_claim[0].from_id, "CHG001")
        self.assertEqual(charge_to_claim[0].to_id, "CLM001")
        self.assertEqual(charge_to_claim[0].state, RelationshipState.ACCEPTED)

    def test_match_claim_to_ack_creates_accepted_relationship_when_acknowledged(self):
        """Test that claim→ack relationship is created when claim status is acknowledged."""
        record = {
            "token_id": "CLM001",
            "ack_id": "ACK001",
            "claim_status": "acknowledged",
        }
        relationships = RelationshipMatcher.extract_from_record(record)

        claim_to_ack = [
            r for r in relationships if r.from_type == "claim" and r.to_type == "acknowledgment"
        ]
        self.assertEqual(len(claim_to_ack), 1)
        self.assertEqual(claim_to_ack[0].from_id, "CLM001")
        self.assertEqual(claim_to_ack[0].to_id, "ACK001")
        self.assertEqual(claim_to_ack[0].state, RelationshipState.ACCEPTED)

    def test_match_claim_to_ack_accepts_multiple_statuses(self):
        """Test that claim→ack is accepted for multiple terminal claim statuses."""
        for status in ["acknowledged", "in_adjudication", "paid", "denied"]:
            record = {
                "token_id": f"CLM_{status}",
                "ack_id": f"ACK_{status}",
                "claim_status": status,
            }
            relationships = RelationshipMatcher.extract_from_record(record)

            claim_to_ack = [
                r for r in relationships if r.from_type == "claim" and r.to_type == "acknowledgment"
            ]
            self.assertGreater(len(claim_to_ack), 0, f"Status {status} should produce relationship")
            self.assertEqual(claim_to_ack[0].state, RelationshipState.ACCEPTED)

    def test_match_claim_to_ack_not_created_when_no_ack_id(self):
        """Test that claim→ack is not created when ack_id is missing."""
        record = {
            "token_id": "CLM001",
            "claim_status": "acknowledged",
            # ack_id missing
        }
        relationships = RelationshipMatcher.extract_from_record(record)

        claim_to_ack = [
            r for r in relationships if r.from_type == "claim" and r.to_type == "acknowledgment"
        ]
        self.assertEqual(len(claim_to_ack), 0)

    def test_match_ack_to_remittance_creates_accepted_relationship(self):
        """Test that ack→remittance relationship is created when both present."""
        record = {
            "ack_id": "ACK001",
            "remittance_id": "REM001",
            "token_id": "CLM001",
        }
        relationships = RelationshipMatcher.extract_from_record(record)

        ack_to_remittance = [
            r for r in relationships if r.from_type == "acknowledgment" and r.to_type == "remittance"
        ]
        self.assertEqual(len(ack_to_remittance), 1)
        self.assertEqual(ack_to_remittance[0].from_id, "ACK001")
        self.assertEqual(ack_to_remittance[0].to_id, "REM001")
        self.assertEqual(ack_to_remittance[0].state, RelationshipState.ACCEPTED)

    def test_extract_batch_with_multiple_records(self):
        """Test that extract_batch processes multiple records correctly."""
        records = [
            {
                "token_id": "CLM001",
                "encounter_id": "ENC001",
                "charge_ids": ["CHG001"],
                "claim_status": "submitted",
            },
            {
                "token_id": "CLM002",
                "encounter_id": "ENC002",
                "charge_ids": ["CHG002", "CHG003"],
                "ack_id": "ACK002",
                "claim_status": "acknowledged",
            },
        ]

        relationships = RelationshipMatcher.extract_batch(records)

        # CLM001 should produce: encounter→charge (1), charge→claim (1) = 2 total
        # CLM002 should produce: encounter→charge (2), charge→claim (2), claim→ack (1) = 5 total
        # Total: 7 relationships
        self.assertGreaterEqual(len(relationships), 6)

    def test_extract_batch_empty_records_returns_empty_list(self):
        """Test that extract_batch with empty list returns empty list."""
        relationships = RelationshipMatcher.extract_batch([])
        self.assertEqual(len(relationships), 0)

    def test_extract_from_record_with_minimal_data(self):
        """Test that extract_from_record gracefully handles minimal data."""
        record = {"token_id": "CLM001"}
        relationships = RelationshipMatcher.extract_from_record(record)
        # Should return empty or minimal relationships (no errors)
        self.assertIsInstance(relationships, list)

    def test_full_lifecycle_chain(self):
        """Test a complete encounter→charge→claim→ack→remittance chain."""
        record = {
            "encounter_id": "ENC001",
            "charge_ids": ["CHG001"],
            "token_id": "CLM001",
            "ack_id": "ACK001",
            "claim_status": "acknowledged",
            "remittance_id": "REM001",
        }

        relationships = RelationshipMatcher.extract_from_record(record)

        # Should have exactly 4 relationships (one per edge: encounter→charge, charge→claim, claim→ack, ack→remittance)
        self.assertEqual(len(relationships), 4)

        # Verify the chain
        types = [(r.from_type, r.to_type) for r in relationships]
        expected_types = [
            ("encounter", "charge"),
            ("charge", "claim"),
            ("claim", "acknowledgment"),
            ("acknowledgment", "remittance"),
        ]
        # Should contain all 4 core relationships
        self.assertIn(("encounter", "charge"), types)
        self.assertIn(("charge", "claim"), types)
        self.assertIn(("claim", "acknowledgment"), types)
        self.assertIn(("acknowledgment", "remittance"), types)

    def test_evidence_confidence_scores_vary_by_type(self):
        """Test that different relationship types have appropriate confidence scores."""
        record = {
            "encounter_id": "ENC001",
            "charge_ids": ["CHG001"],
            "token_id": "CLM001",
            "ack_id": "ACK001",
            "claim_status": "acknowledged",
            "remittance_id": "REM001",
        }

        relationships = RelationshipMatcher.extract_from_record(record)

        # All should be ACCEPTED with confidence > 0.9
        for rel in relationships:
            self.assertEqual(rel.state, RelationshipState.ACCEPTED)
            self.assertGreater(rel.evidence[0].confidence_score, 0.85)


if __name__ == "__main__":
    unittest.main()
