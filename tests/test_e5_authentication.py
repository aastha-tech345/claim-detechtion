"""E5 Authentication Hardening Tests.

Tests for secure user identity derivation, session validation, and authorization.
Verifies that untrusted user-entered fields are NOT used for authentication/authorization.
"""

import unittest
from unittest.mock import MagicMock, patch

from waterfall_guard.auth_session import (
    SessionValidator,
    AuthenticatedUser,
    AuthenticationError,
    UserRole,
)
from .jwt_test_helper import create_valid_jwt_token


class TestAuthenticationState(unittest.TestCase):
    """Test session state management and validation."""

    def setUp(self):
        """Set up mocked Streamlit session state."""
        self.mock_session = {}

    def test_is_authenticated_returns_false_when_not_authenticated(self):
        """is_authenticated() returns False when no authentication in session."""
        with patch("streamlit.session_state", {}):
            self.assertFalse(SessionValidator.is_authenticated())

    def test_is_authenticated_returns_false_when_authenticated_false(self):
        """is_authenticated() returns False when is_authenticated=False."""
        with patch("streamlit.session_state", {"is_authenticated": False}):
            self.assertFalse(SessionValidator.is_authenticated())

    def test_is_authenticated_returns_true_when_authenticated_true(self):
        """is_authenticated() returns True when is_authenticated=True."""
        with patch("streamlit.session_state", {"is_authenticated": True}):
            self.assertTrue(SessionValidator.is_authenticated())


class TestUserContextDerivation(unittest.TestCase):
    """Test derivation of user context from authenticated session."""

    def test_get_authenticated_user_returns_none_when_not_authenticated(self):
        """get_authenticated_user() returns None if not authenticated."""
        with patch("streamlit.session_state", {"is_authenticated": False}):
            result = SessionValidator.get_authenticated_user()
            self.assertIsNone(result)

    def test_get_authenticated_user_extracts_user_id_from_session(self):
        """get_authenticated_user() extracts user_id from session (not form)."""
        session = {
            "is_authenticated": True,
            "user": {
                "user_id": "uuid-12345",
                "email": "user@example.com",
                "tenant_id": "tenant_abc",
                "access_token": create_valid_jwt_token(user_id="uuid-12345"),
            },
        }

        with patch("streamlit.session_state", session):
            user = SessionValidator.get_authenticated_user()
            self.assertEqual(user.user_id, "uuid-12345")

    def test_get_authenticated_user_extracts_email_from_session(self):
        """get_authenticated_user() extracts email from session (verified by auth)."""
        session = {
            "is_authenticated": True,
            "user": {
                "user_id": "uuid-12345",
                "email": "verified@supabase.auth",
                "tenant_id": "tenant_abc",
                "access_token": create_valid_jwt_token(user_id="uuid-12345"),
            },
        }

        with patch("streamlit.session_state", session):
            user = SessionValidator.get_authenticated_user()
            self.assertEqual(user.email, "verified@supabase.auth")

    def test_get_authenticated_user_extracts_tenant_id_from_session(self):
        """get_authenticated_user() extracts tenant_id (from DB, not form)."""
        session = {
            "is_authenticated": True,
            "user": {
                "user_id": "uuid-12345",
                "email": "user@example.com",
                "tenant_id": "tenant_organization_123",
                "access_token": create_valid_jwt_token(user_id="uuid-12345"),
            },
        }

        with patch("streamlit.session_state", session):
            user = SessionValidator.get_authenticated_user()
            self.assertEqual(user.tenant_id, "tenant_organization_123")

    def test_get_authenticated_user_raises_on_missing_user_id(self):
        """get_authenticated_user() raises if user_id missing from session."""
        session = {
            "is_authenticated": True,
            "user": {
                "email": "user@example.com",
                "tenant_id": "tenant_abc",
                "access_token": "token_xyz",
            },
        }

        with patch("streamlit.session_state", session):
            with self.assertRaises(AuthenticationError):
                SessionValidator.get_authenticated_user()

    def test_get_authenticated_user_raises_on_missing_email(self):
        """get_authenticated_user() raises if email missing (auth should provide)."""
        session = {
            "is_authenticated": True,
            "user": {
                "user_id": "uuid-12345",
                "tenant_id": "tenant_abc",
                "access_token": "token_xyz",
            },
        }

        with patch("streamlit.session_state", session):
            with self.assertRaises(AuthenticationError):
                SessionValidator.get_authenticated_user()

    def test_get_authenticated_user_raises_on_missing_tenant_id(self):
        """get_authenticated_user() raises if tenant_id missing (should be in DB)."""
        session = {
            "is_authenticated": True,
            "user": {
                "user_id": "uuid-12345",
                "email": "user@example.com",
                "access_token": "token_xyz",
            },
        }

        with patch("streamlit.session_state", session):
            with self.assertRaises(AuthenticationError):
                SessionValidator.get_authenticated_user()

    def test_get_authenticated_user_raises_on_missing_access_token(self):
        """get_authenticated_user() raises if access_token missing."""
        session = {
            "is_authenticated": True,
            "user": {
                "user_id": "uuid-12345",
                "email": "user@example.com",
                "tenant_id": "tenant_abc",
                # No access_token
            },
        }

        with patch("streamlit.session_state", session):
            with self.assertRaises(AuthenticationError):
                SessionValidator.get_authenticated_user()


