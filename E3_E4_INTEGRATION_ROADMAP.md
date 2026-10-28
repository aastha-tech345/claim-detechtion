# E3/E4 Pipeline Integration Roadmap

**Status:** DESIGN PHASE — Not yet implemented  
**Priority:** CRITICAL — E3/E4 logic exists but is not used by production pipeline  
**Estimated Effort:** 4–6 hours (implementation + testing)

---

## 1. Current State: E3/E4 Are Isolated

### What Exists (Unit-Tested)
- ✅ RelationshipState enum (ACCEPTED, REJECTED, UNRESOLVED)
- ✅ RelationshipEvidence model (matching_id, date_proximity, confidence)
- ✅ TransactionRelationship model (encounter→charge, charge→claim, claim→ack, ack→remittance)
- ✅ SuccessorMatcher class with check_missing_successors(), classify_actionable(), classify_delayed_successor()
- ✅ MissingSuccessorFinding and ActionableFinding models
- ✅ SupabaseWriter.write_relationships() method
- ✅ 35 unit tests (15 E3 + 20 E4)

### What's Missing (NOT Integrated)
- ❌ No relationship matching called during ingestion
- ❌ No successor detection called during claim staging
- ❌ No relationships populated on claim objects during pipeline
- ❌ No write_relationships() called after engine completes
- ❌ No successor findings included in LLM diagnosis payload
- ❌ No integration tests verifying end-to-end pipeline

### Current Pipeline (engine.py + main.py)
```python
RAW_CLAIMS (from Epic)
  ↓
Deidentifier.deidentify_batch()  # De-identify PHI
  ↓
ReconciliationEngine.diagnose_batch()  # Diagnose deadlocks
  ↓
LLM diagnosis  # Generate narrative
  ↓
SupabaseWriter.write_diagnostic_payload()  # Persist to Supabase
  ↓
END

E3/E4 UNUSED ← INTEGRATION POINT
```

---

## 2. Desired State: E3/E4 Fully Integrated

### Enhanced Pipeline

```python
RAW_CLAIMS (from Epic)
  ↓
Deidentifier.deidentify_batch()  # De-identify PHI
  ↓
RelationshipMatcher.match_relationships()  # E3: Extract relationships
  │  ↓
  │  Generate: relationships[] with ACCEPTED/REJECTED states
  ↓
Claim objects with relationships[] populated
  ↓
ReconciliationEngine.diagnose_batch()  # Diagnose deadlocks
  ↓
SuccessorMatcher.check_missing_successors()  # E4: Detect missing successors
  │  ↓
  │  Generate: missing, delayed, actionable, expired findings
  ↓
Findings combined with deadlock findings
  ↓
LLM diagnosis (includes successor findings)  # Generate narrative
  ↓
SupabaseWriter.write_diagnostic_payload()  # Persist claims
  ↓
SupabaseWriter.write_relationships()  # Persist relationships  ← E3
  ↓
END (with successor findings included)
```

---

## 3. Integration Tasks

### 3.1 Task 1: Create Relationship Matcher (NEW MODULE)

**File:** `waterfall_guard/matcher.py` (NEW)

**Purpose:** Extract and validate relationships from raw claim data

