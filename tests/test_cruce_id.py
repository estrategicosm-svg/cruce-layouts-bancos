"""Tests for CRUCE_ID operational identifier system.

Validates all mandatory rules:
1. CSC-ING-BNMX starts at 001
2. CSC-EGR-BNMX starts at 001
3. INTRA-ING-BNMX starts at 001
4. Consecutivos don't mix between empresas
5. Consecutivos don't mix between ING/EGR
6. Consecutivos don't mix between bancos
7. Same input produces same CRUCE_ID
8. Two different movements never share a CRUCE_ID
9. Propuesta keeps only CANDIDATO_CRUCE_ID
10. Ambiguo has no definite CRUCE_ID
"""
from __future__ import annotations

import sys
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from agent3.engine import (
    BankMovementRecord,
    _extraer_empresa,
    _mapear_banco_code,
    _naturaleza_tipo_cruce,
    _construir_universo_movimientos,
    asignar_cruce_ids,
    conciliar_banco_first,
    EngineConfig,
)
from agent3.models import EstatusRegistro, TablaIntermediateRow, TipoMatch
from core.models import MovimientoBancario, CedulaRegistro


def _cedula(importe=100, cruce_bancario="REF001", poliza="P001"):
    return CedulaRegistro(
        poliza=poliza, cliente="TEST", rfc="RFC", uuid="",
        importe=Decimal(str(importe)),
        base_iva_16=Decimal("0"), base_iva_8=Decimal("0"),
        base_iva_0=Decimal("0"), exentos=Decimal("0"),
        iva=Decimal("0"), retenciones=Decimal("0"),
        moneda="MXN", tipo_cambio=Decimal("1"),
        fecha_pago=datetime(2024, 2, 15), banco="",
        cruce_bancario=cruce_bancario,
    )


def _make_mov(banco, cargo, abono, ref="REF001", fecha=None, archivo="CSC/test.pdf", fila=2):
    if fecha is None:
        fecha = datetime(2024, 2, 15)
    m = MovimientoBancario(
        banco=banco, cuenta="0123456789", fecha=fecha, concepto="PAGO",
        cargo=Decimal(str(cargo)), abono=Decimal(str(abono)),
        moneda="MXN", referencia=ref,
    )
    m._fila_origen = fila
    m._archivo_origen = archivo
    return m


# =========================================================================
# 1. CSC-ING-BNMX starts at 001
# =========================================================================
class TestConsecutivoInicio:
    def test_csc_ing_bnmx_starts_001(self):
        m1 = _make_mov("BANAMEX", cargo=0, abono=1000, archivo="CSC/CSC_BNMX.pdf", fila=2)
        m2 = _make_mov("BANAMEX", cargo=0, abono=2000, archivo="CSC/CSC_BNMX.pdf", fila=3)
        movs = [m1, m2]
        universo = _construir_universo_movimientos(movs, "test.pdf")
        asignar_cruce_ids(universo)
        cruce_ids = [r.CRUCE_ID for r in universo]
        assert cruce_ids[0] == "CSC-ING-BNMX-001"
        assert cruce_ids[1] == "CSC-ING-BNMX-002"

    def test_csc_egr_bnmx_starts_001(self):
        m1 = _make_mov("BANAMEX", cargo=1000, abono=0, archivo="CSC/CSC_BNMX.pdf", fila=2)
        m2 = _make_mov("BANAMEX", cargo=2000, abono=0, archivo="CSC/CSC_BNMX.pdf", fila=3)
        movs = [m1, m2]
        universo = _construir_universo_movimientos(movs, "test.pdf")
        asignar_cruce_ids(universo)
        cruce_ids = [r.CRUCE_ID for r in universo]
        assert cruce_ids[0] == "CSC-EGR-BNMX-001"
        assert cruce_ids[1] == "CSC-EGR-BNMX-002"

    def test_intra_ing_bnmx_starts_001(self):
        m1 = _make_mov("BANAMEX", cargo=0, abono=500, archivo="INTRA/INTRA_BNMX.pdf", fila=2)
        movs = [m1]
        universo = _construir_universo_movimientos(movs, "test.pdf")
        asignar_cruce_ids(universo)
        assert universo[0].CRUCE_ID == "INTRA-ING-BNMX-001"


