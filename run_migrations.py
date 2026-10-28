#!/usr/bin/env python3
"""
Migration runner for E3, E4, E5 database schema updates.

This script applies all pending Alembic migrations and executes Supabase SQL migrations
to prepare the database for E3 (relationships), E4 (successors), and E5 (audit) support.

Usage:
    python3 run_migrations.py

Requirements:
    - DATABASE_URL environment variable must be set (.env file)
    - Supabase service role key configured
    - alembic package installed
"""

import os
import sys
import logging
from pathlib import Path
from datetime import datetime

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def run_alembic_migrations():
    """Run Alembic migrations for local/PostgreSQL databases."""
    logger.info("=" * 80)
    logger.info("Starting Alembic Migrations for E3, E4, E5")
    logger.info("=" * 80)
    
    # Import alembic config
    try:
        from alembic.config import Config
        from alembic import command
    except ImportError:
        logger.error("❌ alembic package not installed. Install with: pip install alembic")
        return False
    
    # Check DATABASE_URL
    database_url = os.getenv('DATABASE_URL')
    if not database_url:
        logger.error("❌ DATABASE_URL not set. Please configure in .env file")
        return False
    
    logger.info(f"✓ DATABASE_URL configured: {database_url[:50]}...")
    
    # Setup Alembic
    try:
        config = Config("alembic.ini")
        config.set_main_option("sqlalchemy.url", database_url)
        
        logger.info("Running: alembic upgrade head")
        command.upgrade(config, "head")
        logger.info("✅ Alembic migrations completed successfully")
        return True
    except Exception as e:
        logger.error(f"❌ Alembic migration failed: {e}")
        return False


def run_supabase_sql_migrations():
    """Execute Supabase-specific SQL migrations via psycopg2."""
    logger.info("\n" + "=" * 80)
    logger.info("Starting Supabase SQL Migrations for E3 (Relationships Table)")
    logger.info("=" * 80)
    
    database_url = os.getenv('DATABASE_URL')
    if not database_url:
        logger.error("❌ DATABASE_URL not set")
        return False
    
    try:
        import psycopg2
        from psycopg2.extras import execute_batch
    except ImportError:
        logger.error("❌ psycopg2 package not installed. Install with: pip install psycopg2-binary")
        return False
    
    # Read migrations from supabase/migrations directory
    migrations_dir = Path("supabase/migrations")
    if not migrations_dir.exists():
        logger.error(f"❌ Migrations directory not found: {migrations_dir}")
        return False
    
    # List SQL migration files
    sql_files = sorted(migrations_dir.glob("*.sql"))
    if not sql_files:
        logger.error("❌ No SQL migration files found")
        return False
    
    logger.info(f"Found {len(sql_files)} SQL migration files:")
    for sql_file in sql_files:
        logger.info(f"  - {sql_file.name}")
    
    # Connect and execute migrations
    try:
        conn = psycopg2.connect(database_url)
        cursor = conn.cursor()
        
        # Track migration history
        migration_history = []
        
        # Execute each migration
        for sql_file in sql_files:
            try:
                with open(sql_file, 'r') as f:
                    sql_content = f.read()
                
                logger.info(f"\nExecuting: {sql_file.name}")
                cursor.execute(sql_content)
                conn.commit()
                
                migration_history.append({
                    'file': sql_file.name,
                    'status': '✅ SUCCESS',
                    'timestamp': datetime.now().isoformat()
                })
                logger.info(f"✅ {sql_file.name} executed successfully")
                
            except psycopg2.Error as e:
                logger.warning(f"⚠️  {sql_file.name} - {str(e)[:100]}")
                # If table already exists, that's OK - it means migration was already applied
                if "already exists" in str(e).lower():
                    logger.info(f"   (Table already exists - migration previously applied)")
                    migration_history.append({
                        'file': sql_file.name,
                        'status': '⚠️  ALREADY EXISTS',
                        'timestamp': datetime.now().isoformat()
                    })
                else:
                    logger.error(f"❌ Migration failed: {e}")
                    migration_history.append({
                        'file': sql_file.name,
                        'status': f'❌ ERROR: {str(e)[:50]}',
                        'timestamp': datetime.now().isoformat()
                    })
                conn.rollback()
        
        cursor.close()
        conn.close()
        
        logger.info("\n" + "=" * 80)
        logger.info("SQL Migration Summary:")
        logger.info("=" * 80)
        for record in migration_history:
            logger.info(f"{record['file']:50} {record['status']}")
        
        return True
        
    except psycopg2.OperationalError as e:
        logger.error(f"❌ Failed to connect to database: {e}")
        logger.error("   Please verify DATABASE_URL in .env file")
        return False
    except Exception as e:
        logger.error(f"❌ Unexpected error during SQL migrations: {e}")
        return False


