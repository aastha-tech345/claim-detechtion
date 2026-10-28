"""Tests for E5: Read-Only Analytical Architecture enforcement.

Tests authorization checks, audit logging, and read-only boundaries.
"""

import pytest

from waterfall_guard.audit import (
    AuditEventType,
    AuditLogger,
    get_audit_logger,
)
from waterfall_guard.readonly import (
    AuthorizationError,
    ReadOnlyGate,
    UserRole,
    is_authorized_role,
)


class TestUserRole:
    """Tests for UserRole enum."""

    def test_user_role_analyst(self):
        assert UserRole.ANALYST.value == "analyst"

    def test_user_role_supervisor(self):
        assert UserRole.SUPERVISOR.value == "supervisor"

    def test_user_role_admin(self):
        assert UserRole.ADMIN.value == "admin"


class TestReadOnlyGateAuthorization:
    """Tests for ReadOnlyGate authorization (E5)."""

    def test_authorize_writeback_supervisor_allowed(self):
        """Supervisor role is authorized for writebacks (E5)."""
        # Should not raise
        ReadOnlyGate.authorize_writeback(
            user_id="user-123",
            user_role="supervisor",
            tenant_id="tenant-1",
        )

    def test_authorize_writeback_admin_allowed(self):
        """Admin role is authorized for writebacks (E5)."""
        # Should not raise
        ReadOnlyGate.authorize_writeback(
            user_id="user-456",
            user_role="admin",
            tenant_id="tenant-1",
        )

    def test_authorize_writeback_analyst_denied(self):
        """Analyst role is NOT authorized for writebacks (E5)."""
        with pytest.raises(AuthorizationError) as exc_info:
            ReadOnlyGate.authorize_writeback(
                user_id="user-789",
                user_role="analyst",
                tenant_id="tenant-1",
            )
        assert "analyst" in str(exc_info.value).lower()
        assert "not authorized" in str(exc_info.value).lower()

    def test_authorize_writeback_no_user_denied(self):
        """No user context denied writeback (E5)."""
        with pytest.raises(AuthorizationError) as exc_info:
            ReadOnlyGate.authorize_writeback(
                user_id=None,
                user_role="supervisor",
                tenant_id="tenant-1",
            )
        assert "no user context" in str(exc_info.value).lower()

    def test_authorize_writeback_no_role_denied(self):
        """No user role denies writeback (E5)."""
        with pytest.raises(AuthorizationError) as exc_info:
            ReadOnlyGate.authorize_writeback(
                user_id="user-123",
                user_role=None,
                tenant_id="tenant-1",
            )
        assert "no user role" in str(exc_info.value).lower()

    def test_authorize_writeback_invalid_role_denied(self):
        """Invalid role string denies writeback (E5)."""
        with pytest.raises(AuthorizationError) as exc_info:
            ReadOnlyGate.authorize_writeback(
                user_id="user-123",
                user_role="invalid_role",
                tenant_id="tenant-1",
            )
        assert "invalid" in str(exc_info.value).lower()

    def test_authorize_writeback_case_insensitive(self):
        """Role check is case-insensitive (E5)."""
        # Should not raise
        ReadOnlyGate.authorize_writeback(
            user_id="user-123",
            user_role="SUPERVISOR",
            tenant_id="tenant-1",
        )

    def test_error_includes_tenant_id(self):
        """Authorization errors include tenant ID for audit (E5)."""
        with pytest.raises(AuthorizationError) as exc_info:
            ReadOnlyGate.authorize_writeback(
                user_id="user-123",
                user_role="analyst",
                tenant_id="tenant-xyz",
            )
        assert "tenant-xyz" in str(exc_info.value)


class TestIsAuthorizedRole:
    """Tests for is_authorized_role utility function (E5)."""

    def test_is_authorized_role_supervisor(self):
        assert is_authorized_role("supervisor") is True

    def test_is_authorized_role_admin(self):
        assert is_authorized_role("admin") is True

    def test_is_authorized_role_analyst(self):
        assert is_authorized_role("analyst") is False

    def test_is_authorized_role_invalid(self):
        assert is_authorized_role("unknown_role") is False

    def test_is_authorized_role_case_insensitive(self):
        assert is_authorized_role("SUPERVISOR") is True
        assert is_authorized_role("Admin") is True


