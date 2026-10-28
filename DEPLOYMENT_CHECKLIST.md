# Waterfall Guard E3–E4–E5 Deployment Checklist

**Prepared:** 2026-10-27  
**Target:** Staging Environment  
**Status:** Ready for deployment

---

## Pre-Deployment Verification

### Code Quality

- [x] All 188 tests passing
- [x] No lint errors or warnings
- [x] No import errors
- [x] No syntax errors
- [x] Git history preserved (no force pushes)
- [x] No hard-coded credentials in version control
- [x] No PHI in code or tests

### Security

- [x] E5 authentication hardened (user ID, role, tenant from session)
- [x] Audit logs trustworthy
- [x] Form field "Your name / staff ID" removed
- [x] Environment variables validated
- [x] .env.example uses safe placeholders

### Documentation

- [x] SECURITY_AUDIT_E5.md (vulnerabilities and fixes documented)
- [x] VERIFICATION_SUMMARY.md (implementation status)
- [x] FINAL_STATUS_REPORT.md (complete status)
- [x] This checklist

---

## Step 1: Code Merge (Estimated: 5 minutes)

### Prerequisites
- [ ] All staging tests green (188/188)
- [ ] No uncommitted changes except intentional ones
- [ ] Git main branch is up to date

### Actions
```bash
# Verify current state
git status  # Should show only expected modified/new files
git log -1 --oneline  # Verify on correct branch

# Merge to main
git checkout main
git merge origin/aastha  # Or use GitHub/GitLab PR merge

# Verify merge succeeded
git log --oneline -5  # Should show new commit
git diff main...origin/main  # Should be empty (or show commits to push)

# Push to remote
git push origin main
```

### Verification
- [ ] New commit appears in git log
- [ ] All changes merged cleanly
- [ ] No conflicts
- [ ] Remote updated

---

## Step 2: Environment Setup (Estimated: 5 minutes)

### Staging Server Prerequisites

```bash
# 1. Verify Python version
python3 --version  # Should be 3.10+

# 2. Install dependencies
pip install -r requirements.txt

# 3. Verify new dependencies installed
pip show sqlalchemy alembic reportlab
```

### Environment Variables

```bash
# Copy template
cp .env.example .env

# Edit .env with staging values
nano .env
# Set:
# SUPABASE_URL=<your-staging-supabase-url>
# SUPABASE_ANON_KEY=<your-staging-anon-key>
# SUPABASE_SERVICE_ROLE_KEY=<your-staging-service-role-key>
# EPIC_FHIR_BASE_URL=<your-staging-epic-url>
# EPIC_CLIENT_ID=<your-staging-client-id>
# EPIC_CLIENT_SECRET=<your-staging-client-secret>
# EPIC_TOKEN_URL=<your-staging-token-url>

# Verify no hard-coded production credentials leaked
grep -E "glipboeuhhpylcvqnruhu|sb_publishable" .env  # Should find nothing
```

### Verification
- [ ] Dependencies installed
- [ ] .env file created with staging values
- [ ] No production credentials in .env

---

## Step 3: Database Migrations (Estimated: 10 minutes)

### Prerequisites
- [ ] Database connection working
- [ ] Supabase admin credentials available
- [ ] Alembic configured

### Actions

```bash
# 1. Verify migration exists
ls alembic/versions/006_create_relationships_table.py

# 2. Test migration (dry-run)
alembic upgrade --sql 006  # Shows SQL without executing

# 3. Run migration (CAUTION: Modifies database)
alembic upgrade 006

# 4. Verify table created
psql -d your_staging_db -c "\dt relationships"

# 5. Verify RLS policy
psql -d your_staging_db -c "SELECT policy_name FROM pg_policies WHERE table_name='relationships';"
```

### Or Using Supabase CLI

```bash
# Push migrations to Supabase
supabase db push

# Verify in Supabase console
# - relationships table should appear
# - RLS policy should be attached
```

### Verification
- [ ] relationships table created
- [ ] RLS policy attached
- [ ] Columns match schema (id, tenant_id, from_type, from_id, to_type, to_id, relationship_state, evidence, created_at, updated_at)
- [ ] Indexes created

