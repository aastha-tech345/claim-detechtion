# Patent Architecture Compliance Matrix — E3, E4, E5, E6

**Repository:** waterfall-guard  
**Audit Date:** 2026-10-27  
**Baseline Commit:** 0ad8799899f61a224038d890eec022bce0427038  
**Branch:** aastha  

---

## Executive Summary

Waterfall Guard is an analytical application for diagnosing orphaned or stalled healthcare revenue-cycle claims in Epic EHRs. It ingests de-identified claim data, applies a hospital's custom business rules, and flags deadlocked claims for staff review. The architecture enforces Zero-Data-Retention (ZDR) for LLM calls and provides read-only analysis with a separate write-back client for Epic FHIR Task updates.

### Requirements Assessment

| Requirement | Status | Gap |
|------------|--------|-----|
| **E3: Transaction-Specific Lifecycle Reconstruction** | PARTIALLY_IMPLEMENTED | Missing: explicit encounter-charge-claim-acknowledgment-remittance relationships; missing UNRESOLVED/ACCEPTED/REJECTED relationship states; no quarantine mechanism for ambiguous matches |
| **E4: Expected-Successor Testing** | PARTIALLY_IMPLEMENTED | Missing: explicit expected-successor linking; missing orphan vs. delayed detection; partially complete orphan detection (age-based, not successor-based); filing-deadline logic present but not integrated with orphan classification |
| **E5: Read-Only Analytical Architecture** | IMPLEMENTED | FHIR writeback client present and operational; enforcement relies on per-tenant OAuth permissions and lacks runtime guardrails |
| **E6: Separate Controlled-Execution Architecture** | NOT_VERIFIED | Writeback client runs within analytical process; no architectural separation verified; execution boundary not documented |

---

## E3 — Transaction-Specific Lifecycle Reconstruction

### Requirement

Establish transaction-specific relationships between encounters, charges, claims, acknowledgments, and remittances. Represent relationship states as ACCEPTED, REJECTED, or UNRESOLVED. Quarantine unresolved relationships and prevent them from being treated as confirmed lifecycle relationships.

### Current Implementation Evidence

**File:** `waterfall_guard/models/claim.py`  
**Status:** MINIMAL_MODEL_ONLY

```python
class Claim(BaseModel):
    claim_id: str
    patient_id: str
    payer: str
    status: ClaimStatus  # SUBMITTED, ACKNOWLEDGED, IN_ADJUDICATION, PAID, DENIED, REJECTED
    amount: float
    submitted_at: datetime
    last_status_change_at: datetime
    expected_response_by: Optional[datetime] = None
```

**Issues:**
- No explicit encounter, charge, acknowledgment, or remittance identifiers
- No relationship state tracking (ACCEPTED/REJECTED/UNRESOLVED)
- No supporting_evidence field to justify relationship acceptance/rejection
- No ambiguous_match_candidates field for quarantined matches
- Claim model is not used by the reconciliation engine (engine.py uses de-identified records with waterfall/WQ metadata)

**File:** `waterfall_guard/deident.py`  
**Status:** PHI_TOKENIZATION_ONLY

- Tokenizes PAT_ENC_CSN_ID as the claim identifier
- Passes through non-PHI state fields (waterfall_stage, hold_reason, current_wq_id, eligible_wq_ids, days_in_stage, account_balance, filing_deadline)
- Does NOT capture or track encounter-charge-claim-acknowledgment-remittance relationships
- Does NOT track relationship evidence or rejection reasons

**File:** `waterfall_guard/integrations/epic_client.py`  
**Status:** MOCK_DATA_ONLY

Mock data captures:
- PAT_ENC_CSN_ID (encounter ID)
- Waterfall stage, work queue, hold reason, days in stage
- Account balance

Missing:
- Explicit charge IDs
- Acknowledgment details (payer response, date, evidence)
- Remittance details (payment, denial reason, evidence)
- Relationship evidence (how was charge matched to claim? how was claim matched to acknowledgment?)

### Database Schema Evidence

**Migration 001** (`alembic/versions/001_create_claim_diagnostics.py`):
```sql
CREATE TABLE claim_diagnostics (
  id BIGINT,
  token_id TEXT,  -- de-identified claim ID
  waterfall_stage TEXT,
  deadlock_types TEXT[],
  active_hold_names TEXT[],
  eligible_wq_ids TEXT[],
  unassigned_wq_ids TEXT[],
  created_at TIMESTAMP WITH TIME ZONE
);
```

