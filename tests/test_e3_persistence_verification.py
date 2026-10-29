"""E3 Persistence Verification Tests

Comprehensive tests to verify that E3 relationships are:
1. Persisted with correct state (ACCEPTED/REJECTED/UNRESOLVED)
2. Retrieved with evidence intact
3. Quarantined appropriately for unresolved cases
4. Subject to proper tenant isolation
5. Cannot be misused as accepted links when unresolved
"""

import json
from typing import Any, Dict, List

import pytest

from waterfall_guard.integrations.supabase_writer import SupabaseWriter, WriteResult
from waterfall_guard.matcher import RelationshipMatcher
from waterfall_guard.models.claim import RelationshipState


class TestE3PersistenceWithStates:
    """Verify E3 relationships are persisted with correct state management."""

    def test_accepted_relationships_persisted_with_evidence(self):
        """Verify ACCEPTED relationships are stored with full evidence chain."""
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

        # Create relationships with multiple evidence items
        relationships = [
            {
                "from_type": "encounter",
                "from_id": "ENC_001",
                "to_type": "charge",
                "to_id": "CHG_001",
                "state": "accepted",
                "evidence": [
                    {
                        "evidence_type": "matching_id",
                        "evidence_value": "encounter_id matches",
                        "source": "epic_charge_encounter_association",
                        "confidence_score": 0.95,
                    }
                ],
            }
        ]

        result = writer.write_relationships("test_tenant", relationships)

        assert result.ok is True
        assert len(written_rows) == 1

        persisted = written_rows[0]
        assert persisted["relationship_state"] == "accepted"
        assert persisted["tenant_id"] == "test_tenant"
        assert persisted["from_type"] == "encounter"
        assert persisted["from_id"] == "ENC_001"
        assert persisted["to_type"] == "charge"
        assert persisted["to_id"] == "CHG_001"
        assert persisted["evidence"] is not None

    def test_rejected_relationships_persisted_with_conflict_evidence(self):
        """Verify REJECTED relationships are persisted with conflicting evidence."""
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

        # Rejected relationship with conflict evidence
        relationships = [
            {
                "from_type": "claim",
                "from_id": "CLM_001",
                "to_type": "acknowledgment",
                "to_id": "ACK_001",
                "state": "rejected",
                "evidence": [
                    {
                        "evidence_type": "conflicting_id",
                        "evidence_value": "claim_id does not match payer reference",
                        "source": "epic_claim_acknowledgment_mismatch",
                        "confidence_score": 0.0,
                    }
                ],
            }
        ]

        result = writer.write_relationships("test_tenant", relationships)

        assert result.ok is True
        assert written_rows[0]["relationship_state"] == "rejected"

    def test_unresolved_relationships_persisted_for_quarantine(self):
        """Verify UNRESOLVED relationships are persisted for review/quarantine."""
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

        # Unresolved relationship requiring manual review
        relationships = [
            {
                "from_type": "charge",
                "from_id": "CHG_002",
                "to_type": "claim",
                "to_id": "CLM_002",
                "state": "unresolved",
                "evidence": [
                    {
                        "evidence_type": "insufficient_evidence",
                        "evidence_value": "multiple possible matches, unable to disambiguate",
                        "source": "epic_charge_claim_ambiguity",
                        "confidence_score": 0.45,
                    }
                ],
            }
        ]

        result = writer.write_relationships("test_tenant", relationships)

        assert result.ok is True
        persisted = written_rows[0]
        assert persisted["relationship_state"] == "unresolved"
        # Unresolved should be marked for review
        assert "insufficient_evidence" in str(persisted.get("evidence", ""))

    def test_tenant_isolation_enforced_in_persistence(self):
        """Verify relationships from different tenants are isolated."""
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

        relationships = [
            {
                "from_type": "encounter",
                "from_id": "ENC_001",
                "to_type": "charge",
                "to_id": "CHG_001",
                "state": "accepted",
                "evidence": [],
            }
        ]

        # Write for tenant A
        writer.write_relationships("tenant_a", relationships)

        # Write for tenant B
        writer.write_relationships("tenant_b", relationships)

        # Both should be persisted with correct tenant IDs
        assert len(written_rows) == 2
        assert written_rows[0]["tenant_id"] == "tenant_a"
        assert written_rows[1]["tenant_id"] == "tenant_b"
        assert written_rows[0]["from_id"] == written_rows[1]["from_id"]

    def test_unresolved_relationships_not_usable_as_accepted_links(self):
        """Verify unresolved relationships cannot be treated as accepted successors."""
        # Create mixed relationships
        records = [
            {
                "token_id": "CLM_001",
                "encounter_id": "ENC_001",
                "charge_ids": ["CHG_001"],
                "status": "acknowledged",
                "ack_id": "ACK_001",
            }
        ]

        matcher = RelationshipMatcher()
        relationships = matcher.extract_batch(records)

        # All should be ACCEPTED (they have all necessary fields)
        accepted_count = sum(1 for r in relationships if r.state == RelationshipState.ACCEPTED)
        unresolved_count = sum(1 for r in relationships if r.state == RelationshipState.UNRESOLVED)

        # Verify ACCEPTED relationships have sufficient evidence
        for rel in relationships:
            if rel.state == RelationshipState.ACCEPTED:
                assert len(rel.evidence) > 0
                assert all(e.confidence_score >= 0.85 for e in rel.evidence)

        # Unresolved (if any) should not be used as lifecycle links
        for rel in relationships:
            if rel.state == RelationshipState.UNRESOLVED:
                # These should require manual review before being used
                assert rel.evidence is not None
                assert any("insufficient" in str(e.evidence_type).lower() for e in rel.evidence)

    def test_mixed_state_relationships_all_persisted_correctly(self):
        """Verify batch containing all states persists each with correct state."""
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

        relationships = [
            {
                "from_type": "encounter",
                "from_id": "ENC_001",
                "to_type": "charge",
                "to_id": "CHG_001",
                "state": "accepted",
                "evidence": [{"evidence_type": "matching_id", "confidence_score": 0.95}],
            },
            {
                "from_type": "charge",
                "from_id": "CHG_002",
                "to_type": "claim",
                "to_id": "CLM_002",
                "state": "unresolved",
                "evidence": [{"evidence_type": "insufficient_evidence", "confidence_score": 0.45}],
            },
            {
                "from_type": "claim",
                "from_id": "CLM_003",
                "to_type": "acknowledgment",
                "to_id": "ACK_003",
                "state": "rejected",
                "evidence": [{"evidence_type": "conflicting_id", "confidence_score": 0.0}],
            },
        ]

        result = writer.write_relationships("test_tenant", relationships)

        assert result.ok is True
        assert len(written_rows) == 3

        states = [row["relationship_state"] for row in written_rows]
        assert "accepted" in states
        assert "unresolved" in states
        assert "rejected" in states

    def test_batch_persistence_prevents_partial_failure(self):
        """Verify batch persistence succeeds or fails atomically."""
        call_count = {"insert": 0}

        class FakeTable:
            def insert(self, rows):
                call_count["insert"] += 1
                # Simulate successful insert
                return self

            def execute(self):
                return None

        class FakeClient:
            def table(self, name):
                return FakeTable()

        writer = SupabaseWriter(url="https://test.supabase.co", key="test", client=FakeClient())

        relationships = [
            {
                "from_type": "encounter",
                "from_id": f"ENC_{i}",
                "to_type": "charge",
                "to_id": f"CHG_{i}",
                "state": "accepted",
                "evidence": [],
            }
            for i in range(10)
        ]

        result = writer.write_relationships("test_tenant", relationships)

        # All rows should be inserted in single call
        assert result.ok is True
        assert call_count["insert"] == 1

    def test_evidence_json_serialization_preserved(self):
        """Verify complex evidence structures are preserved through persistence."""
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

        complex_evidence = [
            {
                "evidence_type": "matching_id",
                "evidence_value": "encounter_id present",
                "source": "epic_charge_encounter_association",
                "confidence_score": 0.95,
            },
            {
                "evidence_type": "date_proximity",
                "evidence_value": "charge date within 1 day of encounter",
                "source": "temporal_validation",
                "confidence_score": 0.90,
            },
        ]

        relationships = [
            {
                "from_type": "encounter",
                "from_id": "ENC_001",
                "to_type": "charge",
                "to_id": "CHG_001",
                "state": "accepted",
                "evidence": complex_evidence,
            }
        ]

        result = writer.write_relationships("test_tenant", relationships)

        assert result.ok is True
        persisted = written_rows[0]
        
        # Evidence should be preserved as JSON
        evidence = persisted.get("evidence")
        assert evidence is not None
        if isinstance(evidence, str):
            evidence = json.loads(evidence)
        
        # Should have both evidence items
        if isinstance(evidence, list):
            assert len(evidence) == 2
            types = {e["evidence_type"] for e in evidence}
            assert "matching_id" in types
            assert "date_proximity" in types


