import os
import sys

# Ensure backend is in PYTHONPATH
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from infrastructure.database.orm.base import Base
from infrastructure.database.uow import SQLAlchemyUnitOfWork
from use_cases.process_files import ProcessFilesAndPersistUseCase
from application.use_cases.generate_tax_file import GenerateTaxFileUseCase

def generate_sample_tax_file():
    # 1. Setup in-memory DB and engines
    engine = create_engine('sqlite:///:memory:')
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    uow = SQLAlchemyUnitOfWork(session_factory)
    
    process_use_case = ProcessFilesAndPersistUseCase(uow)
    reporting_use_case = GenerateTaxFileUseCase(uow)
    
    # 2. Create a dummy XML file
    dummy_xml_path = "dummy_sample.xml"
    with open(dummy_xml_path, 'w') as f:
        f.write('<cfdi:Comprobante xmlns:cfdi="http://www.sat.gob.mx/cfd/4" TipoDeComprobante="I" SubTotal="5000.00" Total="5800.00"><cfdi:Emisor Rfc="PROVEEDOR_MUESTRA"/><cfdi:Receptor Rfc="TENANT1"/><cfdi:Conceptos><cfdi:Concepto><cfdi:Impuestos><cfdi:Traslados><cfdi:Traslado Impuesto="002" TasaOCuota="0.160000" Importe="800.00"/></cfdi:Traslados></cfdi:Impuestos></cfdi:Concepto></cfdi:Conceptos><cfdi:Complemento><tfd:TimbreFiscalDigital xmlns:tfd="http://www.sat.gob.mx/TimbreFiscalDigital" UUID="SAMPLE-UUID-77777"/></cfdi:Complemento></cfdi:Comprobante>')
        
    try:
        # 3. Process the file
        print("Procesando archivo dummy...")
        run_id = process_use_case.execute([dummy_xml_path], "TENANT1")
        print(f"Archivo procesado. Processing Run ID: {run_id}")
        
        # 4. Generate the Tax File (Expediente Electrónico)
        print("Generando Expediente Electrónico SAT...")
        audit_file = reporting_use_case.execute(run_id)
        
        # 5. Export to JSON
        json_output_path = "sample_tax_file.json"
        with open(json_output_path, 'w', encoding='utf-8') as f:
            f.write(audit_file.to_json())
            
        print(f"Expediente generado exitosamente y guardado en: {json_output_path}")
    finally:
        if os.path.exists(dummy_xml_path):
            os.remove(dummy_xml_path)

if __name__ == "__main__":
    generate_sample_tax_file()