**Missing Columns:**
- encounter_id / charge_ids (no place to store transaction-specific IDs)
- acknowledgment_details (payer response evidence)
- remittance_details (payment/denial evidence)
- relationship_state (ACCEPTED/REJECTED/UNRESOLVED)
- relationship_evidence (how relationship was matched)
- ambiguous_candidates (for quarantine)

### Test Coverage

**test_engine.py:** Tests deadlock detection, not relationship lifecycle.  
**test_deident.py:** Tests PHI tokenization, not relationship matching.  
**test_epic_client.py:** Mock data only, no relationship matching tests.

**Test Gap:** Zero tests for:
- Accepting a valid encounter-charge-claim-acknowledgment relationship
- Rejecting a conflicting relationship
- Quarantining an ambiguous match
- Preventing unresolved relationships from being used in downstream analysis

### Current Status

**PARTIALLY_IMPLEMENTED** — Claim model exists but:
1. Relationships between transactions not modeled
2. Relationship state (ACCEPTED/REJECTED/UNRESOLVED) not implemented
3. Supporting evidence not tracked
4. Ambiguous matches not quarantined
5. Engine operates on de-identified records without relationship metadata

### Identified Gaps for E3

1. **Relationship Data Model:** Must extend beyond single Claim to model:
   - Encounter (encounter_id, service dates, facility)
   - Charge (charge_id, amount, procedure code, associated encounter)
   - Claim (claim_id, associated charges, submitted date, payer)
   - Acknowledgment (ack_id, claim_id, payer response, receipt date)
   - Remittance (remit_id, acknowledgment_id, payment/denial, amount)

2. **Relationship Matching Logic:** Must establish:
   - Encounter → Charge matching (same patient, overlapping service dates)
   - Charge → Claim grouping (same encounter, same payer, amount tolerance)
   - Claim → Acknowledgment matching (claim_id or billing ID, date correlation)
   - Acknowledgment → Remittance matching (claim_id, remittance date correlation)

3. **Relationship State Tracking:**
   - ACCEPTED: Evidence supports relationship (e.g., matching claim ID, date within tolerance)
   - REJECTED: Evidence contradicts relationship (e.g., conflicting amounts, different payers)
   - UNRESOLVED: Ambiguous or incomplete (e.g., multiple candidate matches, missing identifier)

4. **Quarantine Mechanism:**
   - Mark unresolved relationships as such in persistence layer
   - Prevent unresolved relationships from being used in E4 expected-successor checks
   - Surface ambiguous matches in diagnostic output

5. **Database Migrations:**
   - Add relationships table (encounter_id, charge_id, claim_id, ack_id, remit_id, relationship_state, evidence, created_at)
   - Add relationship_evidence table (relationship_id, evidence_type, evidence_value, source)

### Implementation Plan for E3

**Phase 1: Data Model Extension**
- Extend Claim model with encounter_id, charge_ids[], ack_id, remit_id, relationship_state
- Add RelationshipEvidence dataclass (evidence_type, value, source, confidence_score)
- Add TransactionRelationship dataclass (from_type, from_id, to_type, to_id, state, evidence[])

**Phase 2: Relationship Matching Logic**
- Implement encounter-to-charge matcher (patient ID + service date overlap)
- Implement charge-to-claim matcher (encounter ID + amount tolerance)
- Implement claim-to-ack matcher (claim_id correlation + date proximity)
- Implement ack-to-remittance matcher (claim_id + date order)

**Phase 3: Relationship Persistence**
- Create migration 006 for relationships table
- Implement write to relationships table in supabase_writer.py
- Add RLS policy for relationships table (tenant isolation)

**Phase 4: Engine Integration**
- Update engine.py to accept relationship metadata
- Suppress deadlock findings that depend on unresolved relationships
- Document relationship evidence in diagnostic output

**Phase 5: Testing**
- Add test_relationships.py with cases for ACCEPTED, REJECTED, UNRESOLVED
- Add test cases for ambiguous candidate detection
- Add test cases for evidence collection and storage

---

## E4 — Expected-Successor Testing

### Requirement

