"""Integration helpers for auth_app.py to use session management.

Provides utility functions that auth_app.py (and other Streamlit apps) can use
to enforce session timeout and token refresh logic.
"""

import streamlit as st
from waterfall_guard.session_manager import (
    SessionManager,
    require_valid_session,
    require_session,
)


def initialize_auth_app_session():
    """Initialize session state for auth_app.py."""
    if "auth_app_initialized" not in st.session_state:
        st.session_state.auth_app_initialized = True
        # Will be set by login/signup
        if "is_authenticated" not in st.session_state:
            st.session_state.is_authenticated = False
        if "user" not in st.session_state:
            st.session_state.user = None
        if "page" not in st.session_state:
            st.session_state.page = "login"


def handle_authentication_result(success: bool, user_data: dict = None, error_msg: str = ""):
    """
    Handle authentication result from login/signup.
    
    Args:
        success: Whether authentication was successful
        user_data: User data dict if successful
        error_msg: Error message if failed
    """
    if success and user_data:
        st.session_state.is_authenticated = True
        st.session_state.user = user_data
        st.session_state.page = "dashboard"
        # Initialize session tracking
        SessionManager._initialize_session_tracking()
    else:
        st.session_state.is_authenticated = False
        st.session_state.user = None
        if error_msg:
            st.error(error_msg)


def render_protected_page(page_func):
    """
    Render a protected page with session validation.
    
    Args:
        page_func: Function that renders the page content
    """
    if not require_valid_session():
        return
    
    page_func()


def handle_session_timeout_redirect():
    """
    Handle redirect when session times out.
    Clears auth state and redirects to login.
    """
    SessionManager.end_session()
    st.session_state.page = "login"
    st.error("Your session has expired. Please log in again.")
    st.rerun()


def get_session_status_info() -> dict:
    """Get formatted session status information for display."""
    status = SessionManager.check_session_status()
    
    return {
        "is_valid": status["is_valid"],
        "idle_minutes": round(status["idle_duration_minutes"], 1),
        "session_minutes": round(status["session_duration_minutes"], 1),
        "message": status["message"],
        "is_warning": status["is_expiration_warning"],
        "is_expired": not status["is_valid"],
    }


def render_session_info_sidebar():
    """Render session information in sidebar (for development/debugging)."""
    with st.sidebar:
        if st.session_state.get("is_authenticated"):
            st.divider()
            st.caption("📊 Session Info")
            status = get_session_status_info()
            
            col1, col2 = st.columns(2)
            with col1:
                st.metric("Idle (min)", status["idle_minutes"])
            with col2:
                st.metric("Total (min)", status["session_minutes"])
            
            if not status["is_valid"]:
                st.warning("Session expired")
