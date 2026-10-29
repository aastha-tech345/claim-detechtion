"""Audit logging for E5: Read-Only Analytical Architecture enforcement.

Logs all external write operations, authorization decisions, and access attempts.
Provides durable evidence trail for compliance and security review (Blocker #3 fix).

Events are:
1. Logged to Python logger (for development/debugging)
2. Persisted to audit_logs table (for compliance/production)
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from waterfall_guard.integrations.supabase_writer import SupabaseWriter

logger = logging.getLogger(__name__)


class AuditEventType(str, Enum):
    """Types of auditable events (E5)."""
    WRITEBACK_ATTEMPTED = "writeback_attempted"
    WRITEBACK_AUTHORIZED = "writeback_authorized"
    WRITEBACK_DENIED = "writeback_denied"
    WRITEBACK_SUCCEEDED = "writeback_succeeded"
    WRITEBACK_FAILED = "writeback_failed"
    AUTHORIZATION_CHECK = "authorization_check"
    ROLE_CHECK_PASSED = "role_check_passed"
    ROLE_CHECK_FAILED = "role_check_failed"


@dataclass
class AuditEvent:
    """A single auditable event (E5)."""
    event_type: AuditEventType
    timestamp: datetime
    tenant_id: str
    user_id: Optional[str]
    user_role: Optional[str]
    operation: str  # "epic_fhir_writeback", "claim_modification", etc.
    resource_id: str  # task_id, claim_id, etc.
    resource_type: str  # "fhir_task", "claim", etc.
    status: str  # "success", "denied", "failed"
    reason: Optional[str]  # Why denied or why failed
    details: Optional[Dict[str, Any]] = None  # Additional context (no PHI)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for JSON serialization."""
        event_dict = asdict(self)
        event_dict["timestamp"] = self.timestamp.isoformat()
        event_dict["event_type"] = self.event_type.value
        return event_dict

    def to_json(self) -> str:
        """Serialize to JSON."""
        return json.dumps(self.to_dict(), default=str)


