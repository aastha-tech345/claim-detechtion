"""
Authentication and authorization utilities for Waterfall Guard.
Integrates with Supabase Auth for user signup, login, and session management.
"""

import os
from typing import Optional, Tuple
from datetime import datetime, timezone
import streamlit as st
from supabase import create_client
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


def get_auth_client():
    """Get Supabase client for authentication."""
    supabase_url = os.getenv("SUPABASE_URL")
    anon_key = os.getenv("SUPABASE_ANON_KEY")
    
    if not supabase_url or not anon_key:
        st.error("❌ Supabase credentials not configured in .env")
        st.stop()
    
    return create_client(supabase_url, anon_key)


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
        
        if response.user:
            user_id = response.user.id
            
            # Get user's organization config (anon key only)
            try:
                config_response = client.table("client_configurations").select(
                    "*"
                ).eq("user_id", user_id).execute()
                
                if config_response.data:
                    config = config_response.data[0]
                    return True, "✅ Login successful", {
                        "user_id": user_id,
                        "email": email,
                        "tenant_id": config.get("tenant_id"),
                        "organization_name": config.get("organization_name"),
                        "session": response.session.dict() if response.session else None
                    }
            except:
                # RLS might block, but user is still authenticated
                pass
            
            return True, "✅ Login successful", {
                "user_id": user_id,
                "email": email,
                "tenant_id": None,
                "organization_name": None,
            }
        else:
            return False, "❌ Invalid email or password", None
            
    except Exception as e:
        return False, f"❌ Login failed: {str(e)}", None


def logout_user() -> bool:
    """Log out current user."""
    try:
        client = get_auth_client()
        client.auth.sign_out()
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