class TestRoleDerivation(unittest.TestCase):
    """Test role derivation from session."""

    def test_authenticated_user_defaults_to_analyst_role(self):
        """AuthenticatedUser defaults to ANALYST role if not specified."""
        session = {
            "is_authenticated": True,
            "user": {
                "user_id": "uuid-12345",
                "email": "user@example.com",
                "tenant_id": "tenant_abc",
                "access_token": create_valid_jwt_token(user_id="uuid-12345"),
                # No role specified
            },
        }

        with patch("streamlit.session_state", session):
            user = SessionValidator.get_authenticated_user()
            self.assertEqual(user.role, UserRole.ANALYST)

    def test_authenticated_user_accepts_supervisor_role_from_session(self):
        """AuthenticatedUser accepts supervisor role from session."""
        session = {
            "is_authenticated": True,
            "user": {
                "user_id": "uuid-12345",
                "email": "user@example.com",
                "tenant_id": "tenant_abc",
                "access_token": create_valid_jwt_token(user_id="uuid-12345"),
                "role": "supervisor",
            },
        }

        with patch("streamlit.session_state", session):
            user = SessionValidator.get_authenticated_user()
            self.assertEqual(user.role, UserRole.SUPERVISOR)

    def test_authenticated_user_accepts_admin_role_from_session(self):
        """AuthenticatedUser accepts admin role from session."""
        session = {
            "is_authenticated": True,
            "user": {
                "user_id": "uuid-12345",
                "email": "user@example.com",
                "tenant_id": "tenant_abc",
                "access_token": create_valid_jwt_token(user_id="uuid-12345"),
                "role": "admin",
            },
        }

        with patch("streamlit.session_state", session):
            user = SessionValidator.get_authenticated_user()
            self.assertEqual(user.role, UserRole.ADMIN)

    def test_authenticated_user_ignores_case_in_role(self):
        """AuthenticatedUser normalizes role to lowercase."""
        session = {
            "is_authenticated": True,
            "user": {
                "user_id": "uuid-12345",
                "email": "user@example.com",
                "tenant_id": "tenant_abc",
                "access_token": create_valid_jwt_token(user_id="uuid-12345"),
                "role": "SUPERVISOR",  # Uppercase
            },
        }

        with patch("streamlit.session_state", session):
            user = SessionValidator.get_authenticated_user()
            self.assertEqual(user.role, UserRole.SUPERVISOR)

    def test_authenticated_user_defaults_analyst_on_invalid_role(self):
        """AuthenticatedUser defaults to ANALYST if role is invalid."""
        session = {
            "is_authenticated": True,
            "user": {
                "user_id": "uuid-12345",
                "email": "user@example.com",
                "tenant_id": "tenant_abc",
                "access_token": create_valid_jwt_token(user_id="uuid-12345"),
                "role": "invalid_role",
            },
        }

        with patch("streamlit.session_state", session):
            user = SessionValidator.get_authenticated_user()
            self.assertEqual(user.role, UserRole.ANALYST)


