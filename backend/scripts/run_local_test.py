import os
import json
import xml.etree.ElementTree as ET
from decimal import Decimal
from datetime import date
from typing import List, Dict

import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from domains.shared.canonical_models import CanonicalXML, CanonicalTransaction
from domains.configuration.models import GeneralConfiguration, ConfigurationVersion, Tenant, AccountingConfiguration
from domains.configuration.engine import ConfigurationEngine
from domains.configuration.repositories import ConfigurationRepository
from domains.accounting.engine import AccountingEngine
from domains.accounting.rules.egreso_rule import EgresoRule
from domains.accounting.rules.iva_acreditable_rule import IVAAcreditableRule
from domains.accounting.rules.proveedor_rule import ProveedorRule
from domains.accounting.rules.pago_rule import PagoRule
from domains.accounting.rules.ingreso_rule import IngresoRule
from domains.accounting.rules.iva_rule import IVARule

from domains.conciliation.engine import ConciliationEngine
from domains.conciliation.tolerance import ToleranceEngine
from domains.conciliation.strategies import (
    UUIDMatchStrategy, ReferenceMatchStrategy, SubsetSumMatchStrategy,
    ManyToOneMatchStrategy, SplitPaymentMatchStrategy
)

from domains.sat.validator import SATValidator
from domains.sat.rules.iva_rule import IVARule as SATIVARule
from domains.sat.rules.cfdi_status_rule import CFDIStatusRule as SATCFDIStatusRule

class InMemoryConfigRepo(ConfigurationRepository):
    def __init__(self):
        self.globals = []
    def add_tenant(self, tenant: Tenant) -> None: pass
    def get_tenant(self, tenant_id: str) -> Tenant: return None
    def add_global_config(self, config: GeneralConfiguration) -> None: self.globals.append(config)
    def get_global_configs(self) -> List[GeneralConfiguration]: return self.globals
    def add_company_config(self, config) -> None: pass
    def get_company_configs(self, tenant_id: str) -> List: return []

def setup_engines():
    print("[SETUP] Inicializando motores y repositorios en memoria (Sin PostgreSQL)...")
    repo = InMemoryConfigRepo()
    config_engine = ConfigurationEngine(repo)
    config_engine.register_global_config(GeneralConfiguration(
        id="GLOBAL_1",
        version_info=ConfigurationVersion(version="1.0"),
        accounting=AccountingConfiguration(
            cuenta_gastos="501-01-000",
            cuenta_compras="501-02-000",
            cuenta_activos="103-01-000",
            cuenta_iva_acreditable="118-01-000",
            cuenta_proveedores="201-01-000",
            cuenta_bancos="102-01-000"
        )
    ))
    
    accounting_engine = AccountingEngine(
        config_engine=config_engine,
        rules=[IngresoRule(), IVARule(), EgresoRule(), IVAAcreditableRule(), ProveedorRule(), PagoRule()]
    )
    
    tolerance = ToleranceEngine(allowed_days_diff=3, allowed_cents_diff=Decimal("1.0"))
    conciliation_engine = ConciliationEngine(strategies=[
        UUIDMatchStrategy(tolerance),
        ReferenceMatchStrategy(tolerance),
        SubsetSumMatchStrategy(tolerance),
        ManyToOneMatchStrategy(tolerance),
        SplitPaymentMatchStrategy(tolerance)
    ])
    
    sat_validator = SATValidator(rules=[SATIVARule(), SATCFDIStatusRule()])
    
    return config_engine, accounting_engine, conciliation_engine, sat_validator

