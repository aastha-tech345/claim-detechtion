#!/usr/bin/env python3
"""
Load dummy claims data into Supabase for testing
Associated with specific tenants
"""

import os
from dotenv import load_dotenv
from datetime import datetime, timedelta, timezone
import random
import uuid
from supabase import create_client

load_dotenv()

def get_supabase_client():
    """Get Supabase client with anon key (simpler approach)."""
    supabase_url = os.getenv("SUPABASE_URL")
    anon_key = os.getenv("SUPABASE_ANON_KEY")
    
    if not supabase_url or not anon_key:
        print("❌ SUPABASE_URL or ANON_KEY not set")
        exit(1)
    
    return create_client(supabase_url, anon_key)

def generate_dummy_claims(tenant_id: str, n=50):
    """Generate dummy claim data for a specific tenant."""
    waterfall_stages = ["Pending", "In Review", "Appealed", "Resolved", "Denied"]
    deadlock_types = ["BILLING", "AUTHORIZATION", "COVERAGE", "DOCUMENTATION", "CLINICAL"]
    
    claims = []
    
    for i in range(n):
        token_id = f"{tenant_id}_hash_{uuid.uuid4().hex[:12]}"
        
        claim = {
            "token_id": token_id,
            "waterfall_stage": random.choice(waterfall_stages),
            "deadlock_types": random.sample(deadlock_types, random.randint(1, 3)),
            "active_hold_names": [f"Hold_{j}" for j in range(random.randint(0, 2))],
            "eligible_wq_ids": [f"WQ_{j}" for j in range(random.randint(1, 3))],
            "unassigned_wq_ids": [f"UWQ_{j}" for j in range(random.randint(0, 2))],
            "financial_impact": round(random.uniform(100, 50000), 2),
            "filing_deadline": (datetime.now(timezone.utc) + timedelta(days=random.randint(1, 90))).isoformat(),
            "created_at": (datetime.now(timezone.utc) - timedelta(days=random.randint(0, 30))).isoformat(),
        }
        
        claims.append(claim)
    
    return claims

def load_claims_for_tenant(client, tenant_id: str, organization_name: str, n=50):
    """Load claims for a specific tenant."""
    print(f"\n📊 Generating {n} claims for {organization_name} ({tenant_id})...")
    
    claims = generate_dummy_claims(tenant_id, n)
    
    try:
        response = client.table("claim_diagnostics").insert(claims).execute()
        total_impact = sum(c.get('financial_impact', 0) for c in response.data)
        
        print(f"✅ Loaded {len(response.data)} claims")
        print(f"   💰 Financial Impact: ${total_impact:,.2f}")
        print(f"   📈 Stages: {set(c['waterfall_stage'] for c in response.data)}")
        
        return len(response.data)
    except Exception as e:
        print(f"❌ Error: {e}")
        return 0

def main():
    """Main entry point."""
    print("=" * 70)
    print("🚀 Loading Tenant-Specific Dummy Claims Data")
    print("=" * 70)
    
    client = get_supabase_client()
    
    # Get all organizations from database
    print("\n📋 Fetching organizations from database...")
    
    try:
        orgs_response = client.table("client_configurations").select("tenant_id,organization_name").execute()
        organizations = orgs_response.data
        
        if not organizations:
            print("❌ No organizations found in database!")
            print("   Please create at least one organization first via signup")
            exit(1)
        
        print(f"✅ Found {len(organizations)} organization(s)")
        
    except Exception as e:
        print(f"❌ Error fetching organizations: {e}")
        exit(1)
    
    # Load data for each organization
    total_claims = 0
    total_impact = 0.0
    
    for org in organizations:
        tenant_id = org["tenant_id"]
        org_name = org["organization_name"]
        
        claims = generate_dummy_claims(tenant_id, n=50)
        
        try:
            response = client.table("claim_diagnostics").insert(claims).execute()
            count = len(response.data)
            impact = sum(c.get('financial_impact', 0) for c in response.data)
            
            total_claims += count
            total_impact += impact
            
            print(f"\n✅ {org_name}")
            print(f"   • Claims: {count}")
            print(f"   • Financial Impact: ${impact:,.2f}")
            
        except Exception as e:
            print(f"\n❌ Error loading data for {org_name}: {e}")
    
    # Summary
    print("\n" + "=" * 70)
    print("📊 SUMMARY")
    print("=" * 70)
    print(f"Total Claims Loaded: {total_claims}")
    print(f"Total Financial Impact: ${total_impact:,.2f}")
    print(f"Organizations: {len(organizations)}")
    print("\n✅ Dummy data loaded successfully!")
    print("=" * 70)
    print("\n📊 Next Steps:")
    print("   1. Restart dashboard: streamlit run auth_app.py")
    print("   2. Login with your credentials")
    print("   3. See tenant-specific data on dashboard!")

if __name__ == "__main__":
    main()