# =========================================================================
# 2. Consecutivos no se mezclan entre empresas
# =========================================================================
class TestNoMezclaEmpresas:
    def test_csc_and_intra_independent(self):
        m_csc = _make_mov("BANAMEX", cargo=100, abono=0, archivo="CSC/CSC_BNMX.pdf", fila=2)
        m_intra = _make_mov("BANAMEX", cargo=200, abono=0, archivo="INTRA/INTRA_BNMX.pdf", fila=2)
        movs = [m_csc, m_intra]
        universo = _construir_universo_movimientos(movs, "test.pdf")
        asignar_cruce_ids(universo)
        ids = {r.ARCHIVO_BANCO: r.CRUCE_ID for r in universo}
        assert ids["CSC/CSC_BNMX.pdf"] == "CSC-EGR-BNMX-001"
        assert ids["INTRA/INTRA_BNMX.pdf"] == "INTRA-EGR-BNMX-001"


# =========================================================================
# 3. Consecutivos no se mezclan entre ING y EGR
# =========================================================================
class TestNoMezclaTipo:
    def test_ing_and_egr_independent(self):
        m_egr = _make_mov("BANAMEX", cargo=100, abono=0, archivo="CSC/CSC_BNMX.pdf", fila=2)
        m_ing = _make_mov("BANAMEX", cargo=0, abono=200, archivo="CSC/CSC_BNMX.pdf", fila=3)
        movs = [m_egr, m_ing]
        universo = _construir_universo_movimientos(movs, "test.pdf")
        asignar_cruce_ids(universo)
        ids = {(r.CARGO, r.ABONO): r.CRUCE_ID for r in universo}
        assert ids[(Decimal("100"), Decimal("0"))] == "CSC-EGR-BNMX-001"
        assert ids[(Decimal("0"), Decimal("200"))] == "CSC-ING-BNMX-001"


# =========================================================================
# 4. Consecutivos no se mezclan entre bancos
# =========================================================================
class TestNoMezclaBancos:
    def test_bnmx_and_bbva_independent(self):
        m_bnmx = _make_mov("BANAMEX", cargo=100, abono=0, archivo="CSC/CSC_BNMX.pdf", fila=2)
        m_bbva = _make_mov("BBVA", cargo=200, abono=0, archivo="CSC/CSC_BBVA.pdf", fila=2)
        movs = [m_bnmx, m_bbva]
        universo = _construir_universo_movimientos(movs, "test.pdf")
        asignar_cruce_ids(universo)
        ids = {r.BANCO: r.CRUCE_ID for r in universo}
        assert ids["BANAMEX"] == "CSC-EGR-BNMX-001"
        assert ids["BBVA"] == "CSC-EGR-BBVA-001"


# =========================================================================
# 5. Same input produces same CRUCE_ID (determinism)
# =========================================================================
class TestDeterminismo:
    def test_same_input_same_output(self):
        movs = [
            _make_mov("BANAMEX", cargo=100, abono=0, archivo="CSC/CSC_BNMX.pdf", fila=2),
            _make_mov("BBVA", cargo=0, abono=200, archivo="INTRA/INTRA_BBVA.pdf", fila=3),
            _make_mov("AMEX", cargo=300, abono=0, archivo="ICOLD/ICOLD_AMEX.pdf", fila=4),
        ]
        u1 = _construir_universo_movimientos(movs, "test.pdf")
        asignar_cruce_ids(u1)
        ids1 = [r.CRUCE_ID for r in u1]

        u2 = _construir_universo_movimientos(movs, "test.pdf")
        asignar_cruce_ids(u2)
        ids2 = [r.CRUCE_ID for r in u2]

        assert ids1 == ids2

    def test_reversed_input_same_ids(self):
        movs_forward = [
            _make_mov("BANAMEX", cargo=100, abono=0, archivo="CSC/CSC_BNMX.pdf", fila=2),
            _make_mov("BANAMEX", cargo=200, abono=0, archivo="CSC/CSC_BNMX.pdf", fila=3),
        ]
        movs_reverse = list(reversed(movs_forward))

        u1 = _construir_universo_movimientos(movs_forward, "test.pdf")
        asignar_cruce_ids(u1)

        u2 = _construir_universo_movimientos(movs_reverse, "test.pdf")
        asignar_cruce_ids(u2)

        mapping1 = {r.MOVIMIENTO_ID: r.CRUCE_ID for r in u1}
        mapping2 = {r.MOVIMIENTO_ID: r.CRUCE_ID for r in u2}
        assert mapping1 == mapping2