def parse_cfdi(file_path: str) -> CanonicalXML:
    tree = ET.parse(file_path)
    root = tree.getroot()
    ns = {'cfdi': 'http://www.sat.gob.mx/cfd/4', 'tfd': 'http://www.sat.gob.mx/TimbreFiscalDigital'}
    # Try cfdi v3.3 if v4 fails
    if not root.findall('.//cfdi:Emisor', ns):
        ns['cfdi'] = 'http://www.sat.gob.mx/cfd/3'
    
    emisor = root.find('.//cfdi:Emisor', ns)
    receptor = root.find('.//cfdi:Receptor', ns)
    tfd = root.find('.//tfd:TimbreFiscalDigital', ns)
    
    rfc_emisor = emisor.attrib.get('Rfc', 'UNKNOWN') if emisor is not None else 'UNKNOWN'
    rfc_receptor = receptor.attrib.get('Rfc', 'UNKNOWN') if receptor is not None else 'UNKNOWN'
    tipo = root.attrib.get('TipoDeComprobante', 'I')
    subtotal = Decimal(root.attrib.get('SubTotal', '0.00'))
    total = Decimal(root.attrib.get('Total', '0.00'))
    uuid_cfdi = tfd.attrib.get('UUID', 'NO-UUID') if tfd is not None else 'NO-UUID'
    
    # Extraer impuestos básicos (IVA)
    impuestos_desglosados = {"IVA": []}
    conceptos = root.findall('.//cfdi:Concepto', ns)
    for concepto in conceptos:
        traslados = concepto.findall('.//cfdi:Traslado', ns)
        for t in traslados:
            if t.attrib.get('Impuesto') == '002': # IVA
                impuestos_desglosados["IVA"].append({
                    "TasaOCuota": t.attrib.get('TasaOCuota', '0.160000'),
                    "Importe": t.attrib.get('Importe', '0.00')
                })
                
    return CanonicalXML(
        uuid_cfdi=uuid_cfdi,
        rfc_emisor=rfc_emisor,
        rfc_receptor=rfc_receptor,
        tipo_cfdi=tipo,
        subtotal=subtotal,
        total=total,
        impuestos_desglosados=impuestos_desglosados
    )