**Pseudocode:**
```python
class RelationshipMatcher:
    """Matches relationships between claim lifecycle events."""

    @staticmethod
    def match_encounter_to_charge(record: Dict) -> List[TransactionRelationship]:
        """Match encounter_id → charge_id if present."""
        if "encounter_id" in record and "charge_ids" in record:
            for charge_id in record["charge_ids"]:
                yield TransactionRelationship(
                    from_type=RecordType.ENCOUNTER,
                    from_id=record["encounter_id"],
                    to_type=RecordType.CHARGE,
                    to_id=charge_id,
                    relationship_state=RelationshipState.ACCEPTED,
                    evidence=[
                        RelationshipEvidence(
                            evidence_type=EvidenceType.MATCHING_ID,
                            supporting_id=record["encounter_id"],
                        )
                    ],
                )

    @staticmethod
    def match_charge_to_claim(record: Dict) -> List[TransactionRelationship]:
        """Match charge_id → claim_id if present."""
        if "charge_ids" in record and "token_id" in record:
            for charge_id in record["charge_ids"]:
                yield TransactionRelationship(
                    from_type=RecordType.CHARGE,
                    from_id=charge_id,
                    to_type=RecordType.CLAIM,
                    to_id=record["token_id"],
                    relationship_state=RelationshipState.ACCEPTED,
                    evidence=[RelationshipEvidence(evidence_type=EvidenceType.MATCHING_ID)],
                )

    @staticmethod
    def match_claim_to_ack(record: Dict) -> List[TransactionRelationship]:
        """Match claim_id → acknowledgment_id if claim is acknowledged."""
        if record.get("claim_status") == "acknowledged" and "ack_id" in record:
            yield TransactionRelationship(
                from_type=RecordType.CLAIM,
                from_id=record["token_id"],
                to_type=RecordType.ACKNOWLEDGMENT,
                to_id=record["ack_id"],
                relationship_state=RelationshipState.ACCEPTED,
                evidence=[...],
            )

    @staticmethod
    def match_ack_to_remittance(record: Dict) -> List[TransactionRelationship]:
        """Match acknowledgment_id → remittance_id if present."""
        if "ack_id" in record and "remittance_id" in record:
            yield TransactionRelationship(
                from_type=RecordType.ACKNOWLEDGMENT,
                from_id=record["ack_id"],
                to_type=RecordType.REMITTANCE,
                to_id=record["remittance_id"],
                relationship_state=RelationshipState.ACCEPTED,
                evidence=[...],
            )

    @staticmethod
    def extract_from_record(record: Dict) -> List[TransactionRelationship]:
        """Extract all relationships from a single claim record."""
        relationships = []
        relationships.extend(RelationshipMatcher.match_encounter_to_charge(record))
        relationships.extend(RelationshipMatcher.match_charge_to_claim(record))
        relationships.extend(RelationshipMatcher.match_claim_to_ack(record))
        relationships.extend(RelationshipMatcher.match_ack_to_remittance(record))
        return relationships

    @staticmethod
    def extract_batch(records: List[Dict]) -> List[TransactionRelationship]:
        """Extract relationships from a batch of records."""
        all_relationships = []
        for record in records:
            all_relationships.extend(RelationshipMatcher.extract_from_record(record))
        return all_relationships
```

**Tests:** `tests/test_matcher.py`
```python
def test_match_encounter_to_charge_creates_accepted_relationship():
    record = {"encounter_id": "E123", "charge_ids": ["C456", "C789"]}
    relationships = RelationshipMatcher.extract_from_record(record)
    assert len(relationships) == 2
    assert relationships[0].from_id == "E123"
    assert relationships[0].to_id == "C456"
    assert relationships[0].relationship_state == RelationshipState.ACCEPTED

def test_extract_batch_with_multiple_records():
    records = [
        {"encounter_id": "E1", "charge_ids": ["C1"]},
        {"encounter_id": "E2", "charge_ids": ["C2", "C3"]},
    ]
    relationships = RelationshipMatcher.extract_batch(records)
    assert len(relationships) == 3
```

---

### 3.2 Task 2: Integrate Relationship Matching into Pipeline

**File:** `waterfall_guard/main.py`

**Change:** Call RelationshipMatcher.extract_batch() before engine

