"""Read-Only Analytical Architecture Enforcement — E5.

Enforces that the analytical environment cannot independently execute write
operations. All writes must go through authorized channels (e.g., dashboard form,
approval workflow).

This module provides guardrails to prevent unauthorized invocations of the
writeback client from within the analytical process.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional


class UserRole(str, Enum):
    """User roles for E5 authorization (E5)."""
    ANALYST = "analyst"  # Read-only analysis
    SUPERVISOR = "supervisor"  # Can approve resolutions
    ADMIN = "admin"  # Full access


class AuthorizationError(Exception):
    """Raised when an unauthorized write attempt is made (E5)."""
    pass


class ReadOnlyGate:
    """Enforces read-only boundaries for the analytical environment (E5).

    This gate prevents direct invocation of write clients from analytical code
    (engine.py, main.py) without proper authorization.
    """

    # Roles allowed to execute writebacks
    AUTHORIZED_WRITEBACK_ROLES = {UserRole.SUPERVISOR, UserRole.ADMIN}

    @classmethod
    def authorize_writeback(
        cls,
        user_id: Optional[str],
        user_role: Optional[str],
        tenant_id: str,
    ) -> None:
        """Check if a user is authorized to execute a writeback operation (E5).

        Args:
            user_id: User identifier (from session/auth context)
            user_role: User role (analyst, supervisor, admin)
            tenant_id: Tenant ID

        Raises:
            AuthorizationError: If user is not authorized.
        """
        if not user_id:
            raise AuthorizationError(
                f"Writeback denied: No user context available. "
                f"Tenant={tenant_id}. User must be authenticated."
            )

        if not user_role:
            raise AuthorizationError(
                f"Writeback denied: No user role available. "
                f"Tenant={tenant_id}, User={user_id}. Role must be set."
            )

        try:
            role = UserRole(user_role.lower())
        except ValueError:
            raise AuthorizationError(
                f"Writeback denied: Invalid user role {user_role!r}. "
                f"Tenant={tenant_id}, User={user_id}. "
                f"Allowed roles: {', '.join(r.value for r in UserRole)}"
            )

        if role not in cls.AUTHORIZED_WRITEBACK_ROLES:
            raise AuthorizationError(
                f"Writeback denied: User role {role.value!r} not authorized for writebacks. "
                f"Tenant={tenant_id}, User={user_id}. "
                f"Authorized roles: {', '.join(r.value for r in cls.AUTHORIZED_WRITEBACK_ROLES)}"
            )

    @classmethod
    def assert_analytical_context(cls) -> None:
        """Assert we're in the analytical (read-only) context, not execution context (E5).

        This is a documentation guardrail; raises if called from a write context.

        Raises:
            AuthorizationError: If called from an execution context.
        """
        # Future: implement stack inspection to prevent writeback client
        # from being invoked from non-approved call paths.
        pass


def is_authorized_role(role: str) -> bool:
    """Check if a role is authorized for write operations (E5).

    Args:
        role: Role string (analyst, supervisor, admin)

    Returns:
        True if role is authorized, False otherwise.
    """
    try:
        user_role = UserRole(role.lower())
        return user_role in ReadOnlyGate.AUTHORIZED_WRITEBACK_ROLES
    except ValueError:
        return False
