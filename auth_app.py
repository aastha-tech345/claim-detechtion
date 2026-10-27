"""
Waterfall Guard Authentication App
User signup, login, and dashboard access
"""

import os
from dotenv import load_dotenv

# Load .env file at the very beginning - BEFORE other imports
load_dotenv()

import streamlit as st
import pandas as pd
import plotly.express as px
from waterfall_guard.auth import (
    initialize_session_state,
    signup_user,
    login_user,
    logout_user,
    get_current_user,
    is_user_authenticated,
    get_auth_client,
)

# Page config
st.set_page_config(
    page_title="Waterfall Guard - Revenue Recovery",
    page_icon="🦅",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Initialize session
initialize_session_state()

# Custom CSS
st.markdown("""
<style>
    .auth-container {
        max-width: 400px;
        margin: 50px auto;
        padding: 30px;
        border-radius: 10px;
        background-color: #f9f8f5;
        box-shadow: 0 2px 10px rgba(0,0,0,0.1);
    }
    .header {
        text-align: center;
        margin-bottom: 30px;
    }
    .success {
        padding: 15px;
        border-radius: 5px;
        background-color: #d4edda;
        color: #155724;
        border: 1px solid #c3e6cb;
    }
    .error {
        padding: 15px;
        border-radius: 5px;
        background-color: #f8d7da;
        color: #721c24;
        border: 1px solid #f5c6cb;
    }
</style>
""", unsafe_allow_html=True)


def render_login_page():
    """Render login form."""
    st.markdown("""
    <div class="auth-container">
        <div class="header">
            <h1>🦅 Waterfall Guard</h1>
            <p>Healthcare Revenue Recovery Analytics</p>
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1, 2, 1])
    
    with col2:
        st.subheader("Login")
        
        email = st.text_input("📧 Email", key="login_email")
        password = st.text_input("🔐 Password", type="password", key="login_password")
        
        col_login, col_signup = st.columns(2)
        
        with col_login:
            if st.button("Login", use_container_width=True, type="primary"):
                if not email or not password:
                    st.error("❌ Please enter email and password")
                else:
                    success, message, user_data = login_user(email, password)
                    
                    if success:
                        st.session_state.is_authenticated = True
                        st.session_state.user = user_data
                        st.session_state.page = "dashboard"
                        st.success(message)
                        st.rerun()
                    else:
                        st.error(message)
        
        with col_signup:
            if st.button("Sign Up", use_container_width=True):
                st.session_state.page = "signup"
                st.rerun()
        
        # Demo credentials info
        with st.expander("ℹ️ Demo Credentials"):
            st.info("""
            **For Testing:**
            - Email: demo@waterfall.local
            - Password: demo123456
            """)


def render_signup_page():
    """Render signup form."""
    st.markdown("""
    <div class="auth-container">
        <div class="header">
            <h1>🦅 Waterfall Guard</h1>
            <p>Healthcare Revenue Recovery Analytics</p>
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1, 2, 1])
    
    with col2:
        st.subheader("Create Account")
        
        email = st.text_input("📧 Email Address", key="signup_email")
        password = st.text_input("🔐 Password (min 6 chars)", type="password", key="signup_password")
        password_confirm = st.text_input("🔐 Confirm Password", type="password", key="signup_password_confirm")
        organization_name = st.text_input("🏢 Organization Name", key="org_name")
        tenant_id = st.text_input("🆔 Tenant ID (lowercase, no spaces)", key="tenant_id")
        
        col_signup, col_back = st.columns(2)
        
        with col_signup:
            if st.button("Sign Up", use_container_width=True, type="primary"):
                # Validation
                if not email or not password or not password_confirm or not organization_name or not tenant_id:
                    st.error("❌ Please fill all fields")
                elif password != password_confirm:
                    st.error("❌ Passwords don't match")
                elif len(password) < 6:
                    st.error("❌ Password must be at least 6 characters")
                elif "@" not in email:
                    st.error("❌ Invalid email format")
                elif " " in tenant_id or tenant_id != tenant_id.lower():
                    st.error("❌ Tenant ID must be lowercase with no spaces")
                else:
                    success, message = signup_user(email, password, tenant_id, organization_name)
                    
                    if success:
                        st.success(message)
                        st.info("📧 Check your email to verify your account, then login")
                        st.session_state.page = "login"
                        st.rerun()
                    else:
                        st.error(message)
        
        with col_back:
            if st.button("Back to Login", use_container_width=True):
                st.session_state.page = "login"
                st.rerun()