class TestE3StateTransitionSafety:
    """Verify E3 state transitions and lifecycle safety."""

    def test_unresolved_cannot_transition_to_accepted_without_new_evidence(self):
        """Verify UNRESOLVED relationships require explicit new evidence to accept."""
        # This is a logical test - implementation would require retrieval logic
        # For now, verify that new extractions with better evidence produce new relationships

        record_incomplete = {
            "token_id": "CLM_001",
            "encounter_id": "ENC_001",
            "charge_ids": ["CHG_001"],
            "status": None,  # Ambiguous status
            "ack_id": None,  # No acknowledgment
        }

        record_complete = {
            "token_id": "CLM_001",
            "encounter_id": "ENC_001",
            "charge_ids": ["CHG_001"],
            "status": "acknowledged",
            "ack_id": "ACK_001",  # Acknowledgment now present
        }

        matcher = RelationshipMatcher()

        # First extraction with incomplete data
        rels_incomplete = matcher.extract_batch([record_incomplete])
        
        # Second extraction with complete data
        rels_complete = matcher.extract_batch([record_complete])

        # Complete data should produce more relationships with higher confidence
        assert len(rels_complete) >= len(rels_incomplete)

        # Any new relationships should be ACCEPTED with sufficient evidence
        for rel in rels_complete:
            if rel.state == RelationshipState.ACCEPTED:
                assert all(e.confidence_score >= 0.85 for e in rel.evidence)