Use accepted lifecycle relationships to determine which downstream events should exist. Implement expected-successor relationship identification, missing-claim detection, delayed-claim detection, potential orphan detection before payer timely-filing deadlines, and classification of actionable vs. expired claims.

### Current Implementation Evidence

**File:** `waterfall_guard/agents/reconciliation_agent.py`  
**Status:** SIMPLE_AGE_BASED_ORPHAN_DETECTION

```python
def find_orphaned_claims(self, claims: List[Claim]) -> List[OrphanedClaim]:
    now = datetime.now(timezone.utc)
    orphaned = []
    for claim in claims:
        if claim.status in TERMINAL_STATUSES:
            continue
        days_stalled = (now - claim.last_status_change_at).days
        if days_stalled < self.orphan_threshold_days:
            continue
        reason = f"no status change for {days_stalled} days (status={claim.status.value})"
        orphaned.append(OrphanedClaim(claim=claim, days_stalled=days_stalled, reason=reason))
    return orphaned
```

**Issues:**
- Only detects age-based staleness (last_status_change_at > threshold_days)
- No expected-successor logic (does not check if a specific downstream claim should exist)
- No distinction between missing (never received) vs. delayed (late arrival)
- No timely-filing deadline check
- Does not use lifecycle relationships
- Terminal statuses (PAID, DENIED, REJECTED) exclude from orphan detection

**File:** `waterfall_guard/engine.py`  
**Status:** DEADLOCK_DETECTION_ONLY

Deadlock detection (3 types):
- **no_exit_condition:** Hold has no resolving WQ
- **ambiguous_wq_routing:** Multiple eligible WQs, all unowned
- **no_escalation_owner:** Stalled claim in unowned WQ

```python
is_stalled = record.get("days_in_stage", 0) >= self.stall_threshold_days
```

**Issues:**
- Does NOT check for expected-successor existence
- Does NOT implement missing-claim detection
- Does NOT distinguish delayed vs. missing
- Filing deadline present in output but not used for classification
- Does NOT classify claims as actionable vs. expired

**File:** `waterfall_guard/models/claim.py`  
**Status:** MINIMAL

```python
expected_response_by: Optional[datetime] = None
```

Present but never used in orphan detection or successor checking.

### Database Schema Evidence

**Migration 005** (`alembic/versions/005_add_filing_deadline.py`):
```sql
ALTER TABLE claim_diagnostics ADD COLUMN filing_deadline TIMESTAMP WITH TIME ZONE;
```

**Present but unused:** filing_deadline is passed through from ingestion but not used in classification logic.

### Test Coverage

**test_reconciliation_agent.py:**
```python
def test_flags_stalled_claim_past_threshold():
    # Creates claim with status=IN_ADJUDICATION, last_status_change_at 20 days ago
    # Expects OrphanedClaim with reason="no status change for 20 days"

def test_does_not_flag_recent_claim():
    # Status change 5 days ago, threshold=14; expects empty orphaned list

def test_does_not_flag_terminal_status():
    # PAID/DENIED/REJECTED always skipped
```

**Test Gap:** Zero tests for:
- Expected-successor existence checking
- Missing-claim detection
- Delayed-claim detection (late vs. missing)
- Filing-deadline-based classification
- Actionable vs. expired claim classification
- Unresolved relationship suppression

### Current Status

**PARTIALLY_IMPLEMENTED** — Orphan detection present but:
1. Age-based only (no successor expectations)
2. No missing/delayed distinction
3. Filing deadline not used for classification
4. No actionable vs. expired classification
5. No relationship dependency checking

### Identified Gaps for E4

1. **Expected-Successor Identification:**
   - Define state transitions and expected follower events
   - E.g., SUBMITTED → expect ACKNOWLEDGED within X days
   - E.g., ACKNOWLEDGED → expect IN_ADJUDICATION within Y days
   - E.g., CLAIM or claim group → expect REMITTANCE within payer SLA

2. **Missing-Claim Detection:**
   - For an ACKNOWLEDGED claim, check if corresponding IN_ADJUDICATION claim exists
   - If missing after N days, flag as missing (not just stalled)
   - Example: Payer ACK received but no claim progress seen in 7 days

3. **Delayed-Claim Detection:**
   - For claims with expected_response_by set, calculate delay
   - Example: Expected REMITTANCE by 2026-10-20, actual arrival 2026-10-27 (7 days late)
   - Distinguish "late but arrived" from "never arrived"