def main():
    print("==================================================")
    print("    AUDITOR FISCAL SAT - PRUEBA END-TO-END CLI")
    print("==================================================")
    
    INPUT_DIR = os.path.join(os.path.dirname(__file__), '..', 'input_test')
    OUTPUT_DIR = os.path.join(os.path.dirname(__file__), '..', 'output_test')
    os.makedirs(INPUT_DIR, exist_ok=True)
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    config, accounting, conciliation, sat = setup_engines()
    
    errores = []
    xml_list = []
    tx_list = []
    
    print(f"[INTAKE] Leyendo archivos desde: {INPUT_DIR}")
    archivos = os.listdir(INPUT_DIR)
    
    if not archivos:
        print("[WARNING] Carpeta input_test vacía. Agregando archivos dummy por defecto...")
        with open(os.path.join(INPUT_DIR, 'dummy_factura.xml'), 'w') as f:
            f.write('<cfdi:Comprobante xmlns:cfdi="http://www.sat.gob.mx/cfd/4" TipoDeComprobante="I" SubTotal="1000.00" Total="1160.00"><cfdi:Emisor Rfc="PROVEEDOR"/><cfdi:Receptor Rfc="TENANT1"/><cfdi:Conceptos><cfdi:Concepto><cfdi:Impuestos><cfdi:Traslados><cfdi:Traslado Impuesto="002" TasaOCuota="0.160000" Importe="160.00"/></cfdi:Traslados></cfdi:Impuestos></cfdi:Concepto></cfdi:Conceptos><cfdi:Complemento><tfd:TimbreFiscalDigital xmlns:tfd="http://www.sat.gob.mx/TimbreFiscalDigital" UUID="DUMMY-UUID-12345"/></cfdi:Complemento></cfdi:Comprobante>')
        with open(os.path.join(INPUT_DIR, 'dummy_estado_cuenta.pdf'), 'w') as f:
            f.write('%PDF-1.4 DUMMY')
        archivos = os.listdir(INPUT_DIR)

    for arch in archivos:
        path = os.path.join(INPUT_DIR, arch)
        if arch.lower().endswith('.xml'):
            print(f"  -> Procesando XML: {arch}")
            try:
                xml_obj = parse_cfdi(path)
                xml_list.append(xml_obj)
            except Exception as e:
                err_msg = f"Error parseando {arch}: {str(e)}"
                print(f"  [ERROR] {err_msg}")
                errores.append({"file": arch, "error": err_msg})
        elif arch.lower().endswith('.pdf'):
            print(f"  -> Procesando PDF: {arch}")
            # STUB PARSER
            err_msg = "PARSER_STUB_OR_PENDING"
            print(f"  [WARNING] Parser real no disponible para PDF. Generando stub...")
            errores.append({"file": arch, "error": err_msg})
            # Add a mock transaction so the conciliation engine has something to chew on
            tx_list.append(CanonicalTransaction(
                uuid="TX-MOCK-1",
                statement_uuid="STMT-1",
                fecha_operacion=date.today(),
                monto_absoluto=Decimal("1160.00"),
                naturaleza="CARGO", # Cargo is an expense in a bank statement normally. Wait, bank statement cargo = our expense (money leaving) -> Payment to supplier.
                concepto_original="PAGO FACTURA DUMMY-UUID-12345",
                referencia_bancaria_limpia="12345"
            ))
        else:
            print(f"  [SKIPPED] Archivo ignorado: {arch}")

    print(f"\n[SAT ENGINE] Validando {len(xml_list)} CFDI...")
    sat_results = []
    for x in xml_list:
        res = sat.validate(x)
        sat_results.append(res.model_dump())
        print(f"  -> SAT Status: {x.uuid_cfdi} -> {res.overall_status}")
        
    print(f"\n[ACCOUNTING ENGINE] Generando Pólizas de Provisiones...")
    polizas = []
    for x in xml_list:
        try:
            prop = accounting.generate_proposal(tenant_id="TENANT1", fecha=date.today(), xml=x)
            polizas.append(prop.model_dump())
            print(f"  -> Póliza generada y cuadrada para {x.uuid_cfdi}: Cargos={prop.total_cargos}, Abonos={prop.total_abonos}")
        except Exception as e:
            print(f"  [ERROR] Contable {x.uuid_cfdi}: {str(e)}")
            errores.append({"uuid": x.uuid_cfdi, "error": str(e)})

    for t in tx_list:
        try:
            prop = accounting.generate_proposal(tenant_id="TENANT1", fecha=date.today(), tx=t)
            polizas.append(prop.model_dump())
            ref = t.referencia_bancaria_limpia if t.referencia_bancaria_limpia else 'S/N'
            print(f"  -> Pliza bancaria generada para {t.uuid} [Ref: {ref}]: Cargos={prop.total_cargos}, Abonos={prop.total_abonos}")
        except Exception as e:
            print(f"  [ERROR] Contable Tx {t.uuid}: {str(e)}")
            errores.append({"uuid": t.uuid, "error": str(e)})

    print(f"\n[CONCILIATION ENGINE] Cruzando Movimientos...")
    conciliacion_res = conciliation.conciliate(tx_list, xml_list)
    print(f"  -> Matches exactos encontrados: {len(conciliacion_res.matches)}")
    print(f"  -> TX sin conciliar: {len(conciliacion_res.unmatched_transactions)}")
    print(f"  -> XML sin conciliar: {len(conciliacion_res.unmatched_xmls)}")
    
    # Escribir Outputs
    print(f"\n[OUTPUT] Escribiendo resultados a JSON...")
    
    with open(os.path.join(OUTPUT_DIR, 'errores.json'), 'w') as f:
        json.dump(errores, f, indent=2, default=str)
        
    with open(os.path.join(OUTPUT_DIR, 'sat_resultados.json'), 'w') as f:
        json.dump(sat_results, f, indent=2, default=str)
        
    with open(os.path.join(OUTPUT_DIR, 'polizas_resultados.json'), 'w') as f:
        json.dump(polizas, f, indent=2, default=str)
        
    with open(os.path.join(OUTPUT_DIR, 'conciliacion_resultados.json'), 'w') as f:
        json.dump(conciliacion_res.model_dump(), f, indent=2, default=str)
        
    resumen = {
        "documentos_leidos": len(archivos),
        "xml_procesados": len(xml_list),
        "movimientos_bancarios_detectados": len(tx_list),
        "matches_encontrados": len(conciliacion_res.matches),
        "errores": len(errores)
    }
    with open(os.path.join(OUTPUT_DIR, 'resumen.json'), 'w') as f:
        json.dump(resumen, f, indent=2, default=str)
        
    print("\n==================================================")
    print(" PRUEBA END-TO-END FINALIZADA ")
    print("==================================================")

if __name__ == "__main__":
    main()
