"""Secure session and user context derivation for E5 authentication.

This module provides server-side validation of user identity, role, and tenant
context. It replaces untrusted user-entered fields with derived, validated
values from the authenticated session.

CRITICAL: Do NOT trust user-entered form fields for identity or authorization.
Always derive user_id, role, and tenant_id from st.session_state which is
populated by the authentication app (auth_app.py) after successful login.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Optional

import streamlit as st

logger = logging.getLogger(__name__)


class UserRole(str, Enum):
    """User roles derived from database or session."""
    ANALYST = "analyst"  # Read-only analysis
    SUPERVISOR = "supervisor"  # Can approve resolutions
    ADMIN = "admin"  # Full access


@dataclass
class AuthenticatedUser:
    """Validated user context from authenticated session."""
    user_id: str  # UUID from Supabase Auth
    email: str  # Verified email from Supabase Auth
    tenant_id: str  # Organization from client_configurations table
    organization_name: str  # Organization display name
    role: UserRole  # Role from user_roles table or default ANALYST
    access_token: str  # JWT access token for API calls

    def to_dict(self):
        """Convert to dict for audit logging."""
        return {
            "user_id": self.user_id,
            "email": self.email,
            "tenant_id": self.tenant_id,
            "organization_name": self.organization_name,
            "role": self.role.value,
        }


class AuthenticationError(Exception):
    """Raised when authentication validation fails."""
    pass


class SessionValidator:
    """Validates and derives user context from authenticated session."""

    @staticmethod
    def is_authenticated() -> bool:
        """Check if a user is currently authenticated in session.

        Returns:
            True if user has valid session, False otherwise.
        """
        if "is_authenticated" not in st.session_state:
            return False

        return st.session_state.get("is_authenticated", False) is True

    @staticmethod
    def get_authenticated_user() -> Optional[AuthenticatedUser]:
        """Get validated authenticated user from session.

        Returns:
            AuthenticatedUser if session is valid, None if not authenticated.

        Raises:
            AuthenticationError: If session is invalid or corrupt.
        """
        if not SessionValidator.is_authenticated():
            return None

        try:
            user_data = st.session_state.get("user", {})

            if not user_data:
                raise AuthenticationError("No user data in session")

            # Validate required fields from session
            required_fields = ["user_id", "email", "tenant_id", "access_token"]
            for field in required_fields:
                if field not in user_data or not user_data[field]:
                    raise AuthenticationError(f"Missing required field: {field}")

            # Derive role from session (default to ANALYST if not set)
            # In production, role would be stored in a user_roles table
            role_str = user_data.get("role", "analyst").lower()
            try:
                role = UserRole(role_str)
            except ValueError:
                logger.warning(f"Invalid role in session: {role_str}, defaulting to ANALYST")
                role = UserRole.ANALYST

            return AuthenticatedUser(
                user_id=user_data["user_id"],
                email=user_data["email"],
                tenant_id=user_data["tenant_id"],
                organization_name=user_data.get("organization_name", ""),
                role=role,
                access_token=user_data["access_token"],
            )

        except KeyError as e:
            raise AuthenticationError(f"Malformed session: {e}")
        except Exception as e:
            raise AuthenticationError(f"Session validation failed: {e}")

    @staticmethod
    def require_authenticated_user() -> AuthenticatedUser:
        """Require authenticated user or raise error.

        Returns:
            AuthenticatedUser from validated session.

        Raises:
            AuthenticationError: If not authenticated or session invalid.
        """
        if not SessionValidator.is_authenticated():
            raise AuthenticationError("Not authenticated: Please log in to continue")

        user = SessionValidator.get_authenticated_user()

        if not user:
            raise AuthenticationError("Invalid or expired session: Please log in again")

        return user

    @staticmethod
    def require_authorized_role(required_role: UserRole) -> AuthenticatedUser:
        """Require authenticated user with specific role or raise error.

        Args:
            required_role: Minimum required role (e.g., UserRole.SUPERVISOR)

        Returns:
            AuthenticatedUser if user has required role.

        Raises:
            AuthenticationError: If not authenticated, invalid session, or insufficient role.
        """
        user = SessionValidator.require_authenticated_user()

        # Role hierarchy: ANALYST < SUPERVISOR < ADMIN
        role_hierarchy = {
            UserRole.ANALYST: 0,
            UserRole.SUPERVISOR: 1,
            UserRole.ADMIN: 2,
        }

        if role_hierarchy.get(user.role, -1) < role_hierarchy.get(required_role, -1):
            raise AuthenticationError(
                f"Insufficient permissions: Your role ({user.role.value}) "
                f"cannot perform this action (requires {required_role.value})"
            )

        return user

    @staticmethod
    def get_tenant_id() -> Optional[str]:
        """Get current user's tenant ID from session.

        Returns:
            Tenant ID if user is authenticated, None otherwise.
        """
        try:
            user = SessionValidator.get_authenticated_user()
            return user.tenant_id if user else None
        except AuthenticationError:
            return None

    @staticmethod
    def require_tenant_id() -> str:
        """Require tenant ID or raise error.

        Returns:
            Tenant ID from authenticated user.

        Raises:
            AuthenticationError: If not authenticated or no tenant ID.
        """
        user = SessionValidator.require_authenticated_user()

        if not user.tenant_id:
            raise AuthenticationError(
                "Tenant ID not available in session. "
                "Contact system administrator."
            )

        return user.tenant_id


def require_authentication() -> AuthenticatedUser:
    """Convenience function: require authentication or stop execution.

    This is typically called at the top of Streamlit pages that require login.

    Returns:
        AuthenticatedUser from validated session.

    Raises:
        st.StopException: If not authenticated (via st.error() + st.stop()).
    """
    try:
        return SessionValidator.require_authenticated_user()
    except AuthenticationError as e:
        st.error(f"🔒 {str(e)}")
        st.stop()


def require_authorization(required_role: UserRole) -> AuthenticatedUser:
    """Convenience function: require authentication with specific role.

    Returns:
        AuthenticatedUser if user is authenticated with required role.

    Raises:
        st.StopException: If not authenticated or insufficient role.
    """
    try:
        return SessionValidator.require_authorized_role(required_role)
    except AuthenticationError as e:
        st.error(f"🔒 {str(e)}")
        st.stop()

