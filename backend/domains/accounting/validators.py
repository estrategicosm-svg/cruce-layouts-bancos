from decimal import Decimal
from domains.accounting.models import AccountingProposal, AccountingProposalStatus
from domains.accounting.exceptions import AccountingValidationError

def validate_proposal(proposal: AccountingProposal):
    # 1. Check double entry balance (Cargos == Abonos)
    # Using a small tolerance for floating point / decimal arithmetic safety if needed, 
    # but with Decimals it should be exact.
    if proposal.total_cargos != proposal.total_abonos:
        raise AccountingValidationError(
            f"Descuadre contable detectado. Cargos: {proposal.total_cargos} != Abonos: {proposal.total_abonos}"
        )
    
    # 2. Check empty entries
    if not proposal.entries:
        raise AccountingValidationError("La propuesta contable no tiene asientos.")
        
    # 3. Check reference links
    if not (proposal.document_uuid or proposal.transaction_uuid or proposal.xml_uuid):
        raise AccountingValidationError("La póliza debe estar vinculada al menos a un Documento, Transacción o XML.")

    proposal.status = AccountingProposalStatus.VALIDATED
