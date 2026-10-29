"""
Authentication and authorization utilities for Waterfall Guard.
Integrates with Supabase Auth for user signup, login, and session management.
Uses browser localStorage for persistent sessions across page refreshes.
"""

import os
import json
import base64
from typing import Optional, Tuple
from datetime import datetime, timezone

# ⚠️ CRITICAL: Disable SSL verification BEFORE any other imports
# This must be done before importing requests, urllib3, or supabase
if os.getenv("SSL_VERIFY", "true").lower() == "false":
    import ssl
    import urllib3
    
    # Disable SSL verification globally
    ssl._create_default_https_context = ssl._create_unverified_context
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    
    # Also set environment variables for requests library
    os.environ['PYTHONHTTPSVERIFY'] = '0'

import streamlit as st
from supabase import create_client
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


def get_auth_client():
    """Get Supabase client for authentication.
    
    Supports SSL_VERIFY env var to disable SSL verification for development/testing
    with self-signed certificates. Set SSL_VERIFY=false to disable.
    """
    import urllib3
    import requests
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry
    
    supabase_url = os.getenv("SUPABASE_URL")
    anon_key = os.getenv("SUPABASE_ANON_KEY")
    ssl_verify = os.getenv("SSL_VERIFY", "true").lower() != "false"
    
    if not supabase_url or not anon_key:
        st.error("❌ Supabase credentials not configured in .env")
        st.stop()
    
    # Disable SSL verification globally if needed (development/testing only)
    if not ssl_verify:
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        requests.packages.urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        
        # Disable SSL verification for all Python requests globally
        import ssl
        ssl._create_default_https_context = ssl._create_unverified_context
    
    # Create client
    client = create_client(supabase_url, anon_key)
    
    # Also set verify=False on the client's internal session if accessible
    try:
        if hasattr(client, '_client'):
            client._client.verify = False
        if hasattr(client, 'postgrest'):
            if hasattr(client.postgrest, '_session'):
                client.postgrest._session.verify = False
            if hasattr(client.postgrest, 'session'):
                client.postgrest.session.verify = False
        if hasattr(client, 'auth'):
            if hasattr(client.auth, '_session'):
                client.auth._session.verify = False
            if hasattr(client.auth, 'session'):
                client.auth.session.verify = False
    except Exception as e:
        print(f"Warning: Could not configure SSL verification: {e}")
    
    return client


def save_auth_to_storage(user_data: dict):
    """Save auth data to browser localStorage via JavaScript."""
    data_json = json.dumps(user_data)
    data_b64 = base64.b64encode(data_json.encode()).decode()
    
    st.markdown(f"""
    <script>
        localStorage.setItem('wg_auth_data', '{data_b64}');
    </script>
    """, unsafe_allow_html=True)


def load_auth_from_storage():
    """Load auth data from browser localStorage via JavaScript."""
    st.markdown("""
    <script>
        let authData = localStorage.getItem('wg_auth_data');
        if (authData) {
            window.parent.postMessage({type: 'auth_data', data: authData}, '*');
        }
    </script>
    """, unsafe_allow_html=True)