class TestRoleHierarchyAndAuthorization(unittest.TestCase):
    """Test role-based authorization checks."""

    def test_require_authorized_role_allows_supervisor_for_supervisor_task(self):
        """require_authorized_role() allows supervisor role for supervisor task."""
        session = {
            "is_authenticated": True,
            "user": {
                "user_id": "uuid-12345",
                "email": "sup@example.com",
                "tenant_id": "tenant_abc",
                "access_token": create_valid_jwt_token(user_id="uuid-12345"),
                "role": "supervisor",
            },
        }

        with patch("streamlit.session_state", session):
            user = SessionValidator.require_authorized_role(UserRole.SUPERVISOR)
            self.assertEqual(user.role, UserRole.SUPERVISOR)

    def test_require_authorized_role_allows_admin_for_supervisor_task(self):
        """require_authorized_role() allows admin role for supervisor task (hierarchy)."""
        session = {
            "is_authenticated": True,
            "user": {
                "user_id": "uuid-12345",
                "email": "admin@example.com",
                "tenant_id": "tenant_abc",
                "access_token": create_valid_jwt_token(user_id="uuid-12345"),
                "role": "admin",
            },
        }

        with patch("streamlit.session_state", session):
            user = SessionValidator.require_authorized_role(UserRole.SUPERVISOR)
            self.assertEqual(user.role, UserRole.ADMIN)

    def test_require_authorized_role_denies_analyst_for_supervisor_task(self):
        """require_authorized_role() denies analyst role for supervisor task."""
        session = {
            "is_authenticated": True,
            "user": {
                "user_id": "uuid-12345",
                "email": "analyst@example.com",
                "tenant_id": "tenant_abc",
                "access_token": create_valid_jwt_token(user_id="uuid-12345"),
                "role": "analyst",
            },
        }

        with patch("streamlit.session_state", session):
            with self.assertRaises(AuthenticationError) as ctx:
                SessionValidator.require_authorized_role(UserRole.SUPERVISOR)
            self.assertIn("Insufficient permissions", str(ctx.exception))

    def test_require_authorized_role_denies_supervisor_for_admin_task(self):
        """require_authorized_role() denies supervisor role for admin task."""
        session = {
            "is_authenticated": True,
            "user": {
                "user_id": "uuid-12345",
                "email": "sup@example.com",
                "tenant_id": "tenant_abc",
                "access_token": create_valid_jwt_token(user_id="uuid-12345"),
                "role": "supervisor",
            },
        }

        with patch("streamlit.session_state", session):
            with self.assertRaises(AuthenticationError) as ctx:
                SessionValidator.require_authorized_role(UserRole.ADMIN)
            self.assertIn("Insufficient permissions", str(ctx.exception))

    def test_require_authorized_role_allows_analyst_for_analyst_task(self):
        """require_authorized_role() allows analyst role for analyst task."""
        session = {
            "is_authenticated": True,
            "user": {
                "user_id": "uuid-12345",
                "email": "analyst@example.com",
                "tenant_id": "tenant_abc",
                "access_token": create_valid_jwt_token(user_id="uuid-12345"),
                "role": "analyst",
            },
        }

        with patch("streamlit.session_state", session):
            user = SessionValidator.require_authorized_role(UserRole.ANALYST)
            self.assertEqual(user.role, UserRole.ANALYST)


class TestTenantIsolation(unittest.TestCase):
    """Test tenant ID extraction and isolation."""

    def test_get_tenant_id_returns_tenant_from_session(self):
        """get_tenant_id() returns tenant_id from authenticated session."""
        session = {
            "is_authenticated": True,
            "user": {
                "user_id": "uuid-12345",
                "email": "user@example.com",
                "tenant_id": "tenant_org_x",
                "access_token": create_valid_jwt_token(user_id="uuid-12345"),
            },
        }

        with patch("streamlit.session_state", session):
            tenant_id = SessionValidator.get_tenant_id()
            self.assertEqual(tenant_id, "tenant_org_x")

    def test_get_tenant_id_returns_none_when_not_authenticated(self):
        """get_tenant_id() returns None if not authenticated."""
        with patch("streamlit.session_state", {"is_authenticated": False}):
            tenant_id = SessionValidator.get_tenant_id()
            self.assertIsNone(tenant_id)

    def test_require_tenant_id_raises_when_not_authenticated(self):
        """require_tenant_id() raises if not authenticated."""
        with patch("streamlit.session_state", {"is_authenticated": False}):
            with self.assertRaises(AuthenticationError):
                SessionValidator.require_tenant_id()

    def test_require_tenant_id_returns_tenant_when_authenticated(self):
        """require_tenant_id() returns tenant_id if authenticated."""
        session = {
            "is_authenticated": True,
            "user": {
                "user_id": "uuid-12345",
                "email": "user@example.com",
                "tenant_id": "tenant_org_y",
                "access_token": create_valid_jwt_token(user_id="uuid-12345"),
            },
        }

        with patch("streamlit.session_state", session):
            tenant_id = SessionValidator.require_tenant_id()
            self.assertEqual(tenant_id, "tenant_org_y")