**Code:**
```python
# In run_diagnostic_pipeline():

def run_diagnostic_pipeline(
    llm_client: Optional[DiagnosticLLMClient] = None,
    supabase_writer: Optional[SupabaseWriter] = None,
) -> Dict[str, Any]:
    """Enhanced pipeline: Epic ingestion → deident → relationships → engine → LLM."""
    
    # 1. Ingestion and deidentification (UNCHANGED)
    deidentifier = Deidentifier()
    rules = HospitalRuleSet.from_config(RULES_CONFIG)
    engine = ReconciliationEngine(rules)
    
    raw_claims = EpicClient().fetch_claims()
    deidentified_records = deidentifier.deidentify_batch(raw_claims)
    engine_records = [record.as_dict() for record in deidentified_records]
    
    # 2. E3: Extract relationships
    matcher = RelationshipMatcher()  # NEW
    relationships = matcher.extract_batch(raw_claims)  # NEW
    
    # 3. E4: Diagnose deadlocks (unchanged)
    findings = engine.diagnose_batch(engine_records)
    
    # 4. E4: Detect missing successors (NEW)
    successor_matcher = SuccessorMatcher()  # NEW
    successor_findings = []  # NEW
    for record in engine_records:  # NEW
        claim = {  # Convert record to Claim-like dict
            "token_id": record["token_id"],
            "claim_status": record.get("claim_status"),
            "created_date": record.get("created_date"),
            "acknowledgment_date": record.get("acknowledgment_date"),
            "filing_deadline": record.get("filing_deadline"),
        }
        missing_successors = successor_matcher.check_missing_successors(claim)  # NEW
        successor_findings.extend(missing_successors)  # NEW
    
    # 5. Build LLM payload (include successor findings)
    payload = engine.build_zdr_payload(findings)
    payload["successor_findings"] = [  # NEW
        {
            "token_id": f.token_id,
            "finding_type": f.finding_type.value,
            "reason": f.reason,
        }
        for f in successor_findings
    ]
    
    # 6. LLM diagnosis (UNCHANGED)
    client = llm_client or DiagnosticLLMClient(transport=_offline_demo_transport)
    result = client.diagnose(payload)
    
    # 7. Persistence (NEW: add relationships)
    writer = supabase_writer if supabase_writer is not None else SupabaseWriter()
    write_result = writer.write_diagnostic_payload(payload)
    write_relationships_result = writer.write_relationships(relationships, tenant_id)  # NEW
    
    return {
        "diagnostic_payload": payload,
        "llm_ok": result.ok,
        "llm_error": result.error,
        "diagnosis": result.parsed,
        "supabase_write_ok": write_result.ok,
        "supabase_write_error": write_result.error,
        "relationships_written": write_relationships_result.ok,  # NEW
        "relationships_error": write_relationships_result.error,  # NEW
    }
```

---

### 3.3 Task 3: Populate Relationships on Claim Objects

**File:** `waterfall_guard/models/claim.py`

**Current State:**
```python
@dataclass
class Claim:
    token_id: str
    charge_ids: List[str] = field(default_factory=list)
    # ... other fields
    relationships: List[TransactionRelationship] = field(default_factory=list)  # EXISTS
```

**No Change Needed** — relationships field already exists and is used in tests.

**Verification:** Ensure RelationshipMatcher populates this field during extraction.

---

### 3.4 Task 4: Populate Successor Findings in Engine

**File:** `waterfall_guard/engine.py`

**Change:** Add successor findings to DeadlockFinding or create SuccessorFinding model

**Current Code:**
```python
@dataclass
class DeadlockFinding:
    token_id: str
    stage: WaterfallStage
    deadlock_types: List[str]
    active_hold_names: List[str]
    eligible_wq_ids: List[str]
    unassigned_wq_ids: List[str]
    financial_impact: float = 0.0
    filing_deadline: Optional[str] = None
```

**Proposed Change:**
```python
@dataclass
class DeadlockFinding:
    token_id: str
    stage: WaterfallStage
    deadlock_types: List[str]
    active_hold_names: List[str]
    eligible_wq_ids: List[str]
    unassigned_wq_ids: List[str]
    financial_impact: float = 0.0
    filing_deadline: Optional[str] = None
    successor_findings: List[MissingSuccessorFinding] = field(default_factory=list)  # NEW
```

**Alternative:** Keep separate, don't modify DeadlockFinding.

---

### 3.5 Task 5: Add Integration Test

**File:** `tests/test_e3_e4_pipeline_integration.py` (NEW)

