# Waterfall Guard E3–E6 Deployment Guide

**Status:** Ready for staging deployment  
**All Tests:** ✅ 156/156 PASS  
**Git Status:** 5 modified + 18 new files (no destructive changes)

---

## Pre-Deployment Checklist

- [x] All 156 tests passing (zero regressions)
- [x] E5 authorization integrated into app.py
- [x] E3/E4/E5 code reviewed and documented
- [x] No breaking changes (all backward-compatible)
- [x] No PHI exposure (audit logs contain only IDs and metadata)
- [x] Git history preserved

---

## Deployment Steps

### 1. Code Deployment (10 minutes)

```bash
# Verify working tree clean except for intended changes
git status

# Expected: 5 modified + 18 new files
# If additional changes present, investigate before proceeding

# Merge to main (or merge PR)
git checkout main
git merge aastha
# OR if using GitHub: merge PR through UI

# Push to remote
git push origin main
```

### 2. Install Dependencies (5 minutes)

```bash
# Update requirements.txt dependencies
pip install -r requirements.txt

# Expected new packages: alembic, sqlalchemy, reportlab
pip show alembic
pip show sqlalchemy
```

### 3. Database Migrations (Optional, can defer)

```bash
# Run Alembic migration for relationships table (migration 006)
alembic upgrade head

# Verify relationships table created
psql -d your_database -c "\dt relationships"

# OR use Supabase CLI for remote database
supabase db push

# Verify RLS policy applied
supabase db policies list
```

### 4. Staging Validation (20 minutes)

```bash
# Run full test suite
python3 -m pytest tests/ -v

# Expected: 156 tests, 1.5 seconds, all PASS

# Manual test in Streamlit
streamlit run app.py

# Test writeback form:
# 1. Navigate to "Post Resolution to Epic" section
# 2. Fill in form with test values
# 3. Submit as ANALYST role (should fail with authorization error)
# 4. Re-submit as SUPERVISOR role (should succeed)
# 5. Check app logs for audit events (WRITEBACK_ATTEMPTED, WRITEBACK_AUTHORIZED, etc.)
```

### 5. Production Deployment (5 minutes)

```bash
# Tag release
git tag -a v1.0-e3e4e5 -m "E3/E4/E5 implementation with E5 authorization integration"
git push origin v1.0-e3e4e5

# Deploy to production
# (Follow your existing deployment process)
# - Push to production branch
# - Trigger CI/CD pipeline
# - Monitor for errors

# Verify production deployment
curl https://your-production-app.com/health
# Should return 200 OK
```

---

## Validation Checklist (Post-Deployment)

### E5 Authorization Tests

- [ ] **Analyst cannot writeback:** Submit form as analyst → see "Authorization denied" error
- [ ] **Supervisor can writeback:** Submit form as supervisor → success (or Epic error, but authorization passes)
- [ ] **Admin can writeback:** Submit form as admin → success
- [ ] **Missing user denies:** Submit form with empty user_id → authorization error
- [ ] **Invalid role denies:** Submit form with invalid role → authorization error

### Audit Logging Tests

- [ ] **Writeback attempts logged:** Each form submission generates WRITEBACK_ATTEMPTED event
- [ ] **Authorization checks logged:** Each attempt generates WRITEBACK_AUTHORIZED or WRITEBACK_DENIED
- [ ] **Success logged:** Successful writeback generates WRITEBACK_SUCCEEDED
- [ ] **Failure logged:** Failed writeback generates WRITEBACK_FAILED
- [ ] **No PHI in logs:** Check application logs; should not contain patient names, SSNs, or clinical data

### Regression Tests

- [ ] **Dashboard still works:** All existing pages render correctly
- [ ] **Existing integrations intact:** Epic FHIR read, Supabase read, LLM calls still work
- [ ] **De-identification intact:** ZDR-safe payloads still generated
- [ ] **Engine still works:** Reconciliation logic unchanged
- [ ] **All 90 original tests still pass:** No regressions introduced

### E3/E4 Readiness Tests

- [ ] **Relationship models loadable:** `from waterfall_guard.models.claim import TransactionRelationship` works
- [ ] **Successor matcher accessible:** `from waterfall_guard.successors import SuccessorMatcher` works
- [ ] **Database schema ready:** relationships table exists (if migration 006 applied)
- [ ] **Persistence layer ready:** supabase_writer.write_relationships() callable

---

## Rollback Plan

If issues occur after deployment:

```bash
# Rollback to previous commit
git revert HEAD  # Creates a new commit undoing changes
git push origin main

# OR reset to previous release
git reset --hard v1.0-e3e4e5~1
git push origin main --force  # Use with caution; only if no other commits

# Rollback database (if migration 006 was applied)
alembic downgrade -1  # Removes relationships table
```

---

## Monitoring & Alerts

### Key Metrics to Monitor

1. **WRITEBACK_DENIED events** — Spike might indicate unauthorized access attempts
2. **WRITEBACK_FAILED events** — Increase might indicate Epic API issues
3. **Authorization errors in logs** — Track for security monitoring
4. **Audit log table size** — If E5 persistence enabled, monitor growth

### Recommended Alerts

- Alert if WRITEBACK_DENIED count > 5 in 1 hour (potential attack)
- Alert if WRITEBACK_FAILED count > 3 in 1 hour (Epic connectivity issue)
- Alert if app error rate increases > 5% after deployment

---

## Next Phases

### Phase 2 (Weeks 2–3): E3/E4 Integration

- Implement relationship matching algorithms
- Integrate SuccessorMatcher into engine
- Display actionability on dashboard

**No deployment blocker; can proceed immediately after this deployment.**

### Phase 3 (Weeks 3–4): Audit Persistence

- Create audit_events table (migration 007)
- Persist audit logs to database
- Add audit log viewer UI

**Can be done in parallel with Phase 2.**

### Phase 4 (Pending Approval): E6 Execution Separation

- Obtain stakeholder approval for async writeback model
- Implement execution_requests table (migration 008)
- Deploy separate execution service

**Decision required before starting; breaking change to dashboard.**

---

## Support & Troubleshooting

### Common Issues

**Issue:** "Authorization denied: No user context available"  
**Cause:** app.py cannot read user_id from form  
**Fix:** Verify form field `resolved_by` is not empty

**Issue:** "Authorization denied: User role not authorized"  
**Cause:** user_role is "analyst", which is not authorized for writebacks  
**Fix:** Change USER_ROLE environment variable or use "supervisor"/"admin"

**Issue:** "Writeback attempted but no audit events logged"  
**Cause:** AuditLogger not persisting to database (in-memory only for now)  
**Fix:** Normal for current phase; audit events logged to app stdout; will persist in Phase 3

**Issue:** "relationships table does not exist"  
**Cause:** Migration 006 not run  
**Fix:** Run `alembic upgrade head` or `supabase db push`

---

## Contact & Escalation

For questions or issues:

1. Check `FINAL_IMPLEMENTATION_REPORT.md` for architecture details
2. Check `docs/E3_E4_E5_E6_IMPLEMENTATION_REPORT.md` for implementation details
3. Run `python3 -m pytest tests/test_readonly_enforcement.py -v` to verify E5 functionality
4. Review application logs for audit events (search for "AUDIT:")

---

**Deployment Date:** 2026-10-27  
**Status:** Ready to merge  
**Estimated Time to Production:** 30 minutes total

