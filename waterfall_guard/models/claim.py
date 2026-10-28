from datetime import datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel


class ClaimStatus(str, Enum):
    SUBMITTED = "submitted"
    ACKNOWLEDGED = "acknowledged"
    IN_ADJUDICATION = "in_adjudication"
    PAID = "paid"
    DENIED = "denied"
    REJECTED = "rejected"


class RelationshipState(str, Enum):
    """Transaction relationship matching state (E3)."""
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    UNRESOLVED = "unresolved"


class RelationshipEvidence(BaseModel):
    """Evidence supporting or rejecting a transaction relationship (E3)."""
    evidence_type: str  # e.g., "matching_id", "date_proximity", "amount_tolerance", "conflicting_id"
    evidence_value: str  # e.g., "claim_id matches", "7 days apart", "within 0.01%", "different payer"
    source: str  # e.g., "epic_claim_id", "submitted_date", "amount_field", "payer_field"
    confidence_score: float  # 0.0-1.0; used to disambiguate multiple candidates


class TransactionRelationship(BaseModel):
    """Explicit relationship between transactions: encounter→charge→claim→ack→remittance (E3)."""
    from_type: str  # "encounter", "charge", "claim", "acknowledgment", "remittance"
    from_id: str  # encounter_id, charge_id, claim_id, ack_id, remit_id
    to_type: str  # target transaction type
    to_id: str  # target transaction ID
    state: RelationshipState  # ACCEPTED, REJECTED, UNRESOLVED
    evidence: List[RelationshipEvidence]  # why relationship was accepted/rejected/unresolved
    created_at: Optional[datetime] = None  # set by persistence layer


class Claim(BaseModel):
    claim_id: str
    patient_id: str
    payer: str
    status: ClaimStatus
    amount: float
    submitted_at: datetime
    last_status_change_at: datetime
    expected_response_by: Optional[datetime] = None
    
    # E3: Transaction-specific relationships
    encounter_id: Optional[str] = None  # Associated encounter
    charge_ids: List[str] = []  # Charges grouped into this claim
    acknowledgment_id: Optional[str] = None  # Payer acknowledgment
    remittance_id: Optional[str] = None  # Payment or denial remittance
    relationships: List[TransactionRelationship] = []  # Explicit lifecycle chain