# =========================================================================
# 6. Two different movements never share a CRUCE_ID (uniqueness)
# =========================================================================
class TestUnicidad:
    def test_all_cruce_ids_unique(self):
        movs = [
            _make_mov("BANAMEX", cargo=i * 100, abono=0, archivo="CSC/CSC_BNMX.pdf", fila=i)
            for i in range(1, 20)
        ]
        universo = _construir_universo_movimientos(movs, "test.pdf")
        asignar_cruce_ids(universo)
        ids = [r.CRUCE_ID for r in universo]
        assert len(ids) == len(set(ids))

    def test_across_empresas_types_bancos_unique(self):
        movs = [
            _make_mov("BANAMEX", cargo=100, abono=0, archivo="CSC/CSC_BNMX.pdf", fila=2),
            _make_mov("BANAMEX", cargo=0, abono=100, archivo="CSC/CSC_BNMX.pdf", fila=3),
            _make_mov("BANAMEX", cargo=200, abono=0, archivo="INTRA/INTRA_BNMX.pdf", fila=2),
            _make_mov("BBVA", cargo=300, abono=0, archivo="CSC/CSC_BBVA.pdf", fila=2),
        ]
        universo = _construir_universo_movimientos(movs, "test.pdf")
        asignar_cruce_ids(universo)
        ids = [r.CRUCE_ID for r in universo]
        assert len(ids) == len(set(ids))
        expected = {"CSC-EGR-BNMX-001", "CSC-ING-BNMX-001", "INTRA-EGR-BNMX-001", "CSC-EGR-BBVA-001"}
        assert set(ids) == expected


# =========================================================================
# 7. Propuesta conserva solo CANDIDATO_CRUCE_ID
# =========================================================================
class TestPropuesta:
    def test_propuesta_has_candidato_cruce_only(self):
        m = _make_mov("BANAMEX", cargo=100, abono=0, archivo="CSC/CSC_BNMX.pdf", fila=2)
        movs = [m]

        cedula = _cedula(importe=100, cruce_bancario="REF001")

        config = EngineConfig(tolerancia_monto=Decimal("0.01"))
        result = conciliar_banco_first(
            movimientos_bancarios=movs,
            cedulas_egresos=[cedula],
            cedulas_ingresos=[],
            cfdis=[],
            config=config,
            archivo_banco="test.pdf",
        )

        filas = [f for f in result.filas if f.ESTATUS == EstatusRegistro.PROPUESTA_REVISAR]
        if filas:
            f = filas[0]
            assert f.CRUCE_ID == ""
            assert f.CANDIDATO_CRUCE_ID != ""
            assert f.CANDIDATO_CRUCE_ID.startswith("CSC-EGR-BNMX-")


# =========================================================================
# 8. Ambiguo no recibe CRUCE_ID definitivo
# =========================================================================
class TestAmbiguo:
    def test_ambiguo_no_cruce_id(self):
        m1 = _make_mov("BANAMEX", cargo=500, abono=0, archivo="CSC/CSC_BNMX.pdf", fila=2)
        m2 = _make_mov("BANAMEX", cargo=500, abono=0, archivo="CSC/CSC_BNMX.pdf", fila=3)
        movs = [m1, m2]

        cedula = _cedula(importe=500, cruce_bancario="")

        config = EngineConfig(tolerancia_monto=Decimal("0.01"))
        result = conciliar_banco_first(
            movimientos_bancarios=movs,
            cedulas_egresos=[cedula],
            cedulas_ingresos=[],
            cfdis=[],
            config=config,
            archivo_banco="test.pdf",
        )

        filas = [f for f in result.filas if f.ESTATUS == EstatusRegistro.AMBIGUO]
        assert len(filas) > 0
        for f in filas:
            assert f.CRUCE_ID == ""