class TestSecurityBoundaries(unittest.TestCase):
    """Test that security boundaries prevent unauthorized access."""

    def test_unauthenticated_user_cannot_get_authenticated_user(self):
        """Unauthenticated user cannot retrieve any authenticated user object."""
        with patch("streamlit.session_state", {"is_authenticated": False}):
            with self.assertRaises(AuthenticationError):
                SessionValidator.require_authenticated_user()

    def test_invalid_session_rejected(self):
        """Invalid or corrupt session is rejected."""
        session = {
            "is_authenticated": True,
            "user": None,  # Corrupt: null user
        }

        with patch("streamlit.session_state", session):
            with self.assertRaises(AuthenticationError):
                SessionValidator.require_authenticated_user()

    def test_forged_user_id_not_trusted(self):
        """User ID must come from session, not form input."""
        # This test verifies the architecture: SessionValidator only reads
        # from st.session_state (trusted) and never accepts user_id from form
        session = {
            "is_authenticated": True,
            "user": {
                "user_id": "session_uuid_correct",
                "email": "user@example.com",
                "tenant_id": "tenant_abc",
                "access_token": create_valid_jwt_token(user_id="session_uuid_correct"),
            },
        }

        with patch("streamlit.session_state", session):
            user = SessionValidator.get_authenticated_user()
            # SessionValidator returns session user_id, NEVER accepts form input
            self.assertEqual(user.user_id, "session_uuid_correct")

    def test_forged_tenant_id_not_trusted(self):
        """Tenant ID must come from session, not form input."""
        session = {
            "is_authenticated": True,
            "user": {
                "user_id": "uuid-12345",
                "email": "user@example.com",
                "tenant_id": "correct_tenant_from_session",
                "access_token": create_valid_jwt_token(user_id="uuid-12345"),
            },
        }

        with patch("streamlit.session_state", session):
            user = SessionValidator.get_authenticated_user()
            # SessionValidator returns session tenant_id, NEVER accepts form input
            self.assertEqual(user.tenant_id, "correct_tenant_from_session")

    def test_forged_role_not_trusted_from_form(self):
        """Role must come from session/DB, not form input."""
        session = {
            "is_authenticated": True,
            "user": {
                "user_id": "uuid-12345",
                "email": "user@example.com",
                "tenant_id": "tenant_abc",
                "access_token": create_valid_jwt_token(user_id="uuid-12345"),
                "role": "admin",  # From session after DB lookup, not form
            },
        }

        with patch("streamlit.session_state", session):
            user = SessionValidator.get_authenticated_user()
            # SessionValidator returns session role, NEVER accepts form input
            self.assertEqual(user.role, UserRole.ADMIN)


class TestAuditContextPreservation(unittest.TestCase):
    """Test that authenticated user context is properly preserved for audit logs."""

    def test_authenticated_user_to_dict_contains_all_audit_fields(self):
        """AuthenticatedUser.to_dict() contains all required audit fields."""
        user = AuthenticatedUser(
            user_id="uuid-12345",
            email="user@example.com",
            tenant_id="tenant_abc",
            organization_name="Org Name",
            role=UserRole.SUPERVISOR,
            access_token="token_xyz",
        )

        user_dict = user.to_dict()

        self.assertIn("user_id", user_dict)
        self.assertIn("email", user_dict)
        self.assertIn("tenant_id", user_dict)
        self.assertIn("organization_name", user_dict)
        self.assertIn("role", user_dict)

    def test_authenticated_user_to_dict_does_not_expose_token(self):
        """AuthenticatedUser.to_dict() does NOT include access_token (security)."""
        user = AuthenticatedUser(
            user_id="uuid-12345",
            email="user@example.com",
            tenant_id="tenant_abc",
            organization_name="Org Name",
            role=UserRole.SUPERVISOR,
            access_token="token_xyz_secret",
        )

        user_dict = user.to_dict()

        self.assertNotIn("access_token", user_dict)


if __name__ == "__main__":
    unittest.main()

