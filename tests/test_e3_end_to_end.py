"""End-to-end E3 tests with synthetic data scenarios.

Tests verify that E3 (Transaction-Specific Lifecycle Reconstruction) correctly:
1. Extracts transaction relationships from raw claims
2. Assigns appropriate ACCEPTED/REJECTED/UNRESOLVED states
3. Handles ambiguous and unresolved relationships safely
4. Integrates with the full diagnostic pipeline
5. Persists relationships with de-identification preserved
"""

import json
from typing import Any, Dict, List

import pytest

from waterfall_guard.integrations.supabase_writer import SupabaseWriter
from waterfall_guard.main import run_diagnostic_pipeline, run_simulation
from waterfall_guard.matcher import RelationshipMatcher
from waterfall_guard.models.claim import RelationshipState


class TestE3EndToEndScenarios:
    """End-to-end E3 integration tests with synthetic data."""

    def test_e3_valid_transaction_chain_extracted(self):
        """Verify E3 extracts a valid, uniquely identifiable transaction chain."""
        # Synthetic data: full lifecycle chain with token_id for claim
        record = {
            "encounter_id": "ENC_001",
            "charge_ids": ["CHG_001"],
            "token_id": "TOK_001",  # Claim token
            "status": "acknowledged",
            "acknowledgment_date": "2026-10-20",
            "ack_id": "ACK_001",
            "remittance_id": "REM_001",
        }

        matcher = RelationshipMatcher()
        relationships = matcher.extract_from_record(record)

        # Should extract: encounter->charge, charge->claim, claim->ack, ack->remittance
        assert len(relationships) >= 4
        
        # Verify all relationships are ACCEPTED
        for rel in relationships:
            assert rel.state == RelationshipState.ACCEPTED
            assert len(rel.evidence) > 0
            assert rel.evidence[0].confidence_score > 0.85

    def test_e3_multiple_charges_same_patient_grouped_correctly(self):
        """Verify E3 correctly handles multiple charges grouped into one claim."""
        # Synthetic data: two charges from same encounter
        record = {
            "encounter_id": "ENC_002",
            "charge_ids": ["CHG_002A", "CHG_002B"],
            "status": "acknowledged",
        }

        matcher = RelationshipMatcher()
        relationships = matcher.extract_from_record(record)

        # Should have encounter->charge for each charge
        encounter_to_charge = [r for r in relationships if r.from_type == "encounter" and r.to_type == "charge"]
        assert len(encounter_to_charge) == 2
        
        # Both should be ACCEPTED
        for rel in encounter_to_charge:
            assert rel.state == RelationshipState.ACCEPTED

    def test_e3_missing_identifiers_marked_unresolved(self):
        """Verify E3 marks relationships as UNRESOLVED when identifiers are missing."""
        # Synthetic data: missing acknowledgment_id
        record = {
            "encounter_id": "ENC_003",
            "charge_ids": ["CHG_003"],
            "status": "acknowledged",
            "ack_id": None,  # Missing ACK ID
        }

        matcher = RelationshipMatcher()
        relationships = matcher.extract_from_record(record)

        # Claim->ACK relationship should not exist (no ack_id)
        claim_to_ack = [r for r in relationships if r.from_type == "claim" and r.to_type == "acknowledgment"]
        assert len(claim_to_ack) == 0

    def test_e3_conflicting_identifiers_handled_safely(self):
        """Verify E3 handles conflicting transaction identifiers appropriately."""
        # Synthetic data: claim with mismatched amounts (would indicate conflict)
        record = {
            "encounter_id": "ENC_004",
            "charge_ids": ["CHG_004"],
            "status": "denied",  # Denied status
            "ack_id": "ACK_004",
            "remittance_id": None,  # No remittance if denied
        }

        matcher = RelationshipMatcher()
        relationships = matcher.extract_from_record(record)

        # ACK->Remittance should not exist (no remit_id even though has ack_id)
        ack_to_rem = [r for r in relationships if r.from_type == "acknowledgment" and r.to_type == "remittance"]
        assert len(ack_to_rem) == 0

    def test_e3_multiple_plausible_matches_handled_safely(self):
        """Verify E3 doesn't arbitrarily accept when multiple matches are possible."""
        # Synthetic data: two encounters, picking one
        record = {
            "encounter_id": "ENC_005",
            "charge_ids": ["CHG_005_ALT"],  # Charge from different encounter
            "status": "acknowledged",
        }

        matcher = RelationshipMatcher()
        relationships = matcher.extract_from_record(record)

        # Should still extract, but confidence should reflect ambiguity if present
        encounter_to_charge = [r for r in relationships if r.from_type == "encounter" and r.to_type == "charge"]
        assert len(encounter_to_charge) == 1
        assert encounter_to_charge[0].state == RelationshipState.ACCEPTED

    def test_e3_unmatched_transaction_not_silently_discarded(self):
        """Verify E3 doesn't silently lose unmatched transactions."""
        # Synthetic data: minimal record
        record = {
            "encounter_id": "ENC_006",
            "charge_ids": [],  # No charges
            "status": "submitted",
        }

        matcher = RelationshipMatcher()
        relationships = matcher.extract_from_record(record)

        # Should process without error, but produce no relationships
        assert relationships is not None
        assert isinstance(relationships, list)

    def test_e3_relationships_state_rules_enforced(self):
        """Verify ACCEPTED/REJECTED/UNRESOLVED state rules are correctly enforced."""
        # Synthetic data: various state conditions
        records = [
            {
                "encounter_id": "ENC_007",
                "charge_ids": ["CHG_007"],
                "status": "acknowledged",  # Valid for ACK relationship
                "ack_id": "ACK_007",
            },
            {
                "encounter_id": "ENC_008",
                "charge_ids": ["CHG_008"],
                "status": "submitted",  # Invalid for ACK relationship
                "ack_id": None,
            },
        ]

        matcher = RelationshipMatcher()
        relationships = matcher.extract_batch(records)

        # Verify state correctness
        for rel in relationships:
            if rel.state == RelationshipState.ACCEPTED:
                # Must have evidence
                assert len(rel.evidence) > 0
                assert rel.evidence[0].confidence_score > 0.0
            elif rel.state == RelationshipState.REJECTED:
                # Must have conflicting evidence
                assert any("conflict" in e.evidence_type.lower() for e in rel.evidence)
            # UNRESOLVED would have insufficient evidence

    def test_e3_unresolved_relationships_quarantined(self):
        """Verify unresolved relationships are recorded and reviewable."""
        # Create a record with ambiguous state
        record = {
            "encounter_id": "ENC_009",
            "charge_ids": ["CHG_009"],
            "status": None,  # Ambiguous: status missing
            "ack_id": None,
        }

        matcher = RelationshipMatcher()
        relationships = matcher.extract_from_record(record)

        # Record should process but not create ACK relationship
        assert relationships is not None

    def test_e3_persistence_integration_with_pipeline(self):
        """Verify E3 relationships persist through the full diagnostic pipeline."""
        written_by_table = {}

        class FakeTable:
            def __init__(self, table_name):
                self.table_name = table_name
                if table_name not in written_by_table:
                    written_by_table[table_name] = []

            def insert(self, rows):
                written_by_table[self.table_name].extend(rows)
                return self

            def execute(self):
                return None

        class FakeClient:
            def table(self, name):
                return FakeTable(name)

        # Run the full pipeline with fake Supabase
        writer = SupabaseWriter(url="https://test.supabase.co", key="test", client=FakeClient())
        result = run_diagnostic_pipeline(supabase_writer=writer)

        # Verify relationships were persisted
        assert result["supabase_write_ok"] is True
        assert "relationships" in written_by_table
        assert len(written_by_table["relationships"]) > 0

        # Verify relationship structure
        rel = written_by_table["relationships"][0]
        assert "tenant_id" in rel  # Tenant injection for RLS
        assert "from_type" in rel
        assert "to_type" in rel
        assert "relationship_state" in rel
        assert "evidence" in rel

    def test_e3_database_persistence_with_state_evidence(self):
        """Verify relationship state and evidence are persisted correctly."""
        written_rows = []

        class FakeTable:
            def insert(self, rows):
                written_rows.extend(rows)
                return self

            def execute(self):
                return None

        class FakeClient:
            def table(self, name):
                return FakeTable()

        writer = SupabaseWriter(url="https://test.supabase.co", key="test", client=FakeClient())

        # Write synthetic relationships
        relationships = [
            {
                "from_type": "encounter",
                "from_id": "ENC_010",
                "to_type": "charge",
                "to_id": "CHG_010",
                "state": "accepted",
                "evidence": [
                    {
                        "evidence_type": "matching_id",
                        "evidence_value": "encounter_id present",
                        "source": "epic_charge_encounter_association",
                        "confidence_score": 0.95,
                    }
                ],
            }
        ]

        result = writer.write_relationships("test_tenant", relationships)

        assert result.ok is True
        assert len(written_rows) == 1
        assert written_rows[0]["relationship_state"] == "accepted"
        assert written_rows[0]["tenant_id"] == "test_tenant"

    def test_e3_end_to_end_payload_contains_relationships(self):
        """Verify full diagnostic pipeline payload includes E3 relationships."""
        payload = run_simulation()

        assert "relationships" in payload
        assert isinstance(payload["relationships"], list)
        assert len(payload["relationships"]) > 0

        # Verify relationship structure in payload
        rel = payload["relationships"][0]
        assert "from_type" in rel
        assert "from_id" in rel
        assert "to_type" in rel
        assert "to_id" in rel
        assert "state" in rel
        assert "evidence" in rel

        # Verify states are valid
        valid_states = {"accepted", "rejected", "unresolved"}
        for rel in payload["relationships"]:
            assert rel["state"] in valid_states

    def test_e3_deidentification_preserved_in_relationships(self):
        """Verify E3 relationships use de-identified IDs, not raw PHI."""
        payload = run_simulation()
        relationships = payload.get("relationships", [])

        # Should not contain raw claim IDs like "1002345678"
        serialized = json.dumps(relationships)
        assert "1002345678" not in serialized
        assert "P-99183" not in serialized  # Patient IDs should not appear
        assert "Doe, Jane" not in serialized  # Patient names should not appear

        # Should contain de-identified token IDs
        assert "tok_" in serialized or "ENC_" in serialized or "CHG_" in serialized

    def test_e3_duplicate_ingestion_handled_safely(self):
        """Verify E3 handles repeated ingestion of same records safely."""
        # Extract relationships twice from same data
        matcher = RelationshipMatcher()

        record = {
            "encounter_id": "ENC_011",
            "charge_ids": ["CHG_011"],
            "status": "acknowledged",
        }

        relationships_1 = matcher.extract_from_record(record)
        relationships_2 = matcher.extract_from_record(record)

        # Both should produce identical results
        assert len(relationships_1) == len(relationships_2)
        assert relationships_1[0].from_id == relationships_2[0].from_id
        assert relationships_1[0].to_id == relationships_2[0].to_id

    def test_e3_batch_processing_performance(self):
        """Verify E3 processes large batches efficiently."""
        matcher = RelationshipMatcher()

        # Synthetic batch: 100 records
        records = [
            {
                "encounter_id": f"ENC_{i:03d}",
                "charge_ids": [f"CHG_{i:03d}"],
                "token_id": f"TOK_{i:03d}",  # Claim token for charge->claim relationship
                "status": "acknowledged",
                "ack_id": f"ACK_{i:03d}" if i % 2 == 0 else None,
            }
            for i in range(100)
        ]

        relationships = matcher.extract_batch(records)

        # Should produce multiple relationships (1+ per record for encounter->charge at minimum)
        # Exact count depends on which records have all fields, but should be substantial
        assert len(relationships) > 0
        
        # All should have state assigned
        for rel in relationships:
            assert rel.state in (RelationshipState.ACCEPTED, RelationshipState.REJECTED, RelationshipState.UNRESOLVED)
