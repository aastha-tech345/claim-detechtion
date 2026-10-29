"""
Waterfall Guard Authentication App
User signup, login, and dashboard access
"""

import os
from dotenv import load_dotenv

# Load .env file at the very beginning - BEFORE other imports
load_dotenv()

# Disable SSL verification for development (if configured)
# This must be done BEFORE importing requests/urllib3
if os.getenv("SSL_VERIFY", "true").lower() == "false":
    import ssl
    import urllib3
    
    ssl._create_default_https_context = ssl._create_unverified_context
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

import streamlit as st
import pandas as pd
import plotly.express as px
from io import BytesIO
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from datetime import datetime
from waterfall_guard.auth import (
    initialize_session_state,
    signup_user,
    login_user,
    logout_user,
    get_current_user,
    is_user_authenticated,
    get_auth_client,
)
from waterfall_guard.session_manager import (
    SessionManager,
    require_valid_session,
)

# Page config
st.set_page_config(
    page_title="Waterfall Guard - Revenue Recovery",
    page_icon="🦅",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Initialize session (only on first load)
if "initialized" not in st.session_state:
    initialize_session_state()
    st.session_state.initialized = True

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


def generate_csv(df):
    """Generate CSV file from dataframe."""
    csv_buffer = BytesIO()
    df.to_csv(csv_buffer, index=False)
    csv_buffer.seek(0)
    return csv_buffer.getvalue()


def generate_pdf(df, metrics, user):
    """Generate PDF report from dataframe and metrics."""
    pdf_buffer = BytesIO()
    doc = SimpleDocTemplate(
        pdf_buffer,
        pagesize=letter,
        rightMargin=0.5*inch,
        leftMargin=0.5*inch,
        topMargin=0.5*inch,
        bottomMargin=0.5*inch
    )
    
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=24,
        textColor=colors.HexColor('#1f77b4'),
        spaceAfter=10,
        fontName='Helvetica-Bold'
    )
    heading_style = ParagraphStyle(
        'CustomHeading',
        parent=styles['Heading2'],
        fontSize=14,
        textColor=colors.HexColor('#1f77b4'),
        spaceAfter=8,
        fontName='Helvetica-Bold'
    )
    
    elements = []
    
    # Title
    elements.append(Paragraph("🦅 Waterfall Guard - Healthcare Revenue Recovery Report", title_style))
    elements.append(Spacer(1, 0.2*inch))
    
    # Metadata
    metadata_style = styles['Normal']
    elements.append(Paragraph(f"<b>Generated:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", metadata_style))
    elements.append(Paragraph(f"<b>Organization:</b> {user.get('organization_name', 'N/A')}", metadata_style))
    elements.append(Paragraph(f"<b>Tenant ID:</b> {user.get('tenant_id', 'N/A')}", metadata_style))
    elements.append(Spacer(1, 0.2*inch))
    
    # Key Metrics
    elements.append(Paragraph("Key Metrics", heading_style))
    metrics_data = [
        ["Metric", "Value"],
        ["Total Claims", f"{metrics['total_claims']:,}"],
        ["Financial Impact", f"${metrics['total_impact']:,.2f}"],
        ["Resolved Claims", f"{metrics['resolved_claims']:,}"],
        ["Recovery Rate", f"{metrics['recovery_rate']:.1f}%"]
    ]
    metrics_table = Table(metrics_data, colWidths=[3*inch, 2*inch])
    metrics_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1f77b4')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 12),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('GRID', (0, 0), (-1, -1), 1, colors.black)
    ]))
    elements.append(metrics_table)
    elements.append(Spacer(1, 0.3*inch))
    
    # Claims Data
    elements.append(PageBreak())
    elements.append(Paragraph("Detailed Claims Data", heading_style))
    elements.append(Spacer(1, 0.1*inch))
    
    # Prepare table data
    table_data = [df.columns.tolist()]
    for row in df.head(100).values:
        table_data.append([str(val) for val in row])
    
    claims_table = Table(table_data, colWidths=[1.2*inch]*len(df.columns))
    claims_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1f77b4')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.lightgrey),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.lightgrey])
    ]))
    elements.append(claims_table)
    
    doc.build(elements)
    pdf_buffer.seek(0)
    return pdf_buffer.getvalue()


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
                        # Initialize session tracking on successful login
                        SessionManager._initialize_session_tracking()
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
    
    # Validate session and check for timeout
    if not require_valid_session():
        st.session_state.page = "login"
        st.rerun()
    
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
            
            # Recent Claims Table with Download Options
            col_title, col_export, col_btn, col_spacer = st.columns([3, 0.8, 0.6, 0.6])
            
            with col_title:
                st.subheader("📋 Recent Claims")
            
            with col_export:
                st.write("")  # Spacer for alignment
                recent_format = st.selectbox(
                    "Format",
                    ["Select Format", "CSV", "PDF"],
                    key="recent_format_select",
                    label_visibility="collapsed"
                )
            
            with col_btn:
                st.write("")  # Spacer for alignment
                if recent_format != "Select Format":
                    display_df = df[["token_id", "waterfall_stage", "financial_impact", "created_at"]].head(20)
                    display_df.columns = ["Claim ID", "Stage", "Financial Impact", "Created"]
                    
                    if recent_format == "CSV":
                        csv_data = generate_csv(display_df)
                        st.download_button(
                            label="Download",
                            data=csv_data,
                            file_name=f"recent_claims_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                            mime="text/csv",
                            key="csv_download_btn",
                            use_container_width=True
                        )
                    elif recent_format == "PDF":
                        pdf_data = generate_pdf(display_df, {
                            'total_claims': len(display_df),
                            'total_impact': pd.to_numeric(display_df["Financial Impact"], errors="coerce").sum(),
                            'resolved_claims': len(display_df[display_df["Stage"] == "Resolved"]),
                            'recovery_rate': (len(display_df[display_df["Stage"] == "Resolved"]) / len(display_df) * 100) if len(display_df) > 0 else 0
                        }, user)
                        st.download_button(
                            label="Download",
                            data=pdf_data,
                            file_name=f"recent_claims_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf",
                            mime="application/pdf",
                            key="pdf_download_btn",
                            use_container_width=True
                        )
            
            with col_spacer:
                pass
            
            # Hide download icon in dataframe toolbar
            st.markdown("""
            <style>
                button[kind="secondary"][data-testid="stDownloadButton"] {
                    display: none !important;
                }
                [data-testid="stDataFrameDownloadButton"] {
                    display: none !important;
                }
            </style>
            """, unsafe_allow_html=True)
            
            display_df = df[["token_id", "waterfall_stage", "financial_impact", "created_at"]].head(20)
            display_df.columns = ["Claim ID", "Stage", "Financial Impact", "Created"]
            st.dataframe(display_df, use_container_width=True, hide_index=False)
            
        else:
            st.info("📭 No claims data available yet. Please load dummy data first.")
            st.code("python3 scripts/load_dummy_data.py")
            
    except Exception as e:
        st.error(f"❌ Error loading data: {e}")
        st.info("💡 Try disabling RLS on claim_diagnostics table in Supabase")


def main():
    """Main app entry point."""
    
    # Handle redirect from dashboard with ?page=auth query param
    if st.query_params.get("page") == "auth":
        st.session_state.page = "login"
        st.query_params.clear()
    
    if is_user_authenticated():
        render_dashboard()
    else:
        if st.session_state.page == "signup":
            render_signup_page()
        else:
            render_login_page()


if __name__ == "__main__":
    main()