def render_dashboard():
    """Render main dashboard after login."""
    user = get_current_user()
    
    # Sidebar with user info
    with st.sidebar:
        st.markdown("### 👤 User Profile")
        st.write(f"**Email:** {user.get('email')}")
        if user.get('organization_name'):
            st.write(f"**Organization:** {user.get('organization_name')}")
        st.write(f"**Tenant ID:** {user.get('tenant_id')}")
        
        st.divider()
        
        if st.button("🚪 Logout", use_container_width=True):
            logout_user()
            st.session_state.is_authenticated = False
            st.session_state.user = None
            st.session_state.page = "login"
            st.rerun()
    
    # Main dashboard content
    st.title("🦅 Waterfall Guard Dashboard")
    st.subheader("Healthcare Revenue Recovery Analytics")
    
    # Fetch claims data
    try:
        client = get_auth_client()
        response = client.table("claim_diagnostics").select("*").order("created_at", desc=True).limit(5000).execute()
        
        if response.data:
            df = pd.DataFrame(response.data)
            
            # Convert financial_impact to numeric
            df["financial_impact"] = pd.to_numeric(df["financial_impact"], errors="coerce").fillna(0.0)
            
            # Calculate metrics
            total_claims = len(df)
            total_impact = df["financial_impact"].sum()
            resolved_claims = len(df[df["waterfall_stage"] == "Resolved"])
            recovery_rate = (resolved_claims / total_claims * 100) if total_claims > 0 else 0
            
            # Display metrics
            col1, col2, col3 = st.columns(3)
            
            with col1:
                st.metric("Total Claims", f"{total_claims:,}", "claims processed")
            
            with col2:
                st.metric("Financial Impact", f"${total_impact:,.2f}", "at risk")
            
            with col3:
                st.metric("Recovery Rate", f"{recovery_rate:.1f}%", "resolved")
            
            st.divider()
            
            # Waterfall Stage Distribution
            col1, col2 = st.columns(2)
            
            with col1:
                stage_counts = df["waterfall_stage"].value_counts()
                fig_stage = px.pie(
                    values=stage_counts.values,
                    names=stage_counts.index,
                    title="Claims by Waterfall Stage",
                    hole=0.3
                )
                st.plotly_chart(fig_stage, use_container_width=True)
            
            with col2:
                # Financial Impact by Stage
                stage_impact = df.groupby("waterfall_stage")["financial_impact"].sum().sort_values(ascending=False)
                fig_impact = px.bar(
                    x=stage_impact.index,
                    y=stage_impact.values,
                    title="Financial Impact by Stage",
                    labels={"y": "Amount ($)", "x": "Stage"}
                )
                st.plotly_chart(fig_impact, use_container_width=True)
            
            st.divider()
            
            # Recent Claims Table
            st.subheader("📋 Recent Claims")
            display_df = df[["token_id", "waterfall_stage", "financial_impact", "created_at"]].head(20)
            display_df.columns = ["Claim ID", "Stage", "Financial Impact", "Created"]
            st.dataframe(display_df, use_container_width=True)
            
        else:
            st.info("📭 No claims data available yet. Please load dummy data first.")
            st.code("python3 scripts/load_dummy_data.py")
            
    except Exception as e:
        st.error(f"❌ Error loading data: {e}")
        st.info("💡 Try disabling RLS on claim_diagnostics table in Supabase")


def main():
    """Main app entry point."""
    
    if is_user_authenticated():
        render_dashboard()
    else:
        if st.session_state.page == "signup":
            render_signup_page()
        else:
            render_login_page()


if __name__ == "__main__":
    main()