class AuditLogger:
    """Centralized audit logging for E5 enforcement (E5).
    
    Events are:
    1. Logged to Python logger (immediate visibility)
    2. Persisted to database (durable audit trail - Blocker #3 fix)
    """

    def __init__(self, logger_instance: Optional[logging.Logger] = None):
        self.logger = logger_instance or logger
        self._writer: Optional[Any] = None  # Lazy-loaded SupabaseWriter

    @property
    def writer(self) -> Optional[Any]:
        """Lazily load SupabaseWriter to avoid circular imports."""
        if self._writer is None:
            try:
                from waterfall_guard.integrations.supabase_writer import SupabaseWriter
                self._writer = SupabaseWriter(table_name="audit_logs")
            except Exception as e:
                logger.warning(f"Could not initialize audit log persistence: {e}")
                self._writer = None
        return self._writer

    def log_event(self, event: AuditEvent) -> None:
        """Log an audit event.

        Args:
            event: AuditEvent to log
            
        Logs to both Python logger and database (if available).
        Never raises - failures are logged but don't crash the application.
        """
        # 1. Log to Python logger (immediate visibility)
        self.logger.info(
            f"AUDIT: {event.event_type.value} | "
            f"tenant={event.tenant_id} | "
            f"user={event.user_id} | "
            f"role={event.user_role} | "
            f"op={event.operation} | "
            f"resource={event.resource_type}:{event.resource_id} | "
            f"status={event.status} | "
            f"reason={event.reason}"
        )
        
        # 2. Persist to database (durable audit trail - Blocker #3 fix)
        self._persist_audit_event(event)

    def _persist_audit_event(self, event: AuditEvent) -> None:
        """Persist audit event to database.
        
        Called by log_event() to write to audit_logs table.
        Failures are logged but don't raise (soft-fail design).
        
        Args:
            event: AuditEvent to persist
        """
        try:
            writer = self.writer
            if writer is None:
                # Supabase not available - skip persistence
                return
            
            if not writer.enabled:
                # Writer is disabled (missing credentials, etc.)
                return
            
            # Prepare event for insertion
            event_dict = event.to_dict()
            
            # Write to audit_logs table
            result = writer.write_rows([event_dict])
            
            if not result.ok:
                logger.warning(f"Failed to persist audit event: {result.error}")
                
        except Exception as e:
            # Soft-fail: log error but don't raise
            logger.warning(f"Error persisting audit event: {e}")


    def log_writeback_attempt(
        self,
        tenant_id: str,
        user_id: Optional[str],
        user_role: Optional[str],
        task_id: str,
        resolution_status: str,
    ) -> AuditEvent:
        """Log a writeback attempt (E5).

        Args:
            tenant_id: Tenant making request
            user_id: User ID (if available)
            user_role: User role (analyst, supervisor, admin)
            task_id: Epic Task ID being updated
            resolution_status: RESOLVED, ESCALATED, WONT_FIX

        Returns:
            AuditEvent logged.
        """
        event = AuditEvent(
            event_type=AuditEventType.WRITEBACK_ATTEMPTED,
            timestamp=datetime.now(timezone.utc),
            tenant_id=tenant_id,
            user_id=user_id,
            user_role=user_role,
            operation="epic_fhir_writeback",
            resource_id=task_id,
            resource_type="fhir_task",
            status="pending",
            reason=None,
            details={"resolution_status": resolution_status},
        )
        self.log_event(event)
        return event

    def log_writeback_authorized(
        self,
        tenant_id: str,
        user_id: Optional[str],
        user_role: str,
        task_id: str,
    ) -> AuditEvent:
        """Log authorization check passed (E5).

        Args:
            tenant_id: Tenant
            user_id: User ID
            user_role: User role
            task_id: Task ID

        Returns:
            AuditEvent logged.
        """
        event = AuditEvent(
            event_type=AuditEventType.WRITEBACK_AUTHORIZED,
            timestamp=datetime.now(timezone.utc),
            tenant_id=tenant_id,
            user_id=user_id,
            user_role=user_role,
            operation="epic_fhir_writeback",
            resource_id=task_id,
            resource_type="fhir_task",
            status="authorized",
            reason=f"User role {user_role} has permission",
        )
        self.log_event(event)
        return event

    def log_writeback_denied(
        self,
        tenant_id: str,
        user_id: Optional[str],
        user_role: Optional[str],
        task_id: str,
        reason: str,
    ) -> AuditEvent:
        """Log authorization check failed (E5).

        Args:
            tenant_id: Tenant
            user_id: User ID (if available)
            user_role: User role (if available)
            task_id: Task ID
            reason: Why denied (e.g., "Missing supervisor role")

        Returns:
            AuditEvent logged.
        """
        event = AuditEvent(
            event_type=AuditEventType.WRITEBACK_DENIED,
            timestamp=datetime.now(timezone.utc),
            tenant_id=tenant_id,
            user_id=user_id,
            user_role=user_role,
            operation="epic_fhir_writeback",
            resource_id=task_id,
            resource_type="fhir_task",
            status="denied",
            reason=reason,
        )
        self.log_event(event)
        return event

    def log_writeback_succeeded(
        self,
        tenant_id: str,
        user_id: Optional[str],
        user_role: str,
        task_id: str,
        fhir_status: str,
    ) -> AuditEvent:
        """Log successful writeback (E5).

        Args:
            tenant_id: Tenant
            user_id: User ID
            user_role: User role
            task_id: Task ID
            fhir_status: Final FHIR status (completed, in-progress, cancelled)

        Returns:
            AuditEvent logged.
        """
        event = AuditEvent(
            event_type=AuditEventType.WRITEBACK_SUCCEEDED,
            timestamp=datetime.now(timezone.utc),
            tenant_id=tenant_id,
            user_id=user_id,
            user_role=user_role,
            operation="epic_fhir_writeback",
            resource_id=task_id,
            resource_type="fhir_task",
            status="succeeded",
            reason=None,
            details={"fhir_status": fhir_status},
        )
        self.log_event(event)
        return event

    def log_writeback_failed(
        self,
        tenant_id: str,
        user_id: Optional[str],
        user_role: str,
        task_id: str,
        error: str,
    ) -> AuditEvent:
        """Log failed writeback (E5).

        Args:
            tenant_id: Tenant
            user_id: User ID
            user_role: User role
            task_id: Task ID
            error: Error message

        Returns:
            AuditEvent logged.
        """
        event = AuditEvent(
            event_type=AuditEventType.WRITEBACK_FAILED,
            timestamp=datetime.now(timezone.utc),
            tenant_id=tenant_id,
            user_id=user_id,
            user_role=user_role,
            operation="epic_fhir_writeback",
            resource_id=task_id,
            resource_type="fhir_task",
            status="failed",
            reason=error,
        )
        self.log_event(event)
        return event


# Global audit logger instance
_audit_logger = AuditLogger()


def get_audit_logger() -> AuditLogger:
    """Get the global audit logger instance."""
    return _audit_logger