def verify_migrations():
    """Verify that migrations were applied successfully."""
    logger.info("\n" + "=" * 80)
    logger.info("Verifying Migrations")
    logger.info("=" * 80)
    
    database_url = os.getenv('DATABASE_URL')
    if not database_url:
        logger.error("❌ DATABASE_URL not set")
        return False
    
    try:
        import psycopg2
    except ImportError:
        logger.error("❌ psycopg2 not available for verification")
        return False
    
    try:
        conn = psycopg2.connect(database_url)
        cursor = conn.cursor()
        
        # Check for key tables
        tables_to_check = [
            'claim_diagnostics',
            'client_configurations',
            'relationships',  # E3 table
        ]
        
        cursor.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public'
        """)
        existing_tables = [row[0] for row in cursor.fetchall()]
        
        logger.info(f"\nExisting tables in public schema ({len(existing_tables)} total):")
        for table in sorted(existing_tables):
            status = "✅" if table in tables_to_check else "  "
            logger.info(f"  {status} {table}")
        
        # Verify E3 relationships table structure
        if 'relationships' in existing_tables:
            logger.info("\n✅ E3 Relationships Table Status:")
            cursor.execute("""
                SELECT column_name, data_type 
                FROM information_schema.columns 
                WHERE table_name = 'relationships'
                ORDER BY ordinal_position
            """)
            columns = cursor.fetchall()
            for col_name, col_type in columns:
                logger.info(f"   - {col_name}: {col_type}")
            
            # Check indexes
            cursor.execute("""
                SELECT indexname 
                FROM pg_indexes 
                WHERE tablename = 'relationships'
            """)
            indexes = [row[0] for row in cursor.fetchall()]
            logger.info(f"\n✅ Indexes on relationships table ({len(indexes)} total):")
            for idx in indexes:
                logger.info(f"   - {idx}")
        else:
            logger.warning("⚠️  relationships table not found")
        
        cursor.close()
        conn.close()
        return True
        
    except Exception as e:
        logger.error(f"❌ Verification failed: {e}")
        return False


def main():
    """Main migration runner."""
    logger.info("\n")
    logger.info("╔" + "=" * 78 + "╗")
    logger.info("║  E3, E4, E5 Database Migration Runner" + " " * 41 + "║")
    logger.info("║  Applying schema updates for relationship, successor, and audit tracking" + " " * 2 + "║")
    logger.info("╚" + "=" * 78 + "╝")
    
    # Check .env file
    if not os.path.exists('.env'):
        logger.error("❌ .env file not found. Please create it with database credentials.")
        logger.error("   Template available at: .env.example")
        return False
    
    logger.info("✓ .env file found")
    
    # Load environment
    from dotenv import load_dotenv
    load_dotenv()
    
    # Run migrations
    all_success = True
    
    # 1. Alembic migrations (local PostgreSQL)
    alembic_success = run_alembic_migrations()
    all_success = all_success and alembic_success
    
    # 2. Supabase SQL migrations
    supabase_success = run_supabase_sql_migrations()
    all_success = all_success and supabase_success
    
    # 3. Verify
    verify_success = verify_migrations()
    
    # Summary
    logger.info("\n" + "=" * 80)
    logger.info("MIGRATION SUMMARY")
    logger.info("=" * 80)
    logger.info(f"Alembic Migrations:      {'✅ SUCCESS' if alembic_success else '❌ FAILED'}")
    logger.info(f"Supabase SQL Migrations: {'✅ SUCCESS' if supabase_success else '❌ FAILED'}")
    logger.info(f"Verification:            {'✅ SUCCESS' if verify_success else '⚠️  PARTIAL'}")
    logger.info("=" * 80)
    
    if all_success:
        logger.info("\n✅ All migrations completed successfully!")
        logger.info("\nNext steps for E3, E4, E5 verification:")
        logger.info("  1. Update verification documents with migration status")
        logger.info("  2. Fix RLS policy (JWT-based instead of connection-variable)")
        logger.info("  3. Implement pipeline integration for E3/E4")
        logger.info("  4. Add JWT token expiration validation for E5")
        return True
    else:
        logger.error("\n❌ Some migrations failed. Please review the errors above.")
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