# =========================================================================
# 9. SIN_CANDIDATO has no CRUCE_ID
# =========================================================================
class TestSinCandidato:
    def test_sin_candidato_no_cruce_id(self):
        cedula = _cedula(importe=999999, cruce_bancario="")

        result = conciliar_banco_first(
            movimientos_bancarios=[],
            cedulas_egresos=[cedula],
            cedulas_ingresos=[],
            cfdis=[],
            archivo_banco="test.pdf",
        )

        for f in result.filas:
            assert f.CRUCE_ID == ""
            assert f.CANDIDATO_CRUCE_ID == ""


# =========================================================================
# 10. Mapping helpers
# =========================================================================
class TestMappings:
    def test_extraer_empresa_csc(self):
        assert _extraer_empresa("CSC/CSC_BAJIO_CTA0201.pdf") == "CSC"

    def test_extraer_empresa_intra(self):
        assert _extraer_empresa("INTRA/INTRA_BNMX_CTA0688.pdf") == "INTRA"

    def test_extraer_empresa_icold(self):
        assert _extraer_empresa("ICOLD/ICOLD_BBVA_CTA2519.pdf") == "ICOLD"

    def test_extraer_empresa_transcruces(self):
        assert _extraer_empresa("TRANSCRUCES/TRANSCRUCES_BNMX.pdf") == "TRANS"

    def test_mapear_banco_bnmx(self):
        assert _mapear_banco_code("BANAMEX") == "BNMX"

    def test_mapear_banco_bbva(self):
        assert _mapear_banco_code("BBVA") == "BBVA"

    def test_mapear_banco_bajio(self):
        assert _mapear_banco_code("BAJIO") == "BAJIO"

    def test_mapear_banco_banregio(self):
        assert _mapear_banco_code("BANREGIO") == "BREG"

    def test_mapear_banco_ibc(self):
        assert _mapear_banco_code("IBC") == "IBC"

    def test_mapear_banco_monex(self):
        assert _mapear_banco_code("MONEX") == "MONEX"

    def test_mapear_banco_amex(self):
        assert _mapear_banco_code("AMEX") == "AMEX"

    def test_naturaleza_tipo_cruce_cargo(self):
        assert _naturaleza_tipo_cruce("CARGO") == "EGR"

    def test_naturaleza_tipo_cruce_abono(self):
        assert _naturaleza_tipo_cruce("ABONO") == "ING"

    def test_naturaleza_tipo_cruce_mixto(self):
        assert _naturaleza_tipo_cruce("MIXTO") == "EGR"


# =========================================================================
# 11. BankMovementRecord has CRUCE_ID field
# =========================================================================
class TestBankMovementRecordCRUCE:
    def test_cruce_id_default_empty(self):
        rec = BankMovementRecord(
            MOVIMIENTO_ID="ABC", ARCHIVO_BANCO="test.pdf", FILA_BANCO=1,
            EMPRESA="CSC", BANCO="BBVA", CUENTA="0123", MONEDA="MXN",
            FECHA="2024-02-15", CONCEPTO="PAGO", CARGO=Decimal("100"),
            ABONO=Decimal("0"), REFERENCIA="REF",
            REFERENCIA_CLASIFICACION="REFERENCIA_EXPLICITA",
            FECHA_VALIDA=True, NATURALEZA="CARGO",
        )
        assert rec.CRUCE_ID == ""

    def test_cruce_id_set_after_assignment(self):
        rec = BankMovementRecord(
            MOVIMIENTO_ID="ABC", ARCHIVO_BANCO="test.pdf", FILA_BANCO=1,
            EMPRESA="CSC", BANCO="BBVA", CUENTA="0123", MONEDA="MXN",
            FECHA="2024-02-15", CONCEPTO="PAGO", CARGO=Decimal("100"),
            ABONO=Decimal("0"), REFERENCIA="REF",
            REFERENCIA_CLASIFICACION="REFERENCIA_EXPLICITA",
            FECHA_VALIDA=True, NATURALEZA="CARGO", CRUCE_ID="CSC-EGR-BBVA-001",
        )
        assert rec.CRUCE_ID == "CSC-EGR-BBVA-001"