def signup_user(email: str, password: str, tenant_id: str, organization_name: str) -> Tuple[bool, str]:
    """
    Sign up a new user with email and password.
    
    Args:
        email: User's email address
        password: User's password (min 6 chars)
        tenant_id: Organization identifier
        organization_name: Organization name
    
    Returns:
        (success: bool, message: str)
    """
    try:
        # Use anon client for auth and database
        client = get_auth_client()
        
        # Create auth user
        response = client.auth.sign_up({
            "email": email,
            "password": password,
        })
        
        if response.user:
            user_id = response.user.id
            
            # Create client configuration entry (anon key)
            config_data = {
                "user_id": user_id,
                "tenant_id": tenant_id,
                "organization_name": organization_name,
                "is_onboarding_completed": False,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            
            try:
                client.table("client_configurations").insert(config_data).execute()
            except Exception as db_error:
                # Even if DB insert fails, user is created in auth
                print(f"Warning: Could not save config: {db_error}")
            
            return True, f"✅ User created! Verification email sent to {email}"
        else:
            return False, "❌ Failed to create user account"
            
    except Exception as e:
        error_msg = str(e)
        if "already registered" in error_msg.lower():
            return False, "❌ This email is already registered"
        elif "password" in error_msg.lower():
            return False, "❌ Password must be at least 6 characters"
        return False, f"❌ Signup failed: {error_msg}"


def login_user(email: str, password: str) -> Tuple[bool, str, Optional[dict]]:
    """
    Log in an existing user.
    
    Args:
        email: User's email
        password: User's password
    
    Returns:
        (success: bool, message: str, user_data: dict or None)
    """
    try:
        client = get_auth_client()
        
        response = client.auth.sign_in_with_password({
            "email": email,
            "password": password,
        })
        
        if response.user and response.session:
            user_id = response.user.id
            
            # Store tokens in session state
            st.session_state.access_token = response.session.access_token
            st.session_state.refresh_token = response.session.refresh_token
            st.session_state.user_id = user_id
            
            # Get user's organization config
            user_data = {
                "user_id": user_id,
                "email": email,
                "tenant_id": None,
                "organization_name": None,
                "access_token": response.session.access_token,
                "refresh_token": response.session.refresh_token
            }
            
            try:
                config_response = client.table("client_configurations").select(
                    "*"
                ).eq("user_id", user_id).execute()
                
                if config_response.data:
                    config = config_response.data[0]
                    user_data["tenant_id"] = config.get("tenant_id")
                    user_data["organization_name"] = config.get("organization_name")
            except:
                pass
            
            # Save to browser storage
            save_auth_to_storage(user_data)
            
            return True, "✅ Login successful", user_data
        else:
            return False, "❌ Invalid email or password", None
            
    except Exception as e:
        return False, f"❌ Login failed: {str(e)}", None


def logout_user() -> bool:
    """Log out current user."""
    try:
        client = get_auth_client()
        client.auth.sign_out()
        
        # Clear browser storage
        st.markdown("""
        <script>
            localStorage.removeItem('wg_auth_data');
        </script>
        """, unsafe_allow_html=True)
        
        # Clear session state
        st.session_state.is_authenticated = False
        st.session_state.user = None
        
        return True
    except Exception as e:
        st.error(f"❌ Logout failed: {str(e)}")
        return False


def get_current_user() -> Optional[dict]:
    """Get current logged-in user from session state."""
    return st.session_state.get("user", None)


def is_user_authenticated() -> bool:
    """Check if user is currently authenticated."""
    return st.session_state.get("is_authenticated", False)


def get_tenant_id() -> Optional[str]:
    """Get current user's tenant ID."""
    user = get_current_user()
    return user.get("tenant_id") if user else None


def initialize_session_state():
    """Initialize authentication-related session state variables."""
    if "is_authenticated" not in st.session_state:
        st.session_state.is_authenticated = False
    if "user" not in st.session_state:
        st.session_state.user = None
    if "page" not in st.session_state:
        st.session_state.page = "login"  # login, signup, dashboard
    
    # Try to restore session from Supabase auth
    try:
        client = get_auth_client()
        
        # Get the current session from Supabase
        session = client.auth.get_session()
        if session and session.user:
            user_id = session.user.id
            email = session.user.email
            access_token = session.access_token
            refresh_token = session.refresh_token
            
            # Get organization config
            user_data = {
                "user_id": user_id,
                "email": email,
                "tenant_id": None,
                "organization_name": None,
                "access_token": access_token,
                "refresh_token": refresh_token
            }
            
            try:
                config_response = client.table("client_configurations").select(
                    "*"
                ).eq("user_id", user_id).execute()
                
                if config_response.data:
                    config = config_response.data[0]
                    user_data["tenant_id"] = config.get("tenant_id")
                    user_data["organization_name"] = config.get("organization_name")
            except:
                pass
            
            st.session_state.user = user_data
            st.session_state.is_authenticated = True
            st.session_state.page = "dashboard"
    except:
        pass
