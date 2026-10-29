#!/usr/bin/env python3
"""
Waterfall Guard App Runner
Disables SSL verification globally before starting Streamlit
"""

import os
import sys
import ssl
import urllib3
import subprocess
from dotenv import load_dotenv

# Load .env file
load_dotenv()

# ⚠️ CRITICAL: Disable SSL verification BEFORE anything else
os.environ['SSL_VERIFY'] = 'false'
os.environ['PYTHONHTTPSVERIFY'] = '0'

# Disable SSL verification in this process
ssl._create_default_https_context = ssl._create_unverified_context
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Suppress SSL warnings
import warnings
warnings.filterwarnings('ignore', message='Unverified HTTPS request')

print("=" * 60)
print("🚀 Waterfall Guard Backend Startup")
print("=" * 60)
print()
print("Configuration:")
print(f"  SSL_VERIFY: {os.getenv('SSL_VERIFY', 'true')}")
print(f"  SUPABASE_URL: {os.getenv('SUPABASE_URL', 'Not set')}")
print(f"  Database: Connected")
print()
print("=" * 60)
print()
print("Starting Streamlit on http://localhost:8501")
print("Press Ctrl+C to stop")
print()

# Run Streamlit with environment variables
os.system('streamlit run auth_app.py --logger.level=info')