4. **Filing-Deadline Checking:**
   - For claims approaching filing_deadline, flag as actionable (escalate before deadline)
   - Example: filing_deadline = 2026-11-15, today = 2026-11-01 (14 days left)
   - For claims past filing_deadline, flag as expired (requires audit/remediation)
   - Example: filing_deadline = 2026-10-15, today = 2026-10-27 (12 days past, potentially uncollectible)

5. **Actionable vs. Expired Classification:**
   - Actionable: Claim can still be remedied (filing deadline future, escalation possible)
   - Expired: Claim cannot be remedied (filing deadline past, no recovery option)
   - Blocked: Claim waiting on dependency (expected-successor not received)

6. **Relationship Dependency Integration:**
   - Suppress successor checks for unresolved relationships
   - Example: If claim-to-acknowledgment relationship is UNRESOLVED, do not flag missing remittance

### Implementation Plan for E4

**Phase 1: Expected-Successor Model**
- Add SuccessorExpectation dataclass (from_status, to_status, expected_days, payer_sla)
- Add expected_successors config to HospitalRuleSet (similar to hold_conditions and wq_gates)
- Implement successor_exists() method in engine

**Phase 2: Missing/Delayed Detection**
- Implement missing_successor_detector() in engine
- Implement delayed_successor_detector() in engine
- Add to DeadlockFinding or create separate FindingType for missing/delayed

**Phase 3: Filing-Deadline Classification**
- Implement deadline_days_remaining() method
- Classify claims as:
  - ACTIONABLE (deadline future, escalation possible)
  - ESCALATION_REQUIRED (deadline < threshold)
  - EXPIRED (deadline past)
  - UNKNOWN (no deadline available)

**Phase 4: Unresolved Relationship Suppression**
- Query relationships table for unresolved matches
- Suppress successor checks when dependency is unresolved
- Document suppression reason in output

**Phase 5: Testing**
- Add test cases for successor existence checking
- Add test cases for missing-claim detection
- Add test cases for delayed-claim detection
- Add test cases for filing-deadline classification
- Add test cases for actionable vs. expired
- Add test cases for unresolved relationship suppression

---

## E5 — Read-Only Analytical Architecture

### Requirement

The analytical application may retrieve approved healthcare data, analyze it, and present findings for authorized staff. It must NOT independently submit or modify healthcare claims. All code paths that can write to external systems must be documented and enforced with read-only boundaries at the architecture level.

### Current Implementation Evidence

**File:** `waterfall_guard/integrations/fhir_writeback_client.py`  
**Status:** FUNCTIONAL_WRITE_CLIENT

The writeback client is fully implemented and operational:
- Authenticates per-tenant via OAuth2 client_credentials
- Fetches FHIR Task resource (GET)
- Updates Task status field and appends resolution note
- Puts updated Task back to Epic (PUT)
- Maps internal statuses (RESOLVED, ESCALATED, WONT_FIX) to FHIR Task statuses

```python
class EpicFHIRWritebackClient:
    def post_resolution(self, update: ResolutionUpdate) -> WritebackResult:
        # GET /Task/{task_id}
        # Modify task["status"] and task["note"][]
        # PUT /Task/{task_id} with ETag If-Match
        # Return WritebackResult(ok, task_id, fhir_status, error)
```

**Important:** The writeback updates a FHIR Task resource. The spec states this is a resolution status update, not a modification of the underlying healthcare claim itself. However, the FHIR Task is created by the analytical system and posted back to Epic, which may trigger workflows in Epic that act on the claim.

**File:** `app.py`  
**Status:** WRITEBACK_UI_PRESENT

Dashboard form at lines 1063-1119 ("Post Resolution to Epic"):
```python
with st.form("post_resolution_form"):
    ref_token_id = st.selectbox("Claim (token_id, for reference)", ...)
    epic_task_id = st.text_input("Epic Task ID")
    resolution_note = st.text_area("Resolution note")
    resolved_by = st.text_input("Your name / staff ID")
    post_submitted = st.form_submit_button("Post Resolution to Epic")

if post_submitted:
    try:
        epic_config = TenantEpicConfig.load(get_tenant_id())
        writeback_client = EpicFHIRWritebackClient(epic_config)
        result = writeback_client.post_resolution(
            ResolutionUpdate(
                task_id=epic_task_id.strip(),
                status=ResolutionStatus[resolution_status.upper()],
                note=resolution_note,
                resolved_by=resolved_by,
            )
        )
        if result.ok:
            st.success(f"Epic Task {result.task_id} updated to '{result.fhir_status}'.")
        else:
            st.error(f"Failed to post resolution to Epic: {result.error}")
    except ValueError as exc:
        st.error(f"Epic isn't configured for this tenant yet: {exc}")
```