---

## Step 4: Application Startup (Estimated: 5 minutes)

### Prerequisites
- [ ] Database migrations completed
- [ ] .env file configured
- [ ] auth_app.py accessible at /auth

### Actions

```bash
# 1. Run full test suite
python3 -m pytest tests/ -v

# Expected: 188 tests passing
# If any fail, DO NOT PROCEED. Investigate and fix.

# 2. Start application
streamlit run app.py

# 3. Application should start without errors
# Check console output for:
# - "Streamlit is running on http://..."
# - No errors about missing dependencies
# - No errors about database connection
```

### Verification
- [ ] All 188 tests passing
- [ ] Application starts without errors
- [ ] Streamlit accessible at http://localhost:8501

---

## Step 5: Manual Testing (Estimated: 20 minutes)

### Test Case 1: Authentication

```
1. Open app in browser: http://localhost:8501
2. Expected: Login page shown (not dashboard)
3. Click "Login"
4. Enter credentials for test analyst user
5. Expected: Dashboard shown, user info in sidebar
6. Logout (button in sidebar)
7. Expected: Redirect to login page
```

**Verification Checklist:**
- [ ] Login page shown
- [ ] Authentication works
- [ ] Dashboard shown after login
- [ ] Logout works
- [ ] No errors in console

### Test Case 2: Authorization — Analyst Cannot Writeback

```
1. Log in as analyst_test_user (role=analyst)
2. Navigate to "Post Resolution to Epic" form
3. Expected: Form visible but "Your name / staff ID" field REMOVED
4. Fill in:
   - Epic FHIR Task ID: task_123
   - Resolution: "Resolved"
   - Resolution note: "Test resolution"
5. Click "Post Resolution to Epic"
6. Expected ERROR MESSAGE: "Insufficient permissions: Your role (analyst) cannot perform this action (requires supervisor)"
```

**Verification Checklist:**
- [ ] Form displayed without "Your name / staff ID" field
- [ ] Error message shown for analyst
- [ ] No writeback to Epic attempted
- [ ] Audit log shows WRITEBACK_DENIED event

### Test Case 3: Authorization — Supervisor Can Writeback

```
1. Logout and log in as supervisor_test_user (role=supervisor)
2. Navigate to "Post Resolution to Epic" form
3. Fill in:
   - Epic FHIR Task ID: task_456
   - Resolution: "Escalated"
   - Resolution note: "Escalated to supervisor"
4. Click "Post Resolution to Epic"
5. Expected: Either:
   a) Success message: "Epic Task task_456 updated..."
   b) Error from Epic API (but authorization passes)
```

**Verification Checklist:**
- [ ] No authorization error
- [ ] Writeback attempted (may fail if Epic not configured)
- [ ] Audit log shows WRITEBACK_ATTEMPTED and WRITEBACK_AUTHORIZED

### Test Case 4: Audit Logging

```
1. Check application console output
2. Search for lines containing "AUDIT:"
3. Expected format:
   AUDIT: writeback_attempted | tenant=xxx | user=yyy | role=zzz | ...
   AUDIT: writeback_authorized | tenant=xxx | user=yyy | role=zzz | ...
4. Verify user_id is UUID (not form field)
5. Verify user_role is from session (supervisor/analyst/admin)
6. Verify tenant_id matches user
```

**Verification Checklist:**
- [ ] Audit events logged
- [ ] user_id is UUID
- [ ] user_role from session
- [ ] tenant_id correct
- [ ] No hard-coded values

### Test Case 5: Credentials Verification

```
1. Check .env file
2. Verify no hard-coded Supabase URLs like:
   - glipboeuhpylcvqnruhu.supabase.co (old URL)
3. Verify no hard-coded service role keys like:
   - sb_publishable_ke0bsIX0g0as6k...
4. All values should be staging-specific
```

**Verification Checklist:**
- [ ] No production Supabase URLs in .env
- [ ] No production service role keys in .env
- [ ] All URLs point to staging
- [ ] All keys are staging credentials