```python
import unittest
from waterfall_guard.matcher import RelationshipMatcher
from waterfall_guard.successors import SuccessorMatcher, SuccessorState
from waterfall_guard.models.claim import RelationshipState

class TestE3E4PipelineIntegration(unittest.TestCase):
    """Test E3/E4 integration into the full pipeline."""

    def test_relationship_extraction_populates_claim_relationships(self):
        """Test that relationships are extracted from raw claims."""
        raw_claims = [
            {
                "token_id": "CLM001",
                "encounter_id": "ENC001",
                "charge_ids": ["CHG001"],
                "claim_status": "submitted",
            }
        ]
        
        matcher = RelationshipMatcher()
        relationships = matcher.extract_batch(raw_claims)
        
        # Should create encounter→charge relationship
        assert len(relationships) >= 1
        encounter_to_charge = [r for r in relationships 
                               if r.from_type == "encounter" and r.to_type == "charge"]
        assert len(encounter_to_charge) >= 1
        assert encounter_to_charge[0].relationship_state == RelationshipState.ACCEPTED

    def test_successor_detection_flags_missing_acknowledgment(self):
        """Test that missing acknowledgments are detected."""
        claim = {
            "token_id": "CLM001",
            "claim_status": "submitted",  # Not acknowledged
            "created_date": "2026-10-10",  # Old enough to expect ack
            "acknowledgment_date": None,
            "filing_deadline": "2026-11-27",  # Future deadline
        }
        
        matcher = SuccessorMatcher()
        findings = matcher.check_missing_successors(claim)
        
        # Should flag missing acknowledgment
        missing_acks = [f for f in findings 
                       if f.finding_type == SuccessorState.MISSING_ACKNOWLEDGMENT]
        assert len(missing_acks) >= 1

    def test_unresolved_relationships_dont_produce_successor_findings(self):
        """Test that unresolved relationships are quarantined."""
        # If a relationship is UNRESOLVED (ambiguous), it should NOT count as
        # an accepted relationship for successor detection
        
        claim = {
            "token_id": "CLM001",
            "claim_status": "submitted",
            "ack_id": "ACK001",  # Potential ack, but relationship is UNRESOLVED
            "relationships": [
                {
                    "from_type": "claim",
                    "to_type": "acknowledgment",
                    "to_id": "ACK001",
                    "state": RelationshipState.UNRESOLVED,  # UNRESOLVED, not ACCEPTED
                }
            ],
            "filing_deadline": "2026-11-27",
        }
        
        matcher = SuccessorMatcher()
        findings = matcher.check_missing_successors(claim)
        
        # Should still flag as missing (because relationship is UNRESOLVED, not ACCEPTED)
        missing_acks = [f for f in findings 
                       if f.finding_type == SuccessorState.MISSING_ACKNOWLEDGMENT]
        assert len(missing_acks) >= 1, "Unresolved relationships should not count as successors"

    def test_actionable_claim_near_filing_deadline(self):
        """Test that actionable claims are classified correctly."""
        claim = {
            "token_id": "CLM001",
            "claim_status": "follow_up",
            "filing_deadline": "2026-10-28",  # Tomorrow (1 day away)
        }
        
        matcher = SuccessorMatcher()
        actionable = matcher.classify_actionable(claim)
        
        # Should be escalation_required (near deadline)
        assert actionable.finding_type == SuccessorState.ESCALATION_REQUIRED

    def test_expired_claim_past_filing_deadline(self):
        """Test that expired claims are classified correctly."""
        claim = {
            "token_id": "CLM001",
            "claim_status": "follow_up",
            "filing_deadline": "2026-10-26",  # Past (2 days ago)
        }
        
        matcher = SuccessorMatcher()
        expired = matcher.classify_actionable(claim)
        
        # Should be expired
        assert expired.finding_type == SuccessorState.EXPIRED

if __name__ == "__main__":
    unittest.main()
```

**Run Test:**
```bash
$ python3 -m pytest tests/test_e3_e4_pipeline_integration.py -v
```

---

### 3.6 Task 6: Update SupabaseWriter.write_relationships()

**File:** `waterfall_guard/integrations/supabase_writer.py`

**Current Implementation:** Already exists but not called

**Verification:** Ensure tenant_id is auto-injected and error handling is correct

```python
def write_relationships(
    self,
    relationships: List[TransactionRelationship],
    tenant_id: str,
) -> WriteResult:
    """Write relationships to Supabase, auto-injecting tenant_id.
    
    Args:
        relationships: List of TransactionRelationship objects
        tenant_id: Tenant ID (auto-injected for isolation)
    
    Returns:
        WriteResult with ok flag and error message if failed
    """
    if not self.enabled:
        return WriteResult(ok=False, error="Supabase not configured")
    
    if not relationships:
        return WriteResult(ok=True, error=None)  # No-op success
    
    rows = [
        {
            "tenant_id": tenant_id,  # AUTO-INJECT
            "from_type": rel.from_type.value,
            "from_id": rel.from_id,
            "to_type": rel.to_type.value,
            "to_id": rel.to_id,
            "relationship_state": rel.relationship_state.value,
            "evidence": rel.evidence_as_dict(),
        }
        for rel in relationships
    ]
    
    return self.write_rows("relationships", rows)
```