class TestAuditLogger:
    """Tests for audit logging (E5)."""

    def test_audit_logger_creation(self):
        """AuditLogger can be instantiated (E5)."""
        logger = AuditLogger()
        assert logger is not None

    def test_get_global_audit_logger(self):
        """get_audit_logger returns a global instance (E5)."""
        logger1 = get_audit_logger()
        logger2 = get_audit_logger()
        assert logger1 is logger2

    def test_log_writeback_attempt(self):
        """log_writeback_attempt creates an event (E5)."""
        logger = AuditLogger()
        event = logger.log_writeback_attempt(
            tenant_id="tenant-1",
            user_id="user-123",
            user_role="supervisor",
            task_id="task-456",
            resolution_status="RESOLVED",
        )

        assert event.event_type == AuditEventType.WRITEBACK_ATTEMPTED
        assert event.tenant_id == "tenant-1"
        assert event.user_id == "user-123"
        assert event.user_role == "supervisor"
        assert event.resource_id == "task-456"
        assert event.status == "pending"

    def test_log_writeback_authorized(self):
        """log_writeback_authorized creates an event (E5)."""
        logger = AuditLogger()
        event = logger.log_writeback_authorized(
            tenant_id="tenant-1",
            user_id="user-123",
            user_role="supervisor",
            task_id="task-456",
        )

        assert event.event_type == AuditEventType.WRITEBACK_AUTHORIZED
        assert event.status == "authorized"

    def test_log_writeback_denied(self):
        """log_writeback_denied creates an event (E5)."""
        logger = AuditLogger()
        event = logger.log_writeback_denied(
            tenant_id="tenant-1",
            user_id="user-123",
            user_role="analyst",
            task_id="task-456",
            reason="Analyst role not authorized",
        )

        assert event.event_type == AuditEventType.WRITEBACK_DENIED
        assert event.status == "denied"
        assert "Analyst" in event.reason

    def test_log_writeback_succeeded(self):
        """log_writeback_succeeded creates an event (E5)."""
        logger = AuditLogger()
        event = logger.log_writeback_succeeded(
            tenant_id="tenant-1",
            user_id="user-123",
            user_role="supervisor",
            task_id="task-456",
            fhir_status="completed",
        )

        assert event.event_type == AuditEventType.WRITEBACK_SUCCEEDED
        assert event.status == "succeeded"

    def test_log_writeback_failed(self):
        """log_writeback_failed creates an event (E5)."""
        logger = AuditLogger()
        event = logger.log_writeback_failed(
            tenant_id="tenant-1",
            user_id="user-123",
            user_role="supervisor",
            task_id="task-456",
            error="Epic Task not found",
        )

        assert event.event_type == AuditEventType.WRITEBACK_FAILED
        assert event.status == "failed"
        assert "not found" in event.reason

    def test_audit_event_to_dict(self):
        """AuditEvent serializes to dict (E5)."""
        logger = AuditLogger()
        event = logger.log_writeback_attempt(
            tenant_id="tenant-1",
            user_id="user-123",
            user_role="supervisor",
            task_id="task-456",
            resolution_status="RESOLVED",
        )

        event_dict = event.to_dict()
        assert isinstance(event_dict, dict)
        assert event_dict["tenant_id"] == "tenant-1"
        assert event_dict["user_id"] == "user-123"
        assert event_dict["resource_id"] == "task-456"
        assert "timestamp" in event_dict

    def test_audit_event_to_json(self):
        """AuditEvent serializes to JSON (E5)."""
        logger = AuditLogger()
        event = logger.log_writeback_attempt(
            tenant_id="tenant-1",
            user_id="user-123",
            user_role="supervisor",
            task_id="task-456",
            resolution_status="RESOLVED",
        )

        json_str = event.to_json()
        assert isinstance(json_str, str)
        assert "tenant_id" in json_str
        assert "user_id" in json_str