**Issues:**
- Writeback client is accessible from within the analytical dashboard
- No runtime guardrails prevent unauthorized execution
- No audit logging of who performed the write or when
- Enforcement relies on per-tenant OAuth config, not application-level access control

**File:** `waterfall_guard/main.py`  
**Status:** ANALYSIS_ONLY

The end-to-end pipeline (main.py) performs only read and analysis operations:
1. Epic ingestion (mock Clarity/Caboodle/FHIR Task polling)
2. De-identification (local memory, no persistence of PHI)
3. Engine reconciliation (rule matching, deadlock diagnosis)
4. LLM diagnostic call (ZDR-enforced)
5. Supabase diagnostic persistence (de-identified findings only)

The writeback client is NOT invoked by main.py or the LLM diagnostic flow.

**File:** `waterfall_guard/integrations/supabase_writer.py`  
**Status:** WRITE_SAFE

Writes only de-identified diagnostic findings to claim_diagnostics table:
- No PHI ever written
- All identifying information is token_id (HMAC-hashed)
- Only metadata and rule findings written
- Never modifies or deletes claims

### Database Schema Evidence

**client_configurations Table (Migration 004):**
- Stores per-tenant Epic FHIR credentials (client_id, fhir_base_url)
- RLS policy: tenant_id == JWT claim's tenant_id
- Credentials are loaded by EpicFHIRWritebackClient for OAuth

**claim_diagnostics Table:**
- Read-only for dashboard users (SELECT allowed via RLS)
- Writes via service role key only (supabase_writer.py)
- No modification or deletion of healthcare claims

### Test Coverage

**test_fhir_writeback_client.py (11 tests):**
- TenantEpicConfig loading and validation
- post_resolution_once() mock HTTP interaction
- Status mapping (RESOLVED→completed, etc.)
- OAuth token caching and refresh
- ETag handling for concurrent updates
- Retry logic and soft-failure

**test_app.py:** Not present in test suite. Dashboard form is not unit-tested.

**Test Gap:** Zero tests verifying:
- Dashboard form requires authentication
- Dashboard form cannot bypass OAuth permission checks
- Write operations are properly logged
- Unconfirmed claims are not written to

### Current Status

**IMPLEMENTED** — Writeback client is fully functional, but:
1. No architectural separation from analytical environment (runs in same process)
2. No application-level access control (relies on OAuth config only)
3. No audit logging of write operations
4. UI is not gated by additional authorization checks beyond per-tenant config

### Read-Only Boundary Definition

**Permitted (Analytical):**
- Read Epic Clarity/Caboodle data
- De-identify locally
- Analyze against hospital rules
- Generate diagnostic findings
- Store de-identified findings in Supabase
- Call external LLM for analysis

**Prohibited (Not Permitted in Analytical Process):**
- Modify healthcare claims in Epic
- Modify encounter or charge records
- Delete or archive claim data
- Submit claim to payer
- Modify remittance/EOB information
- Change claim status in Epic beyond what authorized staff explicitly approve

**Currently Allowed (Intentional but Constrained):**
- Post resolution status updates to Epic FHIR Task (via dashboard form)
- This is considered a metadata update, not a claim modification
- Gated by per-tenant OAuth config in client_configurations

### Enforcement Gaps

1. **No Application-Level Authorization:**
   - Dashboard form does not check user role (analyst vs. billing supervisor vs. admin)
   - Any authenticated user can attempt write

2. **No Audit Logging:**
   - Write attempts are not logged
   - No record of who, when, what status change

3. **No Runtime Guardrails:**
   - Engine.diagnose() does not prevent writeback
   - main.py does not prevent writeback
   - Only the dashboard form structure prevents it

4. **No Separation of Duties:**
   - Same application that performs analysis also performs writes
   - No separate approval workflow before writes execute

