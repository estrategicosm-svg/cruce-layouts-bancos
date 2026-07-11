"""Tests for ZIP bank statement processing, split XML uploaders, and moneda handling.

Covers mandatory requirements:
- ZIP bank statements accepted and processed
- Split XML emitidos/recibidos with origen_xml
- Multi-currency preservation (no global moneda)
- Error-per-file resilience
- Path traversal prevention
- Control table generation
"""
from __future__ import annotations

import io
import os
import tempfile
import zipfile
from datetime import datetime
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from core.models import CFDI, CedulaIngresoRegistro, MovimientoBancario
from parsers.xml_parser import XMLParser, ParseZipResult


# --- Helpers ---

def _crear_zip_bancario_excel(movimientos: list[dict]) -> bytes:
    """Create a ZIP containing a single Excel bank statement."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        df = pd.DataFrame(movimientos)
        excel_buf = io.BytesIO()
        df.to_excel(excel_buf, index=False)
        zf.writestr("estados/BANX_Enero.xlsx", excel_buf.getvalue())
    return buf.getvalue()


def _crear_zip_vacio() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("readme.txt", "no soy archivo bancario")
    return buf.getvalue()


def _crear_zip_con_ruta_insegura() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("__MACOSX/hidden.txt", "test")
        zf.writestr("estados/.DS_Store", "test")
    return buf.getvalue()


def _crear_zip_multiples_archivos() -> bytes:
    """Create ZIP with 2 Excel files for different empresas."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        df1 = pd.DataFrame([{
            "Fecha": "01/01/2024", "Concepto": "Deposito", "Referencia": "REF001",
            "Cargo": 0, "Abono": 1000.00, "Moneda": "MXN",
        }])
        excel1 = io.BytesIO()
        df1.to_excel(excel1, index=False)
        zf.writestr("CSC/BANX_CTA1.xlsx", excel1.getvalue())

        df2 = pd.DataFrame([{
            "Fecha": "02/01/2024", "Concepto": "Retiro", "Referencia": "REF002",
            "Cargo": 500.00, "Abono": 0, "Moneda": "USD",
        }])
        excel2 = io.BytesIO()
        df2.to_excel(excel2, index=False)
        zf.writestr("INTRA/BANX_CTA2.xlsx", excel2.getvalue())
    return buf.getvalue()


def _valid_cfdi_xml(uuid: str = "TEST-UUID-001", moneda: str = "MXN") -> bytes:
    return (
        '<cfdi:Comprobante xmlns:cfdi="http://www.sat.gob.mx/cfd/4" '
        'xmlns:tfd="http://www.sat.gob.mx/TimbreFiscalDigital" '
        f'Fecha="2026-06-01T12:00:00" SubTotal="1000.00" Total="1160.00" '
        f'Moneda="{moneda}" TipoCambio="1" TipoDeComprobante="I" MetodoPago="PUE" '
        'FormaPago="03">'
        '<cfdi:Emisor Rfc="AAA010101AAA" Nombre="EMISOR"/>'
        '<cfdi:Receptor Rfc="XAXX010101000" Nombre="RECEPTOR"/>'
        '<cfdi:Conceptos>'
        '<cfdi:Concepto>'
        '<cfdi:Impuestos>'
        '<cfdi:Traslados>'
        '<cfdi:Traslado Impuesto="002" TasaOCuota="0.160000" Importe="160.00"/>'
        '</cfdi:Traslados>'
        '</cfdi:Impuestos>'
        '</cfdi:Concepto>'
        '</cfdi:Conceptos>'
        '<cfdi:Complemento>'
        f'<tfd:TimbreFiscalDigital UUID="{uuid}"/>'
        '</cfdi:Complemento>'
        '</cfdi:Comprobante>'
    ).encode("utf-8")


# --- Tests: _es_ruta_segura ---

def test_ruta_segura_acepta_ruta_normal():
    from app import _es_ruta_segura
    assert _es_ruta_segura("CSC/BANX_Enero.xlsx") is True
    assert _es_ruta_segura("INTRA/BANX_CTA1.xlsx") is True


def test_ruta_segura_rechaza_macosx():
    from app import _es_ruta_segura
    assert _es_ruta_segura("__MACOSX/hidden.txt") is False


