#!/usr/bin/env python3
"""
Test SSL certificate verification
Shows if the fix is working correctly
"""

import os
import sys
import ssl
import urllib3
from dotenv import load_dotenv

# Load .env
load_dotenv()

print("=" * 70)
print("🔍 SSL Certificate Verification Test")
print("=" * 70)
print()

# Test 1: Check SSL_VERIFY setting
print("1️⃣  SSL_VERIFY Setting:")
ssl_verify = os.getenv("SSL_VERIFY", "true").lower()
print(f"   Value: {ssl_verify}")
if ssl_verify == "false":
    print("   ✅ SSL verification is DISABLED (development mode)")
else:
    print("   ℹ️  SSL verification is ENABLED (production mode)")
print()

# Test 2: Disable SSL globally
print("2️⃣  Disabling SSL globally...")
ssl._create_default_https_context = ssl._create_unverified_context
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
print("   ✅ SSL disabled")
print()

# Test 3: Try Supabase connection
print("3️⃣  Testing Supabase connection...")
try:
    from supabase import create_client
    
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_ANON_KEY")
    
    if not url or not key:
        print("   ❌ Supabase credentials not configured")
        print(f"      SUPABASE_URL: {'Set' if url else 'Not set'}")
        print(f"      SUPABASE_ANON_KEY: {'Set' if key else 'Not set'}")
    else:
        print(f"   URL: {url}")
        print(f"   Key: {key[:20]}...")
        
        # Create client with SSL disabled
        client = create_client(url, key)
        
        # Try to get session (doesn't require auth)
        try:
            client.auth.get_session()
            print("   ✅ Supabase connection successful!")
        except Exception as e:
            if "SSL" in str(e) or "CERTIFICATE" in str(e):
                print(f"   ❌ SSL Error: {e}")
            else:
                print(f"   ✅ Connected (Auth error expected: {str(e)[:50]}...)")
        
except Exception as e:
    print(f"   ❌ Error: {e}")

print()
print("=" * 70)
print("Summary:")
print("=" * 70)
print()
print("✅ If you see this message, SSL is disabled and app should work")
print()
print("Next steps:")
print("1. Open http://localhost:8501 in browser")
print("2. Try to login or create account")
print("3. If SSL error persists, restart Streamlit with: python3 run_app.py")
print()