---

## Step 6: Database Verification (Estimated: 10 minutes)

### Verify Relationships Table

```sql
-- Check table exists
SELECT table_name FROM information_schema.tables 
WHERE table_name='relationships';
-- Expected: relationships

-- Check columns
SELECT column_name, data_type FROM information_schema.columns 
WHERE table_name='relationships' 
ORDER BY ordinal_position;
-- Expected: id (uuid), tenant_id (varchar), from_type, from_id, to_type, to_id, 
--           relationship_state, evidence (jsonb), created_at, updated_at

-- Check RLS enabled
SELECT schemaname, tablename, rowsecurity FROM pg_tables 
WHERE tablename='relationships';
-- Expected: rowsecurity = true

-- Check RLS policies
SELECT policy_name, cmd FROM pg_policies 
WHERE table_name='relationships';
-- Expected: At least one policy for tenant isolation
```

### Verify No Data Corruption

```sql
-- Check existing tables still intact
SELECT COUNT(*) FROM claim_diagnostics LIMIT 1;
-- Expected: Returns count (no error)

SELECT COUNT(*) FROM client_configurations LIMIT 1;
-- Expected: Returns count (no error)
```

---

## Step 7: Rollback Plan

### If deployment fails:

```bash
# 1. Revert code
git revert HEAD  # Creates new commit undoing changes
# OR (if no other commits)
git reset --hard HEAD~1

# 2. Revert database (if migration was run)
alembic downgrade -1  # Removes relationships table

# 3. Restart application
streamlit run app.py

# 4. Verify rollback
python3 -m pytest tests/ -v  # Original 122 tests should still pass
```

### If partial failure:

```bash
# Keep code, but don't apply migrations
# Run with relationships table optional (supabase_writer soft-fails)
streamlit run app.py

# Then fix issues and retry migration
```

---

## Final Sign-Off

### Pre-Deployment

- [ ] All code changes verified
- [ ] All tests passing (188/188)
- [ ] No syntax errors
- [ ] No hard-coded credentials
- [ ] Documentation complete

### Post-Deployment

- [ ] Application started without errors
- [ ] Authentication working
- [ ] Analyst denied writebacks
- [ ] Supervisor can writeback
- [ ] Audit logs recording events
- [ ] Database tables created
- [ ] RLS policies attached
- [ ] No data corruption

### Staging Validation (Day 1)

- [ ] Monitor error logs for exceptions
- [ ] Verify audit logs being written
- [ ] Test end-to-end flow with sample data
- [ ] Confirm no PHI exposed in logs
- [ ] Check performance metrics

---

## Success Criteria

✅ **Deployment successful if:**

1. **Code:** 188/188 tests passing
2. **Authentication:** Users can log in and authenticate
3. **Authorization:** Analysts denied, supervisors allowed
4. **Database:** relationships table created with RLS
5. **Audit:** Events logged with correct user/tenant context
6. **Security:** No credentials in .env, no PHI in logs
7. **Performance:** No significant slowdowns

---

## Support & Troubleshooting

### Issue: "relationships table not found"

**Solution:**
```bash
alembic upgrade 006
# OR
supabase db push
```

### Issue: "Insufficient permissions" error for supervisor

**Solution:**
- Check user role in session state
- Verify role set correctly in auth_app.py
- Check test user has role=supervisor in client_configurations table

### Issue: "user_id from form field" in audit logs

**Solution:**
- Verify app.py updated with SessionValidator integration
- Check auth_session.py imported correctly
- Restart application after code changes

### Issue: Tests failing after merge

**Solution:**
```bash
git status  # Check for uncommitted changes
pip install -r requirements.txt  # Reinstall dependencies
python3 -m pytest tests/ -v  # Run full test suite
```

---

## Contact for Issues

If issues occur during deployment, check:
1. `SECURITY_AUDIT_E5.md` — E5 authentication details
2. `FINAL_STATUS_REPORT.md` — Complete implementation status
3. Test files — `tests/test_e5_authentication.py` for examples
4. Code — `waterfall_guard/auth_session.py` for authentication logic