def test_ruta_segura_rechaza_ds_store():
    from app import _es_ruta_segura
    assert _es_ruta_segura("estados/.DS_Store") is False


def test_ruta_segura_rechaza_pycache():
    from app import _es_ruta_segura
    assert _es_ruta_segura("__pycache__/module.pyc") is False


def test_ruta_segura_rechaza_directorio_punto():
    from app import _es_ruta_segura
    assert _es_ruta_segura(".git/config") is False


def test_ruta_segura_rechaza_thumbs():
    from app import _es_ruta_segura
    assert _es_ruta_segura("Thumbs.db") is False


# --- Tests: _procesar_zip_bancario ---

def test_zip_bancario_procesa_archivo_excel():
    from app import _procesar_zip_bancario
    movimientos_data = [{
        "Fecha": "01/01/2024", "Concepto": "Deposito",
        "Referencia": "REF001", "Cargo": 0, "Abono": 1000.00, "Moneda": "MXN",
    }]
    zip_bytes = _crear_zip_bancario_excel(movimientos_data)
    movimientos, errores, control_df = _procesar_zip_bancario(zip_bytes)
    assert len(movimientos) >= 1
    assert control_df is not None
    assert len(control_df) == 1
    assert control_df.iloc[0]["ESTATUS"] == "OK"
    assert control_df.iloc[0]["EMPRESA"] == "estados"


def test_zip_bancario_sin_archivos_compatibles():
    from app import _procesar_zip_bancario
    zip_bytes = _crear_zip_vacio()
    movimientos, errores, control_df = _procesar_zip_bancario(zip_bytes)
    assert len(movimientos) == 0
    assert control_df is None
    assert any("No se encontraron archivos compatibles" in e for e in errores)


def test_zip_bancario_rechaza_rutas_inseguras():
    from app import _procesar_zip_bancario
    zip_bytes = _crear_zip_con_ruta_insegura()
    movimientos, errores, control_df = _procesar_zip_bancario(zip_bytes)
    assert any("rutas inseguras" in e for e in errores)


def test_zip_bancario_control_tabla_multiples_archivos():
    from app import _procesar_zip_bancario
    zip_bytes = _crear_zip_multiples_archivos()
    movimientos, errores, control_df = _procesar_zip_bancario(zip_bytes)
    assert control_df is not None
    assert len(control_df) == 2
    empresas = set(control_df["EMPRESA"].tolist())
    assert "CSC" in empresas
    assert "INTRA" in empresas


def test_zip_bancario_error_por_archivo_no_detiene():
    from app import _procesar_zip_bancario
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        df_ok = pd.DataFrame([{
            "Fecha": "01/01/2024", "Concepto": "OK",
            "Referencia": "R1", "Cargo": 0, "Abono": 100.00, "Moneda": "MXN",
        }])
        excel_ok = io.BytesIO()
        df_ok.to_excel(excel_ok, index=False)
        zf.writestr("CSC/ok.xlsx", excel_ok.getvalue())
        zf.writestr("CSC/rotto.xlsx", b"contenido invalido")

    zip_bytes = buf.getvalue()
    movimientos, errores, control_df = _procesar_zip_bancario(zip_bytes)
    assert control_df is not None
    assert len(control_df) == 2
    statuses = control_df["ESTATUS"].tolist()
    assert "OK" in statuses
    assert "ERROR" in statuses


# --- Tests: XML emitidos/recibidos split ---

def test_xml_emitidos_marca_origen_emitido():
    parser = XMLParser()
    xml_bytes = _valid_cfdi_xml("UUID-EMITIDO-001")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("emitido.xml", xml_bytes)
    resultado = parser.parsear_zip(buf.getvalue(), origen_xml="EMITIDO")
    assert resultado.exitosos_count == 1
    assert resultado.exitosos[0].origen_xml == "EMITIDO"


def test_xml_recibidos_marca_origen_recibido():
    parser = XMLParser()
    xml_bytes = _valid_cfdi_xml("UUID-RECIBIDO-001")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("recibido.xml", xml_bytes)
    resultado = parser.parsear_zip(buf.getvalue(), origen_xml="RECIBIDO")
    assert resultado.exitosos_count == 1
    assert resultado.exitosos[0].origen_xml == "RECIBIDO"


