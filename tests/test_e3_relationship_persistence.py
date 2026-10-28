"""E3 relationship persistence tests.

Verifies that E3 relationships can be persisted to Supabase and that the
database schema supports relationship queries and RLS tenant isolation.
"""

import unittest
from unittest.mock import MagicMock, patch

from waterfall_guard.models.claim import (
    RelationshipState,
    RelationshipEvidence,
    TransactionRelationship,
)
from waterfall_guard.integrations.supabase_writer import SupabaseWriter, WriteResult


class TestWriteRelationships(unittest.TestCase):
    """Test E3 relationship persistence to Supabase."""

    def test_write_relationships_requires_tenant_id(self):
        """E3 relationships must be tenant-isolated."""
        # Create a mock Supabase client
        mock_client = MagicMock()
        mock_table = MagicMock()
        mock_client.table.return_value = mock_table
        mock_table.insert.return_value.execute.return_value = None

        writer = SupabaseWriter(
            url="https://test.supabase.co",
            key="test_key",
            client=mock_client,
        )

        relationships = [
            {
                "from_type": "claim",
                "from_id": "claim_123",
                "to_type": "acknowledgment",
                "to_id": "ack_456",
                "state": "accepted",
                "evidence": [
                    {
                        "evidence_type": "matching_id",
                        "evidence_value": "claim_id matches",
                        "source": "epic_claim_id",
                        "confidence_score": 0.99,
                    }
                ],
            }
        ]

        result = writer.write_relationships(
            tenant_id="tenant_123",
            relationships=relationships,
        )

        # Verify the write succeeded
        self.assertTrue(result.ok)
        self.assertEqual(result.written, 1)

        # Verify tenant_id was added to the row
        call_args = mock_client.table.return_value.insert.call_args
        inserted_rows = call_args[0][0]  # First positional argument
        self.assertEqual(len(inserted_rows), 1)
        self.assertEqual(inserted_rows[0]["tenant_id"], "tenant_123")

    def test_write_relationships_with_all_transaction_types(self):
        """E3 relationships should support all transaction types."""
        mock_client = MagicMock()
        mock_table = MagicMock()
        mock_client.table.return_value = mock_table
        mock_table.insert.return_value.execute.return_value = None

        writer = SupabaseWriter(
            url="https://test.supabase.co",
            key="test_key",
            client=mock_client,
        )

        relationships = [
            {
                "from_type": "encounter",
                "from_id": "enc_001",
                "to_type": "charge",
                "to_id": "chg_001",
                "state": "accepted",
                "evidence": [],
            },
            {
                "from_type": "charge",
                "from_id": "chg_001",
                "to_type": "claim",
                "to_id": "clm_001",
                "state": "accepted",
                "evidence": [],
            },
            {
                "from_type": "claim",
                "from_id": "clm_001",
                "to_type": "acknowledgment",
                "to_id": "ack_001",
                "state": "accepted",
                "evidence": [],
            },
            {
                "from_type": "acknowledgment",
                "from_id": "ack_001",
                "to_type": "remittance",
                "to_id": "rem_001",
                "state": "accepted",
                "evidence": [],
            },
        ]

        result = writer.write_relationships(
            tenant_id="tenant_123",
            relationships=relationships,
        )

        self.assertTrue(result.ok)
        self.assertEqual(result.written, 4)

    def test_write_relationships_with_unresolved_state(self):
        """E3 relationships can be persisted with UNRESOLVED state (for quarantine)."""
        mock_client = MagicMock()
        mock_table = MagicMock()
        mock_client.table.return_value = mock_table
        mock_table.insert.return_value.execute.return_value = None

        writer = SupabaseWriter(
            url="https://test.supabase.co",
            key="test_key",
            client=mock_client,
        )

        relationships = [
            {
                "from_type": "claim",
                "from_id": "clm_001",
                "to_type": "acknowledgment",
                "to_id": "ack_ambiguous",
                "state": "unresolved",  # Quarantined due to ambiguous matching
                "evidence": [
                    {
                        "evidence_type": "ambiguous_match",
                        "evidence_value": "multiple candidates: ack_001, ack_002, ack_003",
                        "source": "date_proximity",
                        "confidence_score": 0.65,
                    }
                ],
            }
        ]

        result = writer.write_relationships(
            tenant_id="tenant_123",
            relationships=relationships,
        )

        self.assertTrue(result.ok)

        # Verify UNRESOLVED state is persisted
        call_args = mock_client.table.return_value.insert.call_args
        inserted_rows = call_args[0][0]
        self.assertEqual(inserted_rows[0]["relationship_state"], "unresolved")

    def test_write_relationships_with_rejected_state(self):
        """E3 relationships can be persisted with REJECTED state (failed matching)."""
        mock_client = MagicMock()
        mock_table = MagicMock()
        mock_client.table.return_value = mock_table
        mock_table.insert.return_value.execute.return_value = None

        writer = SupabaseWriter(
            url="https://test.supabase.co",
            key="test_key",
            client=mock_client,
        )

        relationships = [
            {
                "from_type": "claim",
                "from_id": "clm_001",
                "to_type": "acknowledgment",
                "to_id": "ack_999",
                "state": "rejected",
                "evidence": [
                    {
                        "evidence_type": "conflicting_id",
                        "evidence_value": "claim_id mismatch: expected 001, found 999",
                        "source": "epic_claim_id",
                        "confidence_score": 0.99,
                    }
                ],
            }
        ]

        result = writer.write_relationships(
            tenant_id="tenant_123",
            relationships=relationships,
        )

        self.assertTrue(result.ok)

        # Verify REJECTED state is persisted
        call_args = mock_client.table.return_value.insert.call_args
        inserted_rows = call_args[0][0]
        self.assertEqual(inserted_rows[0]["relationship_state"], "rejected")

    def test_write_relationships_empty_list_no_op(self):
        """Writing empty relationships list is a no-op."""
        mock_client = MagicMock()
        writer = SupabaseWriter(
            url="https://test.supabase.co",
            key="test_key",
            client=mock_client,
        )

        result = writer.write_relationships(
            tenant_id="tenant_123",
            relationships=[],
        )

        # Should succeed with zero rows written
        self.assertTrue(result.ok)
        self.assertEqual(result.written, 0)
        # Should NOT call insert
        mock_client.table.assert_not_called()

    def test_write_relationships_disabled_writer(self):
        """Writing relationships to a disabled writer returns failure."""
        # Create a writer with empty credentials (disabled state)
        writer = SupabaseWriter(url="", key="")
        
        # Verify writer is disabled
        self.assertFalse(writer.enabled)

        result = writer.write_relationships(
            tenant_id="tenant_123",
            relationships=[{"from_type": "claim", "from_id": "clm_001"}],
        )

        self.assertFalse(result.ok)
        self.assertIn("not configured", result.error.lower())

    def test_write_relationships_supabase_error_returns_failure(self):
        """Supabase write errors are caught and returned as WriteResult failures."""
        mock_client = MagicMock()
        mock_table = MagicMock()
        mock_client.table.return_value = mock_table

        # Simulate a write error
        mock_table.insert.return_value.execute.side_effect = Exception("Network error")

        writer = SupabaseWriter(
            url="https://test.supabase.co",
            key="test_key",
            client=mock_client,
        )

        result = writer.write_relationships(
            tenant_id="tenant_123",
            relationships=[
                {
                    "from_type": "claim",
                    "from_id": "clm_001",
                    "to_type": "ack",
                    "to_id": "ack_001",
                    "state": "accepted",
                }
            ],
        )

        self.assertFalse(result.ok)
        self.assertIn("Network error", result.error)

    def test_write_relationships_uses_relationships_table(self):
        """E3 relationships are written to the 'relationships' table by default."""
        mock_client = MagicMock()
        mock_table = MagicMock()
        mock_client.table.return_value = mock_table
        mock_table.insert.return_value.execute.return_value = None

        writer = SupabaseWriter(
            url="https://test.supabase.co",
            key="test_key",
            client=mock_client,
        )

        writer.write_relationships(
            tenant_id="tenant_123",
            relationships=[
                {
                    "from_type": "claim",
                    "from_id": "clm_001",
                    "to_type": "ack",
                    "to_id": "ack_001",
                    "state": "accepted",
                }
            ],
        )

        # Verify the correct table was queried
        mock_client.table.assert_called_with("relationships")

    def test_write_relationships_supports_custom_table_name(self):
        """E3 relationships can be written to a custom table."""
        mock_client = MagicMock()
        mock_table = MagicMock()
        mock_client.table.return_value = mock_table
        mock_table.insert.return_value.execute.return_value = None

        writer = SupabaseWriter(
            url="https://test.supabase.co",
            key="test_key",
            client=mock_client,
        )

        writer.write_relationships(
            tenant_id="tenant_123",
            relationships=[{"from_type": "claim", "from_id": "clm_001"}],
            table_name="custom_relationships",
        )

        # Verify the custom table was used
        mock_client.table.assert_called_with("custom_relationships")


if __name__ == "__main__":
    unittest.main()

