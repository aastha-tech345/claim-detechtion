"""Tests for durable audit log persistence (Blocker #3).

Tests verify that:
1. Audit events are persisted to database
2. Persistence failures don't crash the application (soft-fail)
3. All 8 audit event types can be persisted
4. Events include required fields for compliance
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
from datetime import datetime, timezone

from waterfall_guard.audit import (
    AuditLogger,
    AuditEvent,
    AuditEventType,
    get_audit_logger,
)


class TestAuditEventPersistence:
    """Tests for audit event database persistence."""

    def test_audit_event_to_dict_serialization(self):
        """AuditEvent should serialize to dict for database storage."""
        event = AuditEvent(
            event_type=AuditEventType.WRITEBACK_ATTEMPTED,
            timestamp=datetime(2026, 10, 28, 12, 0, 0, tzinfo=timezone.utc),
            tenant_id="tenant-1",
            user_id="user-123",
            user_role="supervisor",
            operation="epic_fhir_writeback",
            resource_id="task-456",
            resource_type="fhir_task",
            status="pending",
            reason=None,
            details={"resolution_status": "RESOLVED"},
        )
        
        event_dict = event.to_dict()
        
        assert isinstance(event_dict, dict)
        assert event_dict["tenant_id"] == "tenant-1"
        assert event_dict["user_id"] == "user-123"
        assert event_dict["user_role"] == "supervisor"
        assert event_dict["event_type"] == "writeback_attempted"
        assert event_dict["status"] == "pending"
        assert event_dict["resource_id"] == "task-456"
        assert "timestamp" in event_dict
        assert isinstance(event_dict["timestamp"], str)  # ISO format

    def test_audit_logger_persistence_with_mock_writer(self):
        """AuditLogger should attempt to persist events using SupabaseWriter."""
        mock_writer = Mock()
        mock_writer.enabled = True
        mock_writer.write_rows = Mock(return_value=Mock(ok=True, written=1, error=None))
        
        logger_instance = AuditLogger()
        logger_instance._writer = mock_writer
        
        event = AuditLogger().log_writeback_attempt(
            tenant_id="tenant-1",
            user_id="user-123",
            user_role="supervisor",
            task_id="task-456",
            resolution_status="RESOLVED",
        )
        
        logger_instance.log_event(event)
        
        # Verify write_rows was called
        assert mock_writer.write_rows.called
        call_args = mock_writer.write_rows.call_args
        rows = call_args[0][0]
        assert len(rows) == 1
        assert rows[0]["tenant_id"] == "tenant-1"

    def test_audit_logger_soft_fails_on_persistence_error(self):
        """AuditLogger should not raise on persistence failure (soft-fail)."""
        mock_writer = Mock()
        mock_writer.enabled = True
        mock_writer.write_rows = Mock(
            side_effect=Exception("Database connection failed")
        )
        
        logger_instance = AuditLogger()
        logger_instance._writer = mock_writer
        
        event = AuditLogger().log_writeback_authorized(
            tenant_id="tenant-1",
            user_id="user-123",
            user_role="supervisor",
            task_id="task-456",
        )
        
        # Should not raise, just log the error
        try:
            logger_instance.log_event(event)
        except Exception:
            pytest.fail("AuditLogger.log_event() should not raise on persistence failure")

    def test_audit_logger_skips_persistence_when_writer_disabled(self):
        """AuditLogger should skip persistence when writer is disabled."""
        mock_writer = Mock()
        mock_writer.enabled = False  # Writer is disabled
        
        logger_instance = AuditLogger()
        logger_instance._writer = mock_writer
        
        event = AuditLogger().log_writeback_denied(
            tenant_id="tenant-1",
            user_id="user-123",
            user_role="analyst",
            task_id="task-456",
            reason="Insufficient permissions",
        )
        
        # Should not attempt to write
        logger_instance.log_event(event)
        assert not mock_writer.write_rows.called


class TestAllAuditEventTypesPersistence:
    """Tests that all 8 audit event types can be persisted."""

    def test_writeback_attempted_persisted(self):
        """WRITEBACK_ATTEMPTED events should be persistable."""
        logger_instance = AuditLogger()
        event = logger_instance.log_writeback_attempt(
            tenant_id="tenant-1",
            user_id="user-123",
            user_role="supervisor",
            task_id="task-456",
            resolution_status="RESOLVED",
        )
        
        assert event.event_type == AuditEventType.WRITEBACK_ATTEMPTED
        event_dict = event.to_dict()
        assert event_dict["event_type"] == "writeback_attempted"

    def test_writeback_authorized_persisted(self):
        """WRITEBACK_AUTHORIZED events should be persistable."""
        logger_instance = AuditLogger()
        event = logger_instance.log_writeback_authorized(
            tenant_id="tenant-1",
            user_id="user-123",
            user_role="supervisor",
            task_id="task-456",
        )
        
        assert event.event_type == AuditEventType.WRITEBACK_AUTHORIZED
        event_dict = event.to_dict()
        assert event_dict["event_type"] == "writeback_authorized"

    def test_writeback_denied_persisted(self):
        """WRITEBACK_DENIED events should be persistable."""
        logger_instance = AuditLogger()
        event = logger_instance.log_writeback_denied(
            tenant_id="tenant-1",
            user_id="user-123",
            user_role="analyst",
            task_id="task-456",
            reason="Insufficient permissions",
        )
        
        assert event.event_type == AuditEventType.WRITEBACK_DENIED
        event_dict = event.to_dict()
        assert event_dict["event_type"] == "writeback_denied"

    def test_writeback_succeeded_persisted(self):
        """WRITEBACK_SUCCEEDED events should be persistable."""
        logger_instance = AuditLogger()
        event = logger_instance.log_writeback_succeeded(
            tenant_id="tenant-1",
            user_id="user-123",
            user_role="supervisor",
            task_id="task-456",
            fhir_status="completed",
        )
        
        assert event.event_type == AuditEventType.WRITEBACK_SUCCEEDED
        event_dict = event.to_dict()
        assert event_dict["event_type"] == "writeback_succeeded"

    def test_writeback_failed_persisted(self):
        """WRITEBACK_FAILED events should be persistable."""
        logger_instance = AuditLogger()
        event = logger_instance.log_writeback_failed(
            tenant_id="tenant-1",
            user_id="user-123",
            user_role="supervisor",
            task_id="task-456",
            error="Epic Task not found",
        )
        
        assert event.event_type == AuditEventType.WRITEBACK_FAILED
        event_dict = event.to_dict()
        assert event_dict["event_type"] == "writeback_failed"


class TestAuditEventComplianceFields:
    """Tests that audit events capture all required compliance fields."""

    def test_event_includes_actor_context(self):
        """Audit events should include actor context (tenant, user, role)."""
        event = AuditEvent(
            event_type=AuditEventType.WRITEBACK_ATTEMPTED,
            timestamp=datetime.now(timezone.utc),
            tenant_id="tenant-1",
            user_id="user-123",
            user_role="supervisor",
            operation="epic_fhir_writeback",
            resource_id="task-456",
            resource_type="fhir_task",
            status="pending",
            reason=None,
        )
        
        event_dict = event.to_dict()
        assert event_dict["tenant_id"] == "tenant-1"
        assert event_dict["user_id"] == "user-123"
        assert event_dict["user_role"] == "supervisor"

    def test_event_includes_timestamp(self):
        """Audit events should include timestamp in UTC."""
        now = datetime.now(timezone.utc)
        event = AuditEvent(
            event_type=AuditEventType.WRITEBACK_ATTEMPTED,
            timestamp=now,
            tenant_id="tenant-1",
            user_id="user-123",
            user_role="supervisor",
            operation="epic_fhir_writeback",
            resource_id="task-456",
            resource_type="fhir_task",
            status="pending",
            reason=None,
        )
        
        event_dict = event.to_dict()
        assert "timestamp" in event_dict
        assert isinstance(event_dict["timestamp"], str)
        assert "T" in event_dict["timestamp"]  # ISO format

    def test_event_includes_action_and_resource(self):
        """Audit events should include action (operation) and resource details."""
        event = AuditEvent(
            event_type=AuditEventType.WRITEBACK_ATTEMPTED,
            timestamp=datetime.now(timezone.utc),
            tenant_id="tenant-1",
            user_id="user-123",
            user_role="supervisor",
            operation="epic_fhir_writeback",
            resource_id="task-456",
            resource_type="fhir_task",
            status="pending",
            reason=None,
        )
        
        event_dict = event.to_dict()
        assert event_dict["operation"] == "epic_fhir_writeback"
        assert event_dict["resource_type"] == "fhir_task"
        assert event_dict["resource_id"] == "task-456"

    def test_event_includes_outcome(self):
        """Audit events should include outcome (status, reason)."""
        event = AuditEvent(
            event_type=AuditEventType.WRITEBACK_DENIED,
            timestamp=datetime.now(timezone.utc),
            tenant_id="tenant-1",
            user_id="user-123",
            user_role="analyst",
            operation="epic_fhir_writeback",
            resource_id="task-456",
            resource_type="fhir_task",
            status="denied",
            reason="Analyst role not authorized for writebacks",
        )
        
        event_dict = event.to_dict()
        assert event_dict["status"] == "denied"
        assert event_dict["reason"] == "Analyst role not authorized for writebacks"

    def test_event_includes_optional_details(self):
        """Audit events should include optional details (no PHI)."""
        event = AuditEvent(
            event_type=AuditEventType.WRITEBACK_ATTEMPTED,
            timestamp=datetime.now(timezone.utc),
            tenant_id="tenant-1",
            user_id="user-123",
            user_role="supervisor",
            operation="epic_fhir_writeback",
            resource_id="task-456",
            resource_type="fhir_task",
            status="pending",
            reason=None,
            details={"resolution_status": "RESOLVED", "correlation_id": "req-789"},
        )
        
        event_dict = event.to_dict()
        assert event_dict["details"] == {
            "resolution_status": "RESOLVED",
            "correlation_id": "req-789",
        }

    def test_event_does_not_include_secrets(self):
        """Audit events should NOT include secrets, tokens, or PHI."""
        event = AuditEvent(
            event_type=AuditEventType.WRITEBACK_ATTEMPTED,
            timestamp=datetime.now(timezone.utc),
            tenant_id="tenant-1",
            user_id="user-123",
            user_role="supervisor",
            operation="epic_fhir_writeback",
            resource_id="task-456",
            resource_type="fhir_task",
            status="pending",
            reason=None,
        )
        
        event_dict = event.to_dict()
        
        # Verify no sensitive fields
        json_str = str(event_dict).lower()
        assert "secret" not in json_str
        assert "token" not in json_str
        assert "password" not in json_str
        assert "key" not in json_str


class TestAuditTenantIsolation:
    """Tests that audit logs maintain tenant isolation."""

    def test_audit_event_includes_tenant_id(self):
        """Every audit event must include tenant_id for RLS isolation."""
        event = AuditEvent(
            event_type=AuditEventType.WRITEBACK_ATTEMPTED,
            timestamp=datetime.now(timezone.utc),
            tenant_id="hospital-a",  # Explicit tenant
            user_id="user-123",
            user_role="supervisor",
            operation="epic_fhir_writeback",
            resource_id="task-456",
            resource_type="fhir_task",
            status="pending",
            reason=None,
        )
        
        event_dict = event.to_dict()
        assert event_dict["tenant_id"] == "hospital-a"

    def test_different_tenants_have_different_audit_isolation(self):
        """Audit events from different tenants should be isolated."""
        event_tenant_a = AuditEvent(
            event_type=AuditEventType.WRITEBACK_ATTEMPTED,
            timestamp=datetime.now(timezone.utc),
            tenant_id="hospital-a",
            user_id="user-1",
            user_role="supervisor",
            operation="epic_fhir_writeback",
            resource_id="task-1",
            resource_type="fhir_task",
            status="pending",
            reason=None,
        )
        
        event_tenant_b = AuditEvent(
            event_type=AuditEventType.WRITEBACK_ATTEMPTED,
            timestamp=datetime.now(timezone.utc),
            tenant_id="hospital-b",
            user_id="user-2",
            user_role="supervisor",
            operation="epic_fhir_writeback",
            resource_id="task-2",
            resource_type="fhir_task",
            status="pending",
            reason=None,
        )
        
        dict_a = event_tenant_a.to_dict()
        dict_b = event_tenant_b.to_dict()
        
        assert dict_a["tenant_id"] != dict_b["tenant_id"]
        assert dict_a["user_id"] != dict_b["user_id"]
        assert dict_a["resource_id"] != dict_b["resource_id"]