def test_xml_por_defecto_origen_vacio():
    parser = XMLParser()
    xml_bytes = _valid_cfdi_xml("UUID-DEFAULT-001")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("default.xml", xml_bytes)
    resultado = parser.parsear_zip(buf.getvalue())
    assert resultado.exitosos_count == 1
    assert resultado.exitosos[0].origen_xml == ""


def test_xml_parsear_individual_origen():
    parser = XMLParser()
    xml_bytes = _valid_cfdi_xml("UUID-IND-001")
    cfdi = parser.parsear_xml(xml_bytes, "test.xml", origen_xml="EMITIDO")
    assert cfdi is not None
    assert cfdi.origen_xml == "EMITIDO"


# --- Tests: Moneda preservation ---

def test_moneda_usd_se_preserva_en_cfdi():
    parser = XMLParser()
    xml_bytes = _valid_cfdi_xml("UUID-USDMX-001", moneda="USD")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("usd.xml", xml_bytes)
    resultado = parser.parsear_zip(buf.getvalue())
    assert resultado.exitosos[0].moneda == "USD"


def test_moneda_eur_se_preserva_en_cfdi():
    parser = XMLParser()
    xml_bytes = _valid_cfdi_xml("UUID-EURMX-001", moneda="EUR")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("eur.xml", xml_bytes)
    resultado = parser.parsear_zip(buf.getvalue())
    assert resultado.exitosos[0].moneda == "EUR"


def test_zip_mixto_monedas_se_preservan():
    parser = XMLParser()
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("mxn.xml", _valid_cfdi_xml("UUID-MXN-001", moneda="MXN"))
        zf.writestr("usd.xml", _valid_cfdi_xml("UUID-USD-001", moneda="USD"))
        zf.writestr("eur.xml", _valid_cfdi_xml("UUID-EUR-001", moneda="EUR"))
    resultado = parser.parsear_zip(buf.getvalue())
    assert resultado.exitosos_count == 3
    monedas = {cfdi.moneda for cfdi in resultado.exitosos}
    assert monedas == {"MXN", "USD", "EUR"}


# --- Tests: ConciliadorIngresos sin moneda_banco global ---

def test_conciliador_ingresos_sin_moneda_banco_param():
    from conciliacion.conciliador_ingresos import ConciliadorIngresos
    conc = ConciliadorIngresos(tolerancia=Decimal("1.00"), dias_tolerancia=5)
    assert hasattr(conc, "conciliar")
    sig = conc.conciliar.__code__.co_varnames[:conc.conciliar.__code__.co_argcount]
    assert "moneda_banco" not in sig


def test_conciliador_ingresos_filtra_por_moneda_del_registro():
    from conciliacion.conciliador_ingresos import ConciliadorIngresos
    conc = ConciliadorIngresos(tolerancia=Decimal("1.00"), dias_tolerancia=5)
    registro = CedulaIngresoRegistro(
        uuid="UUID-FILTER-001", rfc="AAA010101AAA", cliente="TEST",
        factura="F001", fecha=datetime(2024, 1, 15), total=Decimal("1160.00"),
        moneda="MXN", folio_transferencia="REF-FILTER",
        amount_mxn=Decimal("1160.00"), amount_usd=Decimal("0"),
        forma_pago="03", descripcion="test",
    )
    cfdi = CFDI(
        uuid="UUID-FILTER-001", rfc_emisor="AAA010101AAA",
        rfc_receptor="XAXX010101000", nombre_emisor="EMISOR",
        nombre_receptor="RECEPTOR", fecha=datetime(2024, 1, 15),
        subtotal=Decimal("1000.00"), iva=Decimal("160.00"),
        iva_retenido=Decimal("0"), isr_retenido=Decimal("0"),
        total=Decimal("1160.00"), moneda="MXN",
        tipo_cambio=Decimal("1"), tipo_cfdi="I", metodo_pago="PUE", forma_pago="03",
    )
    mov_mxn = MovimientoBancario(
        fecha=datetime(2024, 1, 15), concepto="Deposito MXN",
        cargo=Decimal("0"), abono=Decimal("1160.00"),
        referencia="REF-FILTER", banco="BNMX", cuenta="001",
        moneda="MXN", monto=Decimal("1160.00"),
    )
    mov_usd = MovimientoBancario(
        fecha=datetime(2024, 1, 15), concepto="Deposito USD",
        cargo=Decimal("0"), abono=Decimal("1160.00"),
        referencia="REF-FILTER", banco="BNMX", cuenta="001",
        moneda="USD", monto=Decimal("1160.00"),
    )
    resultado = conc.conciliar([registro], [cfdi], [mov_mxn, mov_usd])
    assert resultado.conciliados == 1
    assert resultado.registros[0].movimiento == mov_mxn


