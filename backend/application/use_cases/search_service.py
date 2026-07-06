from typing import List, Optional
from infrastructure.database.orm.models import Document, Company
from domains.shared.uow import UnitOfWork

class SearchService:
    """
    Provides fast, deterministic indexing searches across documents via PostgreSQL.
    No Elasticsearch.
    """
    def __init__(self, uow: UnitOfWork):
        self.uow = uow

    def search(
        self,
        uuid_cfdi: Optional[str] = None,
        rfc: Optional[str] = None,
        hash_sha256: Optional[str] = None,
        referencia_bancaria: Optional[str] = None,
        banco: Optional[str] = None,
        empresa_id: Optional[str] = None,
        periodo: Optional[int] = None,
        ejercicio: Optional[int] = None,
        tipo_documento: Optional[str] = None
    ) -> List[Document]:
        with self.uow:
            query = self.uow.session.query(Document)
            
            if uuid_cfdi:
                query = query.filter(Document.uuid_cfdi == uuid_cfdi)
            if hash_sha256:
                query = query.filter(Document.hash_sha256 == hash_sha256)
            if referencia_bancaria:
                query = query.filter(Document.referencia_bancaria == referencia_bancaria)
            if banco:
                query = query.filter(Document.banco == banco)
            if empresa_id:
                query = query.filter(Document.company_id == empresa_id)
            if periodo is not None:
                query = query.filter(Document.periodo == periodo)
            if ejercicio is not None:
                query = query.filter(Document.ejercicio == ejercicio)
            if tipo_documento:
                query = query.filter(Document.tipo == tipo_documento)
            
            if rfc:
                # Join with company to filter by RFC
                query = query.join(Company, Document.company_id == Company.id).filter(Company.rfc == rfc)

            return query.all()
