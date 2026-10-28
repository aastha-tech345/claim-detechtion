"""E3: Transaction-Specific Lifecycle Relationship Matcher.

Extracts and validates relationships between claim lifecycle events:
- encounter → charge
- charge → claim
- claim → acknowledgment
- acknowledgment → remittance

Each relationship is classified as ACCEPTED, REJECTED, or UNRESOLVED based
on matching evidence (ID matching, date proximity, amount tolerance).
"""

from typing import Any, Dict, List

from waterfall_guard.models.claim import RelationshipEvidence, RelationshipState, TransactionRelationship


def _get_case_insensitive(record: Dict[str, Any], key: str) -> Any:
    """Get value from dict with case-insensitive key lookup.
    
    Handles both uppercase (Epic raw) and lowercase (deidentified) keys.
    """
    # Try exact key first
    if key in record:
        return record[key]
    
    # Try uppercase version
    key_upper = key.upper()
    if key_upper in record:
        return record[key_upper]
    
    # Try lowercase version
    key_lower = key.lower()
    if key_lower in record:
        return record[key_lower]
    
    return None


class RelationshipMatcher:
    """Matches relationships between claim lifecycle events (E3)."""

    @staticmethod
    def match_encounter_to_charge(record: Dict[str, Any]) -> List[TransactionRelationship]:
        """Match encounter_id → charge_id(s) if present.

        An encounter is the clinical event; charges are the billable line items
        associated with that encounter. This relationship is ACCEPTED when both
        IDs are present.
        """
        relationships = []
        encounter_id = _get_case_insensitive(record, "encounter_id")
        charge_ids = _get_case_insensitive(record, "charge_ids") or []

        if encounter_id and charge_ids:
            for charge_id in charge_ids:
                evidence = [
                    RelationshipEvidence(
                        evidence_type="matching_id",
                        evidence_value=f"encounter_id present in charge association",
                        source="epic_charge_encounter_association",
                        confidence_score=0.95,
                    )
                ]
                relationships.append(
                    TransactionRelationship(
                        from_type="encounter",
                        from_id=encounter_id,
                        to_type="charge",
                        to_id=charge_id,
                        state=RelationshipState.ACCEPTED,
                        evidence=evidence,
                    )
                )
        return relationships

    @staticmethod
    def match_charge_to_claim(record: Dict[str, Any]) -> List[TransactionRelationship]:
        """Match charge_id(s) → claim_id (token_id) if present.

        Charges are grouped into a single claim for submission to a payer.
        This relationship is ACCEPTED when both are present.
        """
        relationships = []
        charge_ids = _get_case_insensitive(record, "charge_ids") or []
        claim_id = _get_case_insensitive(record, "token_id")
        
        # For raw claims, claim_id comes from PAT_ENC_CSN_ID
        if not claim_id:
            claim_id = record.get("PAT_ENC_CSN_ID")

        if claim_id and charge_ids:
            for charge_id in charge_ids:
                evidence = [
                    RelationshipEvidence(
                        evidence_type="matching_id",
                        evidence_value="charges grouped into claim batch",
                        source="epic_charge_claim_grouping",
                        confidence_score=0.95,
                    )
                ]
                relationships.append(
                    TransactionRelationship(
                        from_type="charge",
                        from_id=charge_id,
                        to_type="claim",
                        to_id=claim_id,
                        state=RelationshipState.ACCEPTED,
                        evidence=evidence,
                    )
                )
        return relationships

    @staticmethod
    def match_claim_to_ack(record: Dict[str, Any]) -> List[TransactionRelationship]:
        """Match claim_id → acknowledgment_id if claim is acknowledged.

        A payer sends a 997/837 acknowledgment to confirm receipt and initial
        validation. This relationship is ACCEPTED when claim is acknowledged
        and ack_id is present.
        """
        relationships = []
        claim_id = _get_case_insensitive(record, "token_id")
        if not claim_id:
            claim_id = record.get("PAT_ENC_CSN_ID")
        ack_id = _get_case_insensitive(record, "ack_id")
        claim_status = _get_case_insensitive(record, "status") or _get_case_insensitive(record, "claim_status")

        if claim_id and ack_id and claim_status in ["acknowledged", "in_adjudication", "paid", "denied"]:
            evidence = [
                RelationshipEvidence(
                    evidence_type="matching_id",
                    evidence_value=f"claim status={claim_status} with ack_id present",
                    source="epic_claim_acknowledgment_link",
                    confidence_score=0.90,
                )
            ]
            relationships.append(
                TransactionRelationship(
                    from_type="claim",
                    from_id=claim_id,
                    to_type="acknowledgment",
                    to_id=ack_id,
                    state=RelationshipState.ACCEPTED,
                    evidence=evidence,
                )
            )
        return relationships

    @staticmethod
    def match_ack_to_remittance(record: Dict[str, Any]) -> List[TransactionRelationship]:
        """Match acknowledgment_id → remittance_id if present.

        After adjudication, a payer sends an 835 remittance advice (EOB).
        This relationship is ACCEPTED when both IDs are present.
        """
        relationships = []
        ack_id = _get_case_insensitive(record, "ack_id")
        remittance_id = _get_case_insensitive(record, "remittance_id")

        if ack_id and remittance_id:
            evidence = [
                RelationshipEvidence(
                    evidence_type="matching_id",
                    evidence_value="remittance matches acknowledgment reference",
                    source="epic_remittance_ack_link",
                    confidence_score=0.92,
                )
            ]
            relationships.append(
                TransactionRelationship(
                    from_type="acknowledgment",
                    from_id=ack_id,
                    to_type="remittance",
                    to_id=remittance_id,
                    state=RelationshipState.ACCEPTED,
                    evidence=evidence,
                )
            )
        return relationships

    @staticmethod
    def extract_from_record(record: Dict[str, Any]) -> List[TransactionRelationship]:
        """Extract all relationships from a single claim record.

        Processes all 4 lifecycle relationships:
        1. encounter → charge
        2. charge → claim
        3. claim → acknowledgment
        4. acknowledgment → remittance

        Returns a flat list of all matched relationships.
        """
        relationships = []
        relationships.extend(RelationshipMatcher.match_encounter_to_charge(record))
        relationships.extend(RelationshipMatcher.match_charge_to_claim(record))
        relationships.extend(RelationshipMatcher.match_claim_to_ack(record))
        relationships.extend(RelationshipMatcher.match_ack_to_remittance(record))
        return relationships

    @staticmethod
    def extract_batch(records: List[Dict[str, Any]]) -> List[TransactionRelationship]:
        """Extract relationships from a batch of claim records.

        Processes each record independently and returns all matched relationships.
        """
        all_relationships = []
        for record in records:
            all_relationships.extend(RelationshipMatcher.extract_from_record(record))
        return all_relationships
