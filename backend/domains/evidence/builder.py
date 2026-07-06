from typing import List, Optional
from domains.evidence.models import EvidencePackage, EvidenceItem, EvidenceReference, EvidenceType, EvidenceStatus
from domains.shared.canonical_models import CanonicalDocument, CanonicalTransaction, CanonicalXML
from domains.sat.models import SATValidationResult
from domains.conciliation.models import MatchResult
from domains.workflow.models import WorkflowEventDomain
from uuid_utils import uuid7

class EvidenceBuilder:
    """
    Deterministically builds an EvidencePackage from various domain outputs.
    """
    def __init__(self, document: CanonicalDocument, workflow_history: List[WorkflowEventDomain]):
        self.document = document
        self.workflow_history = [w.dict() for w in workflow_history]
        self.items: List[EvidenceItem] = []
        
        # Base document evidence
        self.add_item(
            evidence_type=EvidenceType.HASH_DOCUMENTAL,
            content={"sha256": document.hash_sha256, "fingerprint": getattr(document, "fingerprint", None)},
            references=[EvidenceReference(target_uuid=document.uuid, target_type="DOCUMENT", description="Root Document")]
        )

    def add_item(self, evidence_type: EvidenceType, content: dict, references: List[EvidenceReference] = None) -> None:
        self.items.append(
            EvidenceItem(
                item_id=str(uuid7()),
                evidence_type=evidence_type,
                content=content,
                references=references or []
            )
        )

    def attach_transaction(self, tx: CanonicalTransaction) -> None:
        self.add_item(
            evidence_type=EvidenceType.TRANSACCION_BANCARIA,
            content=tx.dict(),
            references=[
                EvidenceReference(target_uuid=tx.uuid, target_type="TRANSACTION", description="Extracted Transaction"),
                EvidenceReference(target_uuid=self.document.uuid, target_type="DOCUMENT", description="Source Document")
            ]
        )

    def attach_xml(self, xml: CanonicalXML) -> None:
        self.add_item(
            evidence_type=EvidenceType.XML_CFDI,
            content=xml.dict(),
            references=[
                EvidenceReference(target_uuid=xml.uuid_cfdi, target_type="XML", description="Extracted CFDI"),
                EvidenceReference(target_uuid=self.document.uuid, target_type="DOCUMENT", description="Source Document")
            ]
        )

    def attach_sat_validation(self, sat_result: SATValidationResult) -> None:
        self.add_item(
            evidence_type=EvidenceType.RESULTADO_SAT,
            content=sat_result.dict(),
            references=[
                EvidenceReference(target_uuid=sat_result.uuid_cfdi, target_type="XML", description="Validated CFDI")
            ]
        )

    def attach_match_result(self, match: MatchResult) -> None:
        # For simplicity, attaching the whole match result. In reality, we could map individual matches.
        for m in match.matches:
            self.add_item(
                evidence_type=EvidenceType.MATCH_CONCILIACION,
                content={"status": m.status.value, "explanations": [e.dict() for e in m.explanations]},
                references=[
                    EvidenceReference(target_uuid=m.transaction.uuid, target_type="TRANSACTION", description="Matched Transaction"),
                    EvidenceReference(target_uuid=m.xml.uuid_cfdi, target_type="XML", description="Matched XML")
                ]
            )

    def build(self) -> EvidencePackage:
        pkg = EvidencePackage(
            package_uuid=str(uuid7()),
            document_uuid=self.document.uuid,
            empresa_id=self.document.empresa_rfc, # Simplification
            sha256=self.document.hash_sha256,
            fingerprint=getattr(self.document, "fingerprint", self.document.hash_sha256),
            workflow_history=self.workflow_history,
            items=self.items,
            status=EvidenceStatus.SEALED
        )
        pkg.validate_integrity()
        return pkg