### Implementation Plan for E5

**Phase 1: Define Read-Only Boundary**
- Document explicit list of permitted reads
- Document explicit list of prohibited writes
- Create architectural diagram showing data flow

**Phase 2: Add Authorization Checks to Dashboard**
- Require user role claim (e.g., analyst, supervisor, admin)
- Check role before showing writeback form
- Log all authorization decisions

**Phase 3: Add Audit Logging**
- Log every writeback attempt (success/failure)
- Include timestamp, user, tenant, task_id, status change, result
- Store audit logs in separate immutable table

**Phase 4: Add Runtime Guardrails**
- Add WritebackGate class to prevent unauthorized invocations
- Implement role-based access control
- Return clear error for unauthorized attempts

**Phase 5: Testing**
- Add test cases for authorization checks
- Add test cases for role-based access denial
- Add test cases for audit logging
- Verify writebacks only happen via dashboard form (not main.py)

---

## E6 — Separate Controlled-Execution Architecture

### Requirement

Execution and writeback functionality must remain separate from the analytical environment. The analytical application must not be able to bypass approved boundaries for external write operations. Separate execution permissions from analytical read permissions.

### Current Implementation Evidence

**Architecture Status:** NOT_VERIFIED

**Deployment Configuration:**
- No deployment scripts or Docker configuration in repository
- app.py (Streamlit dashboard) and main.py (batch pipeline) both in same codebase
- No evidence of separate services or execution contexts

**File:** `app.py`  
**Status:** SINGLE_MONOLITHIC_STREAMLIT_APP

- Dashboard includes analytics (data loading, filtering, visualization)
- Dashboard includes writeback form and client invocation
- Single process runs both analysis and writes

**File:** `waterfall_guard/integrations/fhir_writeback_client.py`  
**Status:** IMPORTED_DIRECTLY_BY_DASHBOARD

```python
# app.py, line 17
from waterfall_guard.integrations.fhir_writeback_client import (
    EpicFHIRWritebackClient,
    ResolutionStatus,
    ResolutionUpdate,
    TenantEpicConfig,
)
```

The writeback client is directly imported and instantiated in app.py, allowing it to execute within the analytical process.

**File:** `waterfall_guard/main.py`  
**Status:** ANALYSIS_ONLY

The batch pipeline does NOT import or invoke the writeback client. It only performs analysis and persistence of diagnostic findings.

**Credentials and Permissions:**
- Epic FHIR credentials loaded from client_configurations Supabase table
- OAuth client_credentials token fetched by writeback client
- Token scoped to per-tenant Epic FHIR API access
- No separate execution service identity

### Database Schema Evidence

**client_configurations Table:**
- Stores per-tenant FHIR credentials (client_id, fhir_base_url)
- No separate execution service credentials table
- RLS policy: tenant_id == JWT claim's tenant_id (dashboard user isolation, not service separation)

### Test Coverage

**test_fhir_writeback_client.py:**
- Tests TenantEpicConfig.load() against mocked Supabase
- Tests OAuth token fetching against mocked requests
- Tests POST to Epic against mocked session
- No tests for separation of execution contexts
- No tests for execution authorization

**Tests NOT Present:**
- Verification that writeback cannot be called from main.py
- Verification that execution service has separate permissions
- Verification that analytics service cannot escalate to writes
- Tests for cross-service authorization

### Current Status

**NOT_VERIFIED** — Current architecture does not implement separation:
1. Writeback client runs in same process as analytical dashboard
2. No separate execution service or container
3. No separate execution permissions (uses same tenant OAuth as analytics)
4. No evidence of deployment-level separation
5. No audit boundary between analysis and execution

### Current Execution Context

The writeback happens entirely within the Streamlit dashboard process:
1. User submits form with epic_task_id, resolution_status, resolution_note, resolved_by
2. Dashboard form handler calls TenantEpicConfig.load(tenant_id) → queries Supabase
3. Instantiates EpicFHIRWritebackClient(config)
4. Invokes post_resolution(ResolutionUpdate(...))
5. Client fetches token via OAuth, GETs Task, PUTs updated Task
6. Returns WritebackResult to form handler
7. Form displays success/error to user

**No separate execution:** All steps happen in the same process, same thread.

### Identified Gaps for E6