def test_conciliador_ingresos_no_concilia_diferente_moneda():
    from conciliacion.conciliador_ingresos import ConciliadorIngresos
    conc = ConciliadorIngresos(tolerancia=Decimal("1.00"), dias_tolerancia=5)
    registro = CedulaIngresoRegistro(
        uuid="UUID-USD-ONLY-001", rfc="AAA010101AAA", cliente="TEST",
        factura="F002", fecha=datetime(2024, 1, 15), total=Decimal("1160.00"),
        moneda="USD", folio_transferencia="REF-USD-ONLY",
        amount_mxn=Decimal("0"), amount_usd=Decimal("1160.00"),
        forma_pago="03", descripcion="test",
    )
    cfdi = CFDI(
        uuid="UUID-USD-ONLY-001", rfc_emisor="AAA010101AAA",
        rfc_receptor="XAXX010101000", nombre_emisor="EMISOR",
        nombre_receptor="RECEPTOR", fecha=datetime(2024, 1, 15),
        subtotal=Decimal("1000.00"), iva=Decimal("160.00"),
        iva_retenido=Decimal("0"), isr_retenido=Decimal("0"),
        total=Decimal("1160.00"), moneda="USD",
        tipo_cambio=Decimal("1"), tipo_cfdi="I", metodo_pago="PUE", forma_pago="03",
    )
    mov_mxn_only = MovimientoBancario(
        fecha=datetime(2024, 1, 15), concepto="Deposito MXN",
        cargo=Decimal("0"), abono=Decimal("1160.00"),
        referencia="REF-USD-ONLY", banco="BNMX", cuenta="001",
        moneda="MXN", monto=Decimal("1160.00"),
    )
    resultado = conc.conciliar([registro], [cfdi], [mov_mxn_only])
    assert resultado.conciliados == 0
    assert resultado.sin_banco == 1


# --- Tests: Error resilience in ZIP ---

def test_zip_xml_mixto_exitosos_y_fallos():
    parser = XMLParser()
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("valido1.xml", _valid_cfdi_xml("UUID-OK-001"))
        zf.writestr("invalido.xml", b"<root><broken")
        zf.writestr("valido2.xml", _valid_cfdi_xml("UUID-OK-002"))
    resultado = parser.parsear_zip(buf.getvalue())
    assert resultado.total == 3
    assert resultado.exitosos_count == 2
    assert resultado.fallos_count == 1
    uuids = {cfdi.uuid for cfdi in resultado.exitosos}
    assert "UUID-OK-001" in uuids
    assert "UUID-OK-002" in uuids


def test_zip_vacio_retorna_fallo():
    parser = XMLParser()
    resultado = parser.parsear_zip(b"")
    assert resultado.total == 0
    assert resultado.fallos_count == 1
    assert resultado.fallos[0]["archivo"] == "(ZIP)"


# --- Tests: Date parsing ---

def test_iso_date_2024_02_01_parses_correctly():
    from core.utils import to_datetime
    result = to_datetime("2024-02-01")
    assert result.year == 2024
    assert result.month == 2
    assert result.day == 1


def test_dd_mm_yyyy_parses_correctly():
    from core.utils import to_datetime
    result = to_datetime("01/02/2024")
    assert result.year == 2024
    assert result.month == 2
    assert result.day == 1


def test_iso_datetime_parses_correctly():
    from core.utils import to_datetime
    result = to_datetime("2024-02-01 14:30:00")
    assert result.year == 2024
    assert result.month == 2
    assert result.day == 1
    assert result.hour == 14
    assert result.minute == 30