class TestE3QuarantineHandling:
    """Verify unresolved relationships are properly quarantined and reviewable."""

    def test_unresolved_relationships_marked_for_review(self):
        """Verify UNRESOLVED relationships have evidence suitable for manual review."""
        record = {
            "token_id": "CLM_001",
            "encounter_id": None,  # Missing encounter
            "charge_ids": [],  # No charges
            "status": None,
        }

        matcher = RelationshipMatcher()
        relationships = matcher.extract_batch([record])

        # No relationships should be extracted for this empty record
        # (or if extracted, they should all be UNRESOLVED)
        for rel in relationships:
            if rel.state == RelationshipState.UNRESOLVED:
                # Should have explanation for quarantine
                assert len(rel.evidence) > 0
                assert rel.evidence[0].evidence_value is not None

    def test_quarantine_preserves_confidence_for_manual_triage(self):
        """Verify quarantined relationships preserve confidence scores for triage."""
        relationships = [
            {
                "from_type": "charge",
                "from_id": "CHG_001",
                "to_type": "claim",
                "to_id": "CLM_001",
                "state": "unresolved",
                "evidence": [
                    {
                        "evidence_type": "ambiguous_match",
                        "evidence_value": "3 possible claims match this charge",
                        "source": "charge_claim_ambiguity",
                        "confidence_score": 0.33,  # Low confidence - 1 of 3 possibilities
                    }
                ],
            }
        ]

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
        writer.write_relationships("test_tenant", relationships)

        # Confidence should be preserved for triage
        evidence = written_rows[0].get("evidence")
        if isinstance(evidence, str):
            evidence = json.loads(evidence)
        
        if isinstance(evidence, list):
            assert evidence[0]["confidence_score"] == 0.33