---

## 4. Implementation Checklist

### Phase 1: Setup (0.5 hours)
- [ ] Create `waterfall_guard/matcher.py` with RelationshipMatcher class
- [ ] Create `tests/test_matcher.py` with unit tests
- [ ] Create `tests/test_e3_e4_pipeline_integration.py` with integration tests
- [ ] Import SuccessorMatcher in main.py

### Phase 2: Integration (2–3 hours)
- [ ] Call RelationshipMatcher.extract_batch() in run_diagnostic_pipeline()
- [ ] Call SuccessorMatcher.check_missing_successors() for each claim
- [ ] Populate payload with successor_findings
- [ ] Call write_relationships() in SupabaseWriter
- [ ] Add tenant_id to write_relationships() calls

### Phase 3: Testing (1–2 hours)
- [ ] Run `python3 -m pytest tests/test_matcher.py -v`
- [ ] Run `python3 -m pytest tests/test_e3_e4_pipeline_integration.py -v`
- [ ] Run full test suite: `python3 -m pytest tests/ -v` (should be 200+ tests)
- [ ] Manual integration test with synthetic data
- [ ] Verify relationships are persisted to Supabase (after migrations applied)

### Phase 4: Documentation (0.5 hours)
- [ ] Update README with E3/E4 integration notes
- [ ] Update main.py docstring with new pipeline flow
- [ ] Add architectural diagram to docs/

---

## 5. Success Criteria

After integration, verify:

- [ ] ✅ RelationshipMatcher correctly extracts 4 lifecycle relationships (encounter→charge, charge→claim, claim→ack, ack→remittance)
- [ ] ✅ SuccessorMatcher correctly detects missing, delayed, actionable, and expired claims
- [ ] ✅ Unresolved relationships don't produce false successor findings
- [ ] ✅ ACCEPTED relationships point to real, validated target records
- [ ] ✅ write_relationships() persists to Supabase with tenant_id auto-injected
- [ ] ✅ All integration tests pass: `python3 -m pytest tests/test_e3_e4_pipeline_integration.py -v`
- [ ] ✅ Full test suite passes: `python3 -m pytest tests/ -v` (200+ tests)
- [ ] ✅ LLM diagnosis payload includes successor_findings
- [ ] ✅ Audit logs include relationship extraction and successor detection steps

---

## 6. Risk Mitigation

**Risk 1: Relationship extraction misses some lifecycle paths**
- Mitigation: Unit tests verify all 4 types. Review raw claim schema to ensure all relevant fields are present.

**Risk 2: Successor findings are too noisy or too conservative**
- Mitigation: Tune thresholds (expected_days_to_acknowledge, near_deadline_threshold). Add configuration to HospitalRuleSet.

**Risk 3: Performance impact of relationship extraction**
- Mitigation: Relationship extraction is O(n) where n = number of claims. For 1000 claims, ~10ms. No performance risk.

**Risk 4: Relationships not persisted if Supabase migration not applied**
- Mitigation: SupabaseWriter soft-fails; pipeline completes even if persistence fails. Document migration prerequisite.

**Risk 5: Cross-tenant data leakage if RLS policy not fixed**
- Mitigation: Update RLS policy before production. Test with real Supabase on staging.

---

## 7. Timeline and Next Steps

**Estimated total effort:** 4–6 hours (1 developer, 1 day)

**Next immediate steps:**
1. ✅ Read this roadmap (done)
2. ⏳ Create RelationshipMatcher class and unit tests (~1 hour)
3. ⏳ Integrate into main.py pipeline (~1 hour)
4. ⏳ Add integration tests (~1 hour)
5. ⏳ Update database migrations and RLS policies (~0.5 hours)
6. ⏳ Run full test suite and verify all tests pass (~0.5 hours)
7. ⏳ Manual staging validation (~1 hour)

**Blocking dependencies:**
- Supabase migration applied (required for write_relationships persistence)
- RLS policy updated to JWT-based (required for cross-tenant isolation)
- Staging Supabase environment available

---

**Document Version:** 1.0  
**Date:** 2026-10-27  
**Status:** Ready for implementation sprint
