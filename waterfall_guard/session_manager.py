"""Session timeout and token refresh management.

Handles:
- Session timeout detection with configurable idle time
- Automatic token refresh before expiration
- Session expiration warnings
- Graceful session cleanup on timeout
"""

import os
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, Callable

import streamlit as st
from supabase import create_client

logger = logging.getLogger(__name__)

# Configuration (in minutes)
SESSION_TIMEOUT_MINUTES = int(os.getenv("SESSION_TIMEOUT_MINUTES", "30"))
IDLE_TIMEOUT_MINUTES = int(os.getenv("IDLE_TIMEOUT_MINUTES", "20"))
TOKEN_REFRESH_THRESHOLD_MINUTES = int(os.getenv("TOKEN_REFRESH_THRESHOLD_MINUTES", "5"))
SESSION_WARNING_THRESHOLD_MINUTES = int(os.getenv("SESSION_WARNING_THRESHOLD_MINUTES", "2"))


class SessionManager:
    """Manages session lifecycle, token refresh, and timeout detection."""

    @staticmethod
    def _get_supabase_client():
        """Get Supabase client for token refresh operations."""
        try:
            from waterfall_guard.auth import get_auth_client
            return get_auth_client()
        except Exception as e:
            logger.error(f"Failed to get Supabase client: {e}")
            return None

    @staticmethod
    def _initialize_session_tracking():
        """Initialize session tracking variables in Streamlit session state."""
        if "session_initialized" not in st.session_state:
            now = datetime.now(timezone.utc)
            st.session_state.session_initialized = True
            st.session_state.session_start_time = now
            st.session_state.last_activity_time = now
            st.session_state.token_refresh_attempted = False
            st.session_state.session_expiration_warning_shown = False

    @staticmethod
    def _update_activity():
        """Update last activity timestamp."""
        st.session_state.last_activity_time = datetime.now(timezone.utc)

    @staticmethod
    def _get_session_start_time() -> datetime:
        """Get session start time, defaulting to now if not set."""
        return st.session_state.get("session_start_time") or datetime.now(timezone.utc)

    @staticmethod
    def _get_last_activity_time() -> datetime:
        """Get last activity time, defaulting to now if not set."""
        return st.session_state.get("last_activity_time") or datetime.now(timezone.utc)

    @staticmethod
    def _get_idle_duration() -> timedelta:
        """Calculate time elapsed since last activity."""
        return datetime.now(timezone.utc) - SessionManager._get_last_activity_time()

    @staticmethod
    def _get_session_duration() -> timedelta:
        """Calculate total session duration."""
        return datetime.now(timezone.utc) - SessionManager._get_session_start_time()

    @staticmethod
    def _is_token_about_to_expire() -> bool:
        """Check if access token is near expiration."""
        user = st.session_state.get("user")
        if not user or not user.get("access_token"):
            return False

        try:
            import jwt
            token = user["access_token"]
            # Decode without verification just to check expiration
            decoded = jwt.decode(token, options={"verify_signature": False})
            
            if "exp" not in decoded:
                return False
            
            exp_time = datetime.fromtimestamp(decoded["exp"], tz=timezone.utc)
            time_until_expiration = exp_time - datetime.now(timezone.utc)
            threshold = timedelta(minutes=TOKEN_REFRESH_THRESHOLD_MINUTES)
            
            return time_until_expiration <= threshold
        except Exception as e:
            logger.warning(f"Could not check token expiration: {e}")
            return False

    @staticmethod
    def refresh_access_token() -> bool:
        """
        Refresh the access token using the refresh token.
        
        Returns:
            True if token was successfully refreshed, False otherwise.
        """
        user = st.session_state.get("user")
        if not user or not user.get("refresh_token"):
            logger.warning("No refresh token available")
            return False

        try:
            client = SessionManager._get_supabase_client()
            if not client:
                logger.error("Could not get Supabase client for token refresh")
                return False

            # Refresh the session
            response = client.auth.refresh_session(user["refresh_token"])
            
            if response.session:
                # Update tokens in session state
                st.session_state.user["access_token"] = response.session.access_token
                st.session_state.user["refresh_token"] = response.session.refresh_token
                st.session_state.token_refresh_attempted = True
                
                logger.info(f"Token refreshed successfully for user {user.get('email')}")
                return True
            else:
                logger.warning("Token refresh returned no session")
                return False

        except Exception as e:
            logger.error(f"Token refresh failed: {e}")
            return False

    @staticmethod
    def check_and_refresh_token() -> bool:
        """
        Check if token needs refresh and attempt refresh if necessary.
        
        Returns:
            True if token is valid (or was refreshed), False if refresh failed.
        """
        if not SessionManager._is_token_about_to_expire():
            return True

        logger.info("Token about to expire, attempting refresh")
        return SessionManager.refresh_access_token()

    @staticmethod
    def check_session_status() -> dict:
        """
        Check current session status including timeout and idle conditions.
        
        Returns:
            Dict with keys:
            - 'is_valid': bool - session is valid and active
            - 'is_idle_timeout': bool - idle timeout exceeded
            - 'is_absolute_timeout': bool - absolute session timeout exceeded
            - 'is_token_invalid': bool - token validation failed
            - 'is_expiration_warning': bool - session about to expire
            - 'idle_duration_minutes': float - minutes since last activity
            - 'session_duration_minutes': float - total session duration
            - 'message': str - human-readable status message
        """
        SessionManager._initialize_session_tracking()
        
        if not st.session_state.get("is_authenticated"):
            return {
                "is_valid": False,
                "is_idle_timeout": False,
                "is_absolute_timeout": False,
                "is_token_invalid": False,
                "is_expiration_warning": False,
                "idle_duration_minutes": 0.0,
                "session_duration_minutes": 0.0,
                "message": "Not authenticated"
            }

        # Update activity on each check (user is interacting)
        SessionManager._update_activity()

        # Check token validity
        try:
            from waterfall_guard.auth_session import _validate_jwt_token
            user = st.session_state.get("user", {})
            _validate_jwt_token(user.get("access_token", ""))
        except Exception as e:
            logger.warning(f"Token validation failed: {e}")
            return {
                "is_valid": False,
                "is_idle_timeout": False,
                "is_absolute_timeout": False,
                "is_token_invalid": True,
                "is_expiration_warning": False,
                "idle_duration_minutes": 0.0,
                "session_duration_minutes": 0.0,
                "message": "Token is invalid or expired"
            }

        # Check idle timeout
        idle_duration = SessionManager._get_idle_duration()
        idle_timeout = timedelta(minutes=IDLE_TIMEOUT_MINUTES)
        is_idle_timeout = idle_duration > idle_timeout

        # Check absolute session timeout
        session_duration = SessionManager._get_session_duration()
        session_timeout = timedelta(minutes=SESSION_TIMEOUT_MINUTES)
        is_absolute_timeout = session_duration > session_timeout

        # Check expiration warning
        idle_warning_threshold = timedelta(minutes=IDLE_TIMEOUT_MINUTES - SESSION_WARNING_THRESHOLD_MINUTES)
        is_expiration_warning = (
            idle_duration > idle_warning_threshold and 
            not is_idle_timeout and 
            not st.session_state.get("session_expiration_warning_shown")
        )

        is_valid = not (is_idle_timeout or is_absolute_timeout)
        
        if is_idle_timeout:
            message = f"Session expired due to inactivity ({IDLE_TIMEOUT_MINUTES} minutes)"
        elif is_absolute_timeout:
            message = f"Session expired (maximum duration: {SESSION_TIMEOUT_MINUTES} minutes)"
        elif is_expiration_warning:
            remaining = (idle_timeout - idle_duration).total_seconds() / 60
            message = f"Session will expire in {remaining:.0f} minute(s) due to inactivity"
        elif is_valid:
            message = "Session active"
        else:
            message = "Unknown session state"

        return {
            "is_valid": is_valid,
            "is_idle_timeout": is_idle_timeout,
            "is_absolute_timeout": is_absolute_timeout,
            "is_token_invalid": False,
            "is_expiration_warning": is_expiration_warning,
            "idle_duration_minutes": idle_duration.total_seconds() / 60,
            "session_duration_minutes": session_duration.total_seconds() / 60,
            "message": message
        }

    @staticmethod
    def end_session():
        """Terminate the current session and clear all session data."""
        try:
            client = SessionManager._get_supabase_client()
            if client:
                client.auth.sign_out()
        except Exception as e:
            logger.warning(f"Error during sign out: {e}")

        # Clear session state
        st.session_state.is_authenticated = False
        st.session_state.user = None
        st.session_state.session_initialized = False
        st.session_state.session_start_time = None
        st.session_state.last_activity_time = None
        st.session_state.token_refresh_attempted = False
        st.session_state.session_expiration_warning_shown = False

    @staticmethod
    def show_session_warning():
        """Display a session expiration warning in the UI."""
        st.session_state.session_expiration_warning_shown = True
        st.warning(
            f"⏱️ Your session will expire in {SESSION_WARNING_THRESHOLD_MINUTES} minute(s) due to inactivity. "
            f"Click anywhere to refresh your session.",
            icon="⏱️"
        )

    @staticmethod
    def show_session_expired_message():
        """Display session expired message and prompt to login."""
        st.error(
            "🔒 Your session has expired. Please log in again to continue.",
            icon="🔒"
        )


def require_valid_session() -> bool:
    """
    Check session validity and handle expired/invalid sessions.
    
    Call this at the top of Streamlit pages that require authentication.
    Automatically handles token refresh and session timeout.
    
    Returns:
        True if session is valid, False if user should be logged out.
    """
    SessionManager._initialize_session_tracking()
    
    # Check and refresh token if needed
    SessionManager.check_and_refresh_token()
    
    # Get current session status
    status = SessionManager.check_session_status()
    
    if not status["is_valid"]:
        SessionManager.end_session()
        SessionManager.show_session_expired_message()
        st.stop()
        return False
    
    # Show warning if close to expiration
    if status["is_expiration_warning"]:
        SessionManager.show_session_warning()
    
    return True


# Decorator for protecting pages that require valid sessions
def require_session(func: Callable) -> Callable:
    """Decorator to ensure valid session before executing page function."""
    def wrapper(*args, **kwargs):
        if not require_valid_session():
            return
        return func(*args, **kwargs)
    return wrapper