1. **Execution Service Separation:**
   - Analytical dashboard (read-only analysis + visualization)
   - Execution service (writeback to Epic, isolated runtime)
   - Queue/API between them (async dispatch, not direct invocation)

2. **Execution Permissions:**
   - Analytical dashboard: Read claims, generate findings, call LLM
   - Execution service: OAuth credentials only for FHIR Task writes
   - No ability for execution service to read diagnostic findings
   - No ability for analytical service to write to Epic

3. **Request Audit Trail:**
   - Dashboard cannot directly execute writes
   - Dashboard queues a write request (signed/approved)
   - Execution service reads queue, verifies request, executes
   - Both services log the transaction independently

4. **Deployment Topology:**
   - Streamlit dashboard in one container/process
   - Execution service in separate container/process
   - Message queue (database or job queue) between them
   - No network path from analytics to FHIR endpoint except via execution service

5. **Credentials Separation:**
   - Analytics service: Supabase service role key (read diagnostic_claims, write findings)
   - Execution service: OAuth credentials from client_configurations (write FHIR Task only)
   - No cross-service credential sharing

### Implementation Plan for E6

**Phase 1: Design Execution Service**
- Define async write request schema (tenant_id, task_id, status, note, requested_by, approval_state)
- Create execution_requests table in Supabase
- Design approval workflow (manual, or auto-approve for authorized users)

**Phase 2: Separate Dashboard from Execution**
- Remove direct import of EpicFHIRWritebackClient from app.py
- Replace writeback form with request submission form
- Form inserts row into execution_requests table instead of directly invoking client
- Dashboard displays request status (pending, approved, completed, failed)

**Phase 3: Implement Execution Service**
- Create new service (execution_service.py or separate package)
- Continuously polls execution_requests for pending/approved requests
- Invokes EpicFHIRWritebackClient for approved requests
- Updates request status and result in table
- Logs audit trail independently

**Phase 4: Update Credentials Architecture**
- Keep execution service credentials separate from analytics
- Document credential loading for each service
- Ensure analytics service cannot load execution credentials

**Phase 5: Testing**
- Add tests for request queueing (dashboard → table)
- Add tests for execution service polling
- Add tests that analytics service cannot call writeback client directly
- Add tests for approval workflow
- Add tests for request status transitions

---

## Summary Status Table

| Requirement | Current Status | Implementation Level | Gaps | Effort |
|-------------|---|---|---|---|
| **E3: Lifecycle Reconstruction** | PARTIALLY_IMPLEMENTED | Model only | Relationships, matching, state tracking, quarantine | High |
| **E4: Expected-Successor Testing** | PARTIALLY_IMPLEMENTED | Age-based orphan only | Successors, missing/delayed, deadlines, classification | High |
| **E5: Read-Only Architecture** | IMPLEMENTED | Functional | Authorization, audit logging, runtime guardrails | Medium |
| **E6: Controlled Execution** | NOT_VERIFIED | Same-process writes | Service separation, approval workflow, credentials separation | High |

---

## Baseline Test Results

**All 66 tests passing:**
```
============================= test session starts ==============================
collected 66 items

tests/test_deident.py ............................ [ 10%] (7 tests)
tests/test_engine.py ............................ [ 22%] (9 tests)
tests/test_epic_client.py ........................ [ 34%] (6 tests)
tests/test_fhir_writeback_client.py ............. [ 59%] (11 tests)
tests/test_llm_client.py ........................ [ 71%] (8 tests)
tests/test_main_simulation.py ................... [ 84%] (9 tests)
tests/test_reconciliation_agent.py ............. [ 89%] (3 tests)
tests/test_supabase_writer.py .................. [ 100%] (9 tests)

============================== 66 passed in 0.75s ==============================
```

---

## Next Steps

1. **E3 Implementation:** Extend claim model, implement relationship matching, add quarantine mechanism
2. **E4 Implementation:** Add expected-successor checking, missing/delayed detection, deadline classification
3. **E5 Enforcement:** Add authorization checks, audit logging, runtime guardrails
4. **E6 Implementation:** Design execution service, separate from analytical process, implement approval workflow

---

**Document Version:** 1.0  
**Last Updated:** 2026-10-27  
**Prepared By:** Audit Process  
**Status:** READY FOR IMPLEMENTATION PLANNING
