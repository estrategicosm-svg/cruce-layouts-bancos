"""Test: agrupación por póliza y prueba de doble conteo.

Validates:
- 1 póliza with 10 XML = 1 group
- Total grupo = sum of all XMLs
- 1 bank movement matched against group total
- No double counting
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import pytest

from agent3.engine import (
    EngineConfig,
    _movimiento_id,
    conciliar_banco_first,
)
from agent3.models import EstatusRegistro, TipoMatch
from core.models import CFDI, CedulaRegistro, MovimientoBancario


POLIZA = "PBNK01/2024/TEST-DOBLETE"
BANCO_REF = "REF-DOBLETE-001"
NUM_XMLS = 10
IMPORTE_CADA_XML = Decimal("10000.00")
TOTAL_ESPERADO = IMPORTE_CADA_XML * NUM_XMLS  # 100,000


def _make_cfdi(idx: int) -> CFDI:
    return CFDI(
        uuid=f"UUID-DOBLETE-{idx:03d}",
        rfc_emisor="AAA010101AAA",
        rfc_receptor="XAXX010101000",
        nombre_emisor="Proveedor Test",
        nombre_receptor="Empresa Test",
        fecha=datetime(2024, 2, 15),
        subtotal=IMPORTE_CADA_XML,
        iva=Decimal("1600.00"),
        iva_retenido=Decimal("0"),
        isr_retenido=Decimal("0"),
        total=IMPORTE_CADA_XML + Decimal("1600.00"),
        moneda="MXN",
        tipo_cambio=Decimal("1"),
        tipo_cfdi="I",
        metodo_pago="PUE",
        forma_pago="03",
    )


def _make_cedula_registro(idx: int) -> CedulaRegistro:
    return CedulaRegistro(
        poliza=POLIZA,
        cliente="Proveedor Test",
        rfc="AAA010101AAA",
        uuid=f"UUID-DOBLETE-{idx:03d}",
        importe=IMPORTE_CADA_XML,
        base_iva_16=IMPORTE_CADA_XML,
        base_iva_8=Decimal("0"),
        base_iva_0=Decimal("0"),
        exentos=Decimal("0"),
        iva=Decimal("1600.00"),
        retenciones=Decimal("0"),
        moneda="MXN",
        tipo_cambio=Decimal("1"),
        fecha_pago=datetime(2024, 2, 20),
        banco="BANAMEX",
        cruce_bancario=BANCO_REF,
    )


def _make_movimiento() -> MovimientoBancario:
    return MovimientoBancario(
        banco="BANAMEX",
        cuenta="00123456",
        fecha=datetime(2024, 2, 20),
        concepto="PAGO PROVEEDOR",
        cargo=TOTAL_ESPERADO,
        abono=Decimal("0"),
        moneda="MXN",
        referencia=BANCO_REF,
    )


class TestDobleConteo:
    def test_un_poliza_10_xml_un_movimiento(self):
        """1 póliza, 10 XML de $10,000, 1 movimiento de $100,000."""
        cedulas = [_make_cedula_registro(i) for i in range(NUM_XMLS)]
        cfdis = [_make_cfdi(i) for i in range(NUM_XMLS)]
        movimientos = [_make_movimiento()]

        config = EngineConfig(tolerancia_monto=Decimal("1.00"), tolerancia_dias=5)
        result = conciliar_banco_first(
            movimientos_bancarios=movimientos,
            cedulas_egresos=cedulas,
            cedulas_ingresos=[],
            cfdis=cfdis,
            config=config,
            archivo_banco="BANAMEX/test_doble_conteo.pdf",
        )

        # All 10 rows share the same GRUPO_ID
        grupo_ids = {f.GRUPO_ID for f in result.filas}
        assert len(grupo_ids) == 1, f"Expected 1 group, got {len(grupo_ids)}: {grupo_ids}"

        grupo = list(grupo_ids)[0]
        filas_grupo = [f for f in result.filas if f.GRUPO_ID == grupo]
        assert len(filas_grupo) == NUM_XMLS, f"Expected {NUM_XMLS} rows, got {len(filas_grupo)}"

        # Total grupo = 10 × $10,000 = $100,000
        for f in filas_grupo:
            assert f.TOTAL_GRUPO == TOTAL_ESPERADO, f"TOTAL_GRUPO={f.TOTAL_GRUPO}, expected {TOTAL_ESPERADO}"

        # At least one row is CONCILIADO
        conciliados = [f for f in filas_grupo if f.ESTATUS == EstatusRegistro.CONCILIADO]
        assert len(conciliados) >= 1, "No CONCILIADO rows found"

        # The CONCILIADO row has DIFERENCIA = 0
        for f in conciliados:
            assert f.DIFERENCIA == Decimal("0"), f"DIFERENCIA={f.DIFERENCIA}, expected 0"

        # Only 1 MOVIMIENTO_ID used across the group
        mov_ids_concil = {f.MOVIMIENTO_ID for f in filas_grupo if f.MOVIMIENTO_ID}
        assert len(mov_ids_concil) == 1, f"Expected 1 MOVIMIENTO_ID, got {len(mov_ids_concil)}"

        # All 10 rows share the same GRUPO_ID
        assert result.grupos_conciliados >= 1

    def test_total_layout_conciliado(self):
        """Verify total layout conciliado = sum of conciliado rows."""
        cedulas = [_make_cedula_registro(i) for i in range(NUM_XMLS)]
        cfdis = [_make_cfdi(i) for i in range(NUM_XMLS)]
        movimientos = [_make_movimiento()]

        config = EngineConfig(tolerancia_monto=Decimal("1.00"), tolerancia_dias=5)
        result = conciliar_banco_first(
            movimientos_bancarios=movimientos,
            cedulas_egresos=cedulas,
            cedulas_ingresos=[],
            cfdis=cfdis,
            config=config,
            archivo_banco="BANAMEX/test_doble_conteo.pdf",
        )

        total_layout = sum(
            Decimal("10000.00") for f in result.filas
            if f.ESTATUS == EstatusRegistro.CONCILIADO
        )
        assert total_layout == TOTAL_ESPERADO, f"Total layout={total_layout}, expected {TOTAL_ESPERADO}"

    def test_sin_doble_conteo_movimiento(self):
        """Movement is not reused across groups."""
        cedulas = [_make_cedula_registro(i) for i in range(NUM_XMLS)]
        cfdis = [_make_cfdi(i) for i in range(NUM_XMLS)]
        movimientos = [_make_movimiento()]

        config = EngineConfig(tolerancia_monto=Decimal("1.00"), tolerancia_dias=5)
        result = conciliar_banco_first(
            movimientos_bancarios=movimientos,
            cedulas_egresos=cedulas,
            cedulas_ingresos=[],
            cfdis=cfdis,
            config=config,
            archivo_banco="BANAMEX/test_doble_conteo.pdf",
        )

        mov_ids_used = [f.MOVIMIENTO_ID for f in result.filas if f.MOVIMIENTO_ID]
        assert len(set(mov_ids_used)) == 1, "Movement should be used exactly once"

    def test_un_movimiento_por_grupo(self):
        """Only 1 bank movement per group."""
        cedulas = [_make_cedula_registro(i) for i in range(NUM_XMLS)]
        cfdis = [_make_cfdi(i) for i in range(NUM_XMLS)]
        movimientos = [_make_movimiento()]

        config = EngineConfig(tolerancia_monto=Decimal("1.00"), tolerancia_dias=5)
        result = conciliar_banco_first(
            movimientos_bancarios=movimientos,
            cedulas_egresos=cedulas,
            cedulas_ingresos=[],
            cfdis=cfdis,
            config=config,
            archivo_banco="BANAMEX/test_doble_conteo.pdf",
        )

        assert result.movimientos_asignados == 1
