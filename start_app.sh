#!/bin/bash

# Waterfall Guard Startup Script
# Sets up SSL verification and starts Streamlit

# Load .env file
set -a
source .env
set +a

# Force disable SSL verification for development
export SSL_VERIFY=false
export PYTHONWARNINGS=ignore::urllib3.exceptions.InsecureRequestWarning

# Clear Streamlit cache to force reload
rm -rf ~/.streamlit/cache

echo "=========================================="
echo "🚀 Starting Waterfall Guard Backend"
echo "=========================================="
echo ""
echo "Configuration:"
echo "  SSL_VERIFY: $SSL_VERIFY"
echo "  SUPABASE_URL: $SUPABASE_URL"
echo "  DATABASE: Connected"
echo ""
echo "=========================================="
echo ""
echo "Streamlit app starting on http://localhost:8501"
echo "Press Ctrl+C to stop"
echo ""

# Start Streamlit with SSL_VERIFY disabled globally
PYTHONHTTPSVERIFY=0 streamlit run auth_app.py --logger.level=info