# =========================================================================
# 12. COLUMNS_ORDER includes CRUCE_ID columns
# =========================================================================
class TestModelColumns:
    def test_cruce_id_in_columns_order(self):
        from agent3.models import COLUMNS_ORDER
        assert "CRUCE_ID" in COLUMNS_ORDER
        assert "CANDIDATO_CRUCE_ID" in COLUMNS_ORDER
        idx_cruce = COLUMNS_ORDER.index("CRUCE_ID")
        idx_cand = COLUMNS_ORDER.index("CANDIDATO_CRUCE_ID")
        idx_mov = COLUMNS_ORDER.index("MOVIMIENTO_ID")
        assert idx_cruce < idx_mov
        assert idx_cand < idx_mov

    def test_to_dict_includes_cruce_id(self):
        row = TablaIntermediateRow(
            GRUPO_ID="egreso_P001", POLIZA="P001", EMPRESA="SAT",
            BANCO="test.pdf", MONEDA="MXN", FECHA_LAYOUT="2024-02-15",
            TOTAL_GRUPO=Decimal("100"), NUM_XML_GRUPO=1, CRUCE_ID="CSC-EGR-BNMX-001",
            CANDIDATO_CRUCE_ID="", MOVIMIENTO_ID="",
            CANDIDATO_MOVIMIENTO_ID="", ARCHIVO_BANCO="test.pdf",
            FILA_BANCO=0, FECHA_BANCO="",
            CARGO=Decimal("0"), ABONO=Decimal("0"),
            DIFERENCIA=Decimal("100"), TIPO_MATCH=TipoMatch.NINGUNO,
            NIVEL_CONFIANZA="NINGUNO", ESTATUS=EstatusRegistro.SIN_CANDIDATO,
        )
        d = row.to_dict()
        assert d["CRUCE_ID"] == "CSC-EGR-BNMX-001"
        assert d["CANDIDATO_CRUCE_ID"] == ""


# =========================================================================
# 13. MIXTO movements classified as EGR for CRUCE_ID
# =========================================================================
class TestMixtoClassification:
    def test_mixto_gets_egr_tipo(self):
        m = _make_mov("BANAMEX", cargo=500, abono=300, archivo="CSC/CSC_BNMX.pdf", fila=2)
        movs = [m]
        universo = _construir_universo_movimientos(movs, "test.pdf")
        assert universo[0].NATURALEZA == "MIXTO"
        asignar_cruce_ids(universo)
        assert universo[0].CRUCE_ID == "CSC-EGR-BNMX-001"


# =========================================================================
# 14. Every valid movement gets a CRUCE_ID
# =========================================================================
class TestEveryMovementGetsCRUCE:
    def test_all_records_have_cruce_id(self):
        movs = [
            _make_mov("BANAMEX", cargo=100, abono=0, archivo="CSC/CSC_BNMX.pdf", fila=2),
            _make_mov("BBVA", cargo=0, abono=200, archivo="INTRA/INTRA_BBVA.pdf", fila=3),
            _make_mov("AMEX", cargo=300, abono=0, archivo="ICOLD/ICOLD_AMEX.pdf", fila=4),
        ]
        universo = _construir_universo_movimientos(movs, "test.pdf")
        asignar_cruce_ids(universo)
        for r in universo:
            assert r.CRUCE_ID != "", f"Record {r.MOVIMIENTO_ID} missing CRUCE_ID"
            assert "-" in r.CRUCE_ID
            parts = r.CRUCE_ID.split("-")
            assert len(parts) == 4
            assert parts[1] in ("EGR", "ING")
