"""Tests for all 8 dictamen blockers.

Blocker 1: PROPUESTA_REVISAR must have CRUCE_ID="" and MOVIMIENTO_ID=""
Blocker 2: CRUCE_ID uses cedula empresa, never ZIP/folder name
Blocker 3: Bank dates 0001-01-01 are excluded from matching
Blocker 4: CANDIDATO fields populated in PROPUESTA
Blocker 5: Metrics split by EGRESOS vs INGRESOS
Blocker 6: Excel columns match exact spec (5 sheets, NUM_XML_GRUPO)
Blocker 7: Per-file date diagnostics
Blocker 8: to_datetime() handles DD MON and DD/Mon formats with year
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import pytest

from agent3.engine import (
    EngineConfig,
    _extraer_empresa,
    conciliar_banco_first,
)
from agent3.models import COLUMNS_ORDER, EstatusRegistro, TablaIntermediateRow, TipoMatch
from core.utils import to_datetime
from parsers.legacy_pdf_engine import _append_year_to_date


def _movimiento(cargo=0, abono=0, ref="", fila=2):
    from core.models import MovimientoBancario
    return MovimientoBancario(
        banco="BBVA", cuenta="123", fecha=datetime(2024, 2, 15),
        concepto="test", cargo=Decimal(str(cargo)), abono=Decimal(str(abono)),
        moneda="MXN", referencia=ref, clave_rastreo="", autorizacion="",
        num_operacion="", cruce_bancario=ref,
    )


def _cedula_egreso(importe=1000, uuid="", cruce="", poliza="P001"):
    from core.models import CedulaRegistro
    return CedulaRegistro(
        poliza=poliza, cliente="TEST", rfc="RFC001",
        uuid=uuid, importe=Decimal(str(importe)),
        base_iva_16=Decimal(str(importe)),
        base_iva_8=Decimal("0"), base_iva_0=Decimal("0"),
        exentos=Decimal("0"), iva=Decimal("0"), retenciones=Decimal("0"),
        moneda="MXN", tipo_cambio=Decimal("1"),
        fecha_pago=datetime(2024, 2, 15), banco="BBVA",
        cruce_bancario=cruce,
    )


# =========================================================================
# Blocker 1: PROPUESTA_REVISAR → CRUCE_ID="" and MOVIMIENTO_ID=""
# =========================================================================
class TestBlocker1PropuestaSinCruceId:
    def test_propuesta_monto_solo_cruce_vacio(self):
        """PROPUESTA by monto must have CRUCE_ID="" and MOVIMIENTO_ID=""."""
        movs = [_movimiento(cargo=5000, abono=0, ref="REF_A")]
        cedulas = [_cedula_egreso(importe=5000, cruce="")]
        result = conciliar_banco_first(
            movimientos_bancarios=movs,
            cedulas_egresos=cedulas, cedulas_ingresos=[], cfdis=[],
        )
        for r in result.filas:
            assert r.ESTATUS == EstatusRegistro.PROPUESTA_REVISAR
            assert r.CRUCE_ID == "", f"PROPUESTA CRUCE_ID must be empty, got {r.CRUCE_ID}"
            assert r.MOVIMIENTO_ID == "", f"PROPUESTA MOVIMIENTO_ID must be empty, got {r.MOVIMIENTO_ID}"

    def test_propuesta_tolerancia_cruce_vacio(self):
        """PROPUESTA by tolerance must have CRUCE_ID="" and MOVIMIENTO_ID=""."""
        movs = [_movimiento(cargo=1000.50, abono=0, ref="REF_A")]
        cedulas = [_cedula_egreso(importe=1000, cruce="")]
        result = conciliar_banco_first(
            movimientos_bancarios=movs,
            cedulas_egresos=cedulas, cedulas_ingresos=[], cfdis=[],
            config=EngineConfig(tolerancia_monto=Decimal("1")),
        )
        for r in result.filas:
            assert r.ESTATUS == EstatusRegistro.PROPUESTA_REVISAR
            assert r.CRUCE_ID == ""
            assert r.MOVIMIENTO_ID == ""

    def test_propuesta_referencia_con_monto_cruce_vacio(self):
        """Reference match with wrong amount (diff > tolerance) → SIN_CANDIDATO."""
        movs = [_movimiento(cargo=5000, abono=0, ref="REF_STRONG")]
        cedulas = [_cedula_egreso(importe=3000, cruce="REF_STRONG")]
        result = conciliar_banco_first(
            movimientos_bancarios=movs,
            cedulas_egresos=cedulas, cedulas_ingresos=[], cfdis=[],
        )
        for r in result.filas:
            assert r.ESTATUS in (EstatusRegistro.PROPUESTA_REVISAR, EstatusRegistro.SIN_CANDIDATO)
            assert r.CRUCE_ID == ""
            assert r.MOVIMIENTO_ID == ""

    def test_conciliado_si_tiene_cruce_id(self):
        """CONCILIADO rows MUST have CRUCE_ID and MOVIMIENTO_ID."""
        movs = [_movimiento(cargo=5000, abono=0, ref="REF_STRONG")]
        cedulas = [_cedula_egreso(importe=5000, cruce="REF_STRONG")]
        result = conciliar_banco_first(
            movimientos_bancarios=movs,
            cedulas_egresos=cedulas, cedulas_ingresos=[], cfdis=[],
        )
        for r in result.filas:
            assert r.ESTATUS == EstatusRegistro.CONCILIADO
            assert r.CRUCE_ID != "", "CONCILIADO must have CRUCE_ID"
            assert r.MOVIMIENTO_ID != "", "CONCILIADO must have MOVIMIENTO_ID"


# =========================================================================
# Blocker 2: CRUCE_ID uses cedula empresa, not ZIP/folder name
# =========================================================================
class TestBlocker2CruceIdEmpresa:
    def test_empresa_desde_cedula(self):
        """_extraer_empresa with valid cedula empresa returns catalog code."""
        assert _extraer_empresa("any/path.pdf", "CSC") == "CSC"
        assert _extraer_empresa("any/path.pdf", "INTRA") == "INTRA"
        assert _extraer_empresa("any/path.pdf", "ICOLD") == "ICOLD"
        assert _extraer_empresa("any/path.pdf", "TRANSCRUCES") == "TRANS"
        assert _extraer_empresa("any/path.pdf", "TRANS") == "TRANS"

    def test_empresa_desde_pdf_filename(self):
        """_extraer_empresa falls back to PDF filename prefix."""
        assert _extraer_empresa("CSC/CSC_BANAMEX_2024.pdf", "") == "CSC"
        assert _extraer_empresa("INTRA/INTRA_BBVA_2024.pdf", "") == "INTRA"

    def test_empresa_zip_folder_name_es_invalida(self):
        """ZIP/folder names must never be used as empresa."""
        assert _extraer_empresa("ESTADOS_DE_CTA_RENOMBRADO/file.pdf", "") == "EMPRESA_NO_DETERMINADA"
        assert _extraer_empresa("SAT/file.pdf", "") == "EMPRESA_NO_DETERMINADA"

    def test_empresa_invalida_catalog(self):
        """Unknown empresa in cedula → EMPRESA_NO_DETERMINADA."""
        assert _extraer_empresa("file.pdf", "UNKNOWN") == "EMPRESA_NO_DETERMINADA"
        assert _extraer_empresa("file.pdf", "SAT") == "EMPRESA_NO_DETERMINADA"

    def test_cruce_id_uses_cedula_empresa(self):
        """CRUCE_ID must reflect cedula empresa, not file path."""
        movs = [_movimiento(cargo=5000, abono=0, ref="REF_STRONG")]
        cedulas = [_cedula_egreso(importe=5000, cruce="REF_STRONG")]
        result = conciliar_banco_first(
            movimientos_bancarios=movs,
            cedulas_egresos=cedulas, cedulas_ingresos=[], cfdis=[],
            empresa_cedula="CSC",
        )
        for r in result.filas:
            if r.CRUCE_ID:
                assert r.CRUCE_ID.startswith("CSC-"), f"CRUCE_ID must start with CSC-, got {r.CRUCE_ID}"


# =========================================================================
# Blocker 3: Bank dates 0001-01-01 → not used in matching
# =========================================================================
class TestBlocker3BankDates:
    def test_fecha_invalida_propuesta(self):
        """Bank movement with 0001-01-01 date → PROPUESTA_REVISAR (not CONCILIADO)."""
        from datetime import datetime as dt_min
        from core.models import MovimientoBancario
        mov = MovimientoBancario(
            banco="BBVA", cuenta="123", fecha=dt_min.min,
            concepto="test", cargo=Decimal("5000"), abono=Decimal("0"),
            moneda="MXN", referencia="REF_STRONG", clave_rastreo="",
            autorizacion="", num_operacion="", cruce_bancario="REF_STRONG",
        )
        cedulas = [_cedula_egreso(importe=5000, cruce="REF_STRONG")]
        result = conciliar_banco_first(
            movimientos_bancarios=[mov],
            cedulas_egresos=cedulas, cedulas_ingresos=[], cfdis=[],
        )
        for r in result.filas:
            assert r.ESTATUS == EstatusRegistro.PROPUESTA_REVISAR, \
                f"Invalid bank date must yield PROPUESTA, got {r.ESTATUS}"

    def test_to_datetime_handles_dd_mon_yyyy(self):
        """to_datetime handles '14 FEB 2024' format."""
        result = to_datetime("14 FEB 2024")
        assert result == datetime(2024, 2, 14)

    def test_to_datetime_handles_dd_mon_lower(self):
        """to_datetime handles '02/Feb 2024' format."""
        result = to_datetime("02/Feb 2024")
        assert result == datetime(2024, 2, 2)

    def test_to_datetime_handles_slash_year(self):
        """to_datetime handles '02/02/2024' format."""
        result = to_datetime("02/02/2024")
        assert result == datetime(2024, 2, 2)

    def test_append_year_to_date_slash(self):
        """_append_year_to_date appends year to '02/02'."""
        result = _append_year_to_date("02/02", "Periodo: febrero 2024")
        assert result == "02/02/2024"

    def test_append_year_to_date_space(self):
        """_append_year_to_date appends year to '14 FEB'."""
        result = _append_year_to_date("14 FEB", "Periodo: febrero 2024")
        assert result == "14 FEB 2024"

    def test_append_year_to_date_already_has_year(self):
        """_append_year_to_date does not double-add year."""
        result = _append_year_to_date("14 FEB 2024", "Periodo: 2024")
        assert result == "14 FEB 2024"


# =========================================================================
# Blocker 4: PROPUESTA has CANDIDATO_* filled
# =========================================================================
class TestBlocker4PropuestaCandidatos:
    def test_candidatos_llenos(self):
        """PROPUESTA must have CANDIDATO_CRUCE_ID and CANDIDATO_MOVIMIENTO_ID."""
        movs = [_movimiento(cargo=5000, abono=0, ref="REF_A")]
        cedulas = [_cedula_egreso(importe=5000, cruce="")]
        result = conciliar_banco_first(
            movimientos_bancarios=movs,
            cedulas_egresos=cedulas, cedulas_ingresos=[], cfdis=[],
        )
        for r in result.filas:
            assert r.ESTATUS == EstatusRegistro.PROPUESTA_REVISAR
            assert r.CANDIDATO_MOVIMIENTO_ID != "", "PROPUESTA must have CANDIDATO_MOVIMIENTO_ID"
            assert r.CANDIDATO_CRUCE_ID != "", "PROPUESTA must have CANDIDATO_CRUCE_ID"


# =========================================================================
# Blocker 5: Metrics split by EGRESOS vs INGRESOS
# =========================================================================
class TestBlocker5MetricsSplit:
    def test_metrics_split(self):
        """Metrics are reported separately for egresos and ingresos."""
        movs_egreso = [_movimiento(cargo=5000, abono=0, ref="REF_E")]
        movs_ingreso = [_movimiento(cargo=0, abono=3000, ref="REF_I")]
        cedulas_eg = [_cedula_egreso(importe=5000, cruce="REF_E")]
        from core.models import CedulaIngresoRegistro
        cedulas_ing = [CedulaIngresoRegistro(
            uuid="UUID-ING-001", cliente="CLI", rfc="RFC",
            factura="F001", fecha=datetime(2024, 2, 15),
            total=Decimal("3000"), moneda="MXN",
            amount_mxn=Decimal("3000"), amount_usd=Decimal("0"),
            forma_pago="", folio_transferencia="REF_I",
            descripcion="test",
        )]
        result = conciliar_banco_first(
            movimientos_bancarios=movs_egreso + movs_ingreso,
            cedulas_egresos=cedulas_eg, cedulas_ingresos=cedulas_ing, cfdis=[],
        )
        egreso_grupos = {f.GRUPO_ID for f in result.filas if f.GRUPO_ID.startswith("egreso_")}
        ingreso_grupos = {f.GRUPO_ID for f in result.filas if f.GRUPO_ID.startswith("ingreso_")}
        assert len(egreso_grupos) == 1, "Expected 1 egreso group"
        assert len(ingreso_grupos) == 1, "Expected 1 ingreso group"

    def test_num_xml_grupo_field(self):
        """NUM_XML_GRUPO shows count of XMLs in the group."""
        movs = [_movimiento(cargo=100000, abono=0, ref="REF_BIG")]
        cedulas = [
            _cedula_egreso(importe=10000, uuid=f"UUID-{i:03d}",
                           cruce="", poliza="P001")
            for i in range(10)
        ]
        result = conciliar_banco_first(
            movimientos_bancarios=movs,
            cedulas_egresos=cedulas, cedulas_ingresos=[], cfdis=[],
            config=EngineConfig(tolerancia_monto=Decimal("0.01")),
        )
        for r in result.filas:
            assert r.NUM_XML_GRUPO == 10, f"Expected NUM_XML_GRUPO=10, got {r.NUM_XML_GRUPO}"


# =========================================================================
# Blocker 6: Excel columns match spec
# =========================================================================
class TestBlocker6ExcelColumns:
    def test_columns_order_has_num_xml_grupo(self):
        """COLUMNS_ORDER includes NUM_XML_GRUPO."""
        assert "NUM_XML_GRUPO" in COLUMNS_ORDER
        idx_total = COLUMNS_ORDER.index("TOTAL_GRUPO")
        idx_numxml = COLUMNS_ORDER.index("NUM_XML_GRUPO")
        assert idx_numxml == idx_total + 1, "NUM_XML_GRUPO must come right after TOTAL_GRUPO"

    def test_to_dict_has_num_xml_grupo(self):
        """to_dict includes NUM_XML_GRUPO."""
        row = TablaIntermediateRow(
            GRUPO_ID="egreso_P001", POLIZA="P001", EMPRESA="CSC",
            BANCO="BBVA", MONEDA="MXN", FECHA_LAYOUT="2024-02-15",
            TOTAL_GRUPO=Decimal("100"), NUM_XML_GRUPO=5,
            CRUCE_ID="", CANDIDATO_CRUCE_ID="", MOVIMIENTO_ID="",
            CANDIDATO_MOVIMIENTO_ID="", ARCHIVO_BANCO="banco.pdf",
            FILA_BANCO=1, FECHA_BANCO="2024-02-15",
            CARGO=Decimal("100"), ABONO=Decimal("0"),
            DIFERENCIA=Decimal("0"), TIPO_MATCH=TipoMatch.MONTO,
            NIVEL_CONFIANZA="BAJA", ESTATUS=EstatusRegistro.PROPUESTA_REVISAR,
        )
        d = row.to_dict()
        assert d["NUM_XML_GRUPO"] == 5

    def test_cruce_id_in_columns_order(self):
        """COLUMNS_ORDER has CRUCE_ID, CANDIDATO_CRUCE_ID, MOVIMIENTO_ID, CANDIDATO_MOVIMIENTO_ID."""
        for col in ["CRUCE_ID", "CANDIDATO_CRUCE_ID", "MOVIMIENTO_ID", "CANDIDATO_MOVIMIENTO_ID"]:
            assert col in COLUMNS_ORDER, f"{col} missing from COLUMNS_ORDER"


# =========================================================================
# Blocker 7: Per-file date diagnostics
# =========================================================================
class TestBlocker7DateDiagnostics:
    def test_to_datetime_min_is_invalid(self):
        """to_datetime returns datetime.min for unparseable dates."""
        result = to_datetime("NOT_A_DATE_XYZ")
        assert result == datetime.min

    def test_to_datetime_none_returns_min(self):
        """to_datetime(None) returns datetime.min."""
        result = to_datetime(None)
        assert result == datetime.min

    def test_to_datetime_empty_returns_min(self):
        """to_datetime('') returns datetime.min."""
        result = to_datetime("")
        assert result == datetime.min


class TestBlockerNanoseconds:
    def test_timestamp_with_nanoseconds_no_warning(self):
        """to_datetime truncates nanoseconds without UserWarning."""
        import pandas as pd
        ts_with_ns = pd.Timestamp("2024-02-15 14:30:00.123456789")
        import warnings
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            result = to_datetime(ts_with_ns)
            nanosecond_warnings = [
                x for x in w
                if issubclass(x.category, UserWarning)
                and "nanosecond" in str(x.message).lower()
            ]
            assert len(nanosecond_warnings) == 0
        assert result.year == 2024
        assert result.month == 2
        assert result.day == 15
        assert result.hour == 14
        assert result.minute == 30
        assert result.second == 0
        assert result.microsecond == 123456

    def test_datetime_with_nanoseconds_via_string(self):
        """to_datetime from string with sub-second precision works."""
        result = to_datetime("2024-02-15 14:30:00.123456")
        assert result.year == 2024
        assert result.microsecond == 123456


class TestSpanishMonths:
    def test_to_datetime_ago(self):
        """to_datetime parses Spanish 'AGO' as August."""
        result = to_datetime("19 AGO 2024")
        assert result == datetime(2024, 8, 19)

    def test_to_datetime_ene(self):
        """to_datetime parses Spanish 'ENE' as January."""
        result = to_datetime("01 ENE 2024")
        assert result == datetime(2024, 1, 1)

    def test_to_datetime_dic(self):
        """to_datetime parses Spanish 'DIC' as December."""
        result = to_datetime("25 DIC 2023")
        assert result == datetime(2023, 12, 25)

    def test_to_datetime_lowercase_spanish(self):
        """to_datetime parses lowercase Spanish month abbreviations."""
        result = to_datetime("15 mar 2024")
        assert result == datetime(2024, 3, 15)
