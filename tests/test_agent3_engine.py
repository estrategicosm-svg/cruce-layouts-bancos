"""Tests de invariantes I5-I10 del motor banco-first — sin tautologías.

Cada prueba demuestra el comportamiento del motor con datos sintéticos.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import pytest

from agent3.engine import (
    EngineConfig,
    EngineResult,
    _movimiento_id,
    _movimiento_id_hash,
    _fecha_valida,
    conciliar_banco_first,
)
from agent3.models import EstatusRegistro, TipoMatch
from core.models import CedulaIngresoRegistro, CedulaRegistro, MovimientoBancario


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _movimiento(
    cargo: float = 0, abono: float = 0, ref: str = "REF001",
    fecha: datetime = datetime(2024, 2, 15), banco: str = "BBVA",
    cuenta: str = "0123456789", moneda: str = "MXN", fila: int = 2,
) -> MovimientoBancario:
    m = MovimientoBancario(
        banco=banco, cuenta=cuenta, fecha=fecha, concepto="PAGO",
        cargo=Decimal(str(cargo)), abono=Decimal(str(abono)),
        moneda=moneda, referencia=ref,
    )
    m._fila_origen = fila
    return m


def _cedula_egreso(
    importe: float = 1000, uuid: str = "", cruce: str = "",
    fecha: datetime = datetime(2024, 2, 15), poliza: str = "P001",
    moneda: str = "MXN",
) -> CedulaRegistro:
    return CedulaRegistro(
        poliza=poliza, cliente="PROVEEDOR X", rfc="XAXX010101000",
        uuid=uuid, importe=Decimal(str(importe)),
        base_iva_16=Decimal(str(importe)), base_iva_8=Decimal("0"),
        base_iva_0=Decimal("0"), exentos=Decimal("0"),
        iva=Decimal(str(importe * 0.16)), retenciones=Decimal("0"),
        moneda=moneda, tipo_cambio=Decimal("1"),
        fecha_pago=fecha, banco="BBVA", cruce_bancario=cruce,
    )


def _cedula_ingreso(
    total: float = 5000, uuid: str = "", folio: str = "",
    fecha: datetime = datetime(2024, 2, 15),
) -> CedulaIngresoRegistro:
    return CedulaIngresoRegistro(
        uuid=uuid, cliente="CLIENTE Y", rfc="XAXX010101000",
        factura=uuid, fecha=fecha, total=Decimal(str(total)),
        moneda="MXN", amount_mxn=Decimal(str(total)),
        amount_usd=Decimal("0"), forma_pago="03",
        folio_transferencia=folio, descripcion="COBRO",
    )


# ---------------------------------------------------------------------------
# I5: Solo monto → PROPUESTA_REVISAR (nunca conciliado)
# ---------------------------------------------------------------------------
class TestI5PropuestaRevisar:
    def test_solo_monto_exacto_es_propuesta(self):
        """Sin cruce_bancario, sin UUID. Solo match por monto."""
        movs = [_movimiento(cargo=1000, abono=0, ref="REF_A", fila=2)]
        cedulas = [_cedula_egreso(importe=1000, uuid="", cruce="")]
        result = conciliar_banco_first(
            movimientos_bancarios=movs,
            cedulas_egresos=cedulas, cedulas_ingresos=[], cfdis=[],
        )
        rows = result.filas
        assert len(rows) == 1
        row = rows[0]
        assert row.TIPO_MATCH == TipoMatch.MONTO
        assert row.NIVEL_CONFIANZA == "BAJA"
        assert row.ESTATUS == EstatusRegistro.PROPUESTA_REVISAR
        assert row.MOVIMIENTO_ID == ""

    def test_solo_monto_dentro_tolerancia_es_propuesta(self):
        movs = [_movimiento(cargo=1000.50, abono=0, ref="REF_A", fila=2)]
        cedulas = [_cedula_egreso(importe=1000, uuid="", cruce="")]
        result = conciliar_banco_first(
            movimientos_bancarios=movs,
            cedulas_egresos=cedulas, cedulas_ingresos=[], cfdis=[],
            config=EngineConfig(tolerancia_monto=Decimal("1")),
        )
        rows = result.filas
        assert len(rows) == 1
        row = rows[0]
        assert row.TIPO_MATCH == TipoMatch.MONTO
        assert row.NIVEL_CONFIANZA == "BAJA"
        assert row.ESTATUS == EstatusRegistro.PROPUESTA_REVISAR


# ---------------------------------------------------------------------------
# I6: Multiples candidatos → AMBIGUO sin asignación
# ---------------------------------------------------------------------------
class TestI6AmbiguoSinAsignar:
    def test_dos_movimientos_mismo_monto_ambiguo(self):
        movs = [
            _movimiento(cargo=1000, abono=0, ref="REF_A", fila=2),
            _movimiento(cargo=1000, abono=0, ref="REF_B", fila=3),
        ]
        cedulas = [_cedula_egreso(importe=1000, uuid="", cruce="")]
        result = conciliar_banco_first(
            movimientos_bancarios=movs,
            cedulas_egresos=cedulas, cedulas_ingresos=[], cfdis=[],
        )
        rows = result.filas
        assert len(rows) == 1
        row = rows[0]
        assert row.ESTATUS == EstatusRegistro.AMBIGUO
        assert row.MOVIMIENTO_ID == ""

    def test_dos_grupos_competiten_un_movimiento(self):
        movs = [_movimiento(cargo=1000, abono=0, ref="REF_X", fila=2)]
        cedulas = [
            _cedula_egreso(importe=1000, uuid="", cruce="", poliza="P001"),
            _cedula_egreso(importe=1000, uuid="", cruce="", poliza="P002"),
        ]
        result = conciliar_banco_first(
            movimientos_bancarios=movs,
            cedulas_egresos=cedulas, cedulas_ingresos=[], cfdis=[],
        )
        rows = result.filas
        statuses = [r.ESTATUS for r in rows]
        conciliados = [s for s in statuses if s == EstatusRegistro.CONCILIADO]
        assert len(conciliados) <= 1
        assert EstatusRegistro.AMBIGUO in statuses or EstatusRegistro.SIN_CANDIDATO in statuses


# ---------------------------------------------------------------------------
# I7: Diferencia calculada por GRUPO_ID
# ---------------------------------------------------------------------------
class TestI7DiferenciaPorGrupo:
    def test_dentro_tolerancia_conciliado(self):
        movs = [_movimiento(cargo=1000.50, abono=0, ref="REF_X", fila=2)]
        cedulas = [_cedula_egreso(importe=1000, uuid="", cruce="REF_X")]
        result = conciliar_banco_first(
            movimientos_bancarios=movs,
            cedulas_egresos=cedulas, cedulas_ingresos=[], cfdis=[],
            config=EngineConfig(tolerancia_monto=Decimal("1")),
        )
        rows = result.filas
        assert len(rows) == 1
        row = rows[0]
        assert row.DIFERENCIA == Decimal("0.50")
        assert row.ESTATUS == EstatusRegistro.CONCILIADO

    def test_fuera_tolerancia_no_conciliado(self):
        movs = [_movimiento(cargo=1050, abono=0, ref="REF_X", fila=2)]
        cedulas = [_cedula_egreso(importe=1000, uuid="", cruce="REF_X")]
        result = conciliar_banco_first(
            movimientos_bancarios=movs,
            cedulas_egresos=cedulas, cedulas_ingresos=[], cfdis=[],
            config=EngineConfig(tolerancia_monto=Decimal("5")),
        )
        rows = result.filas
        assert len(rows) == 1
        row = rows[0]
        assert row.DIFERENCIA == Decimal("50")
        assert row.ESTATUS != EstatusRegistro.CONCILIADO


# ---------------------------------------------------------------------------
# I8: Totales con GRUPO_ID y MOVIMIENTO_ID únicos
# ---------------------------------------------------------------------------
class TestI8TotalesUnicos:
    def test_ids_unicos(self):
        movs = [
            _movimiento(cargo=1000, abono=0, ref="R1", fila=2),
            _movimiento(cargo=2000, abono=0, ref="R2", fila=3),
        ]
        cedulas = [
            _cedula_egreso(importe=1000, uuid="", cruce="R1", poliza="P001"),
            _cedula_egreso(importe=2000, uuid="", cruce="R2", poliza="P002"),
        ]
        result = conciliar_banco_first(
            movimientos_bancarios=movs,
            cedulas_egresos=cedulas, cedulas_ingresos=[], cfdis=[],
        )
        rows = result.filas
        grupo_ids = [r.GRUPO_ID for r in rows]
        mov_ids = [r.MOVIMIENTO_ID for r in rows if r.MOVIMIENTO_ID]
        assert len(grupo_ids) == len(set(grupo_ids))
        assert len(mov_ids) == len(set(mov_ids))


# ---------------------------------------------------------------------------
# I9: No fechas inválidas
# ---------------------------------------------------------------------------
class TestI9FechasValidas:
    def test_fechas_validas_iso(self):
        movs = [_movimiento(cargo=1000, abono=0, ref="R1", fila=2)]
        cedulas = [_cedula_egreso(importe=1000, uuid="", cruce="")]
        result = conciliar_banco_first(
            movimientos_bancarios=movs,
            cedulas_egresos=cedulas, cedulas_ingresos=[], cfdis=[],
        )
        for row in result.filas:
            if row.FECHA_BANCO:
                datetime.strptime(row.FECHA_BANCO, "%Y-%m-%d")
            if row.FECHA_LAYOUT:
                datetime.strptime(row.FECHA_LAYOUT, "%Y-%m-%d")

    def test_anio_fuera_rango(self):
        assert _fecha_valida(datetime(1999, 1, 1)) is False
        assert _fecha_valida(datetime(2101, 1, 1)) is False
        assert _fecha_valida(datetime(2024, 6, 15)) is True
        assert _fecha_valida(None) is False

    def test_movimiento_sin_fecha_no_concilia(self):
        mov = MovimientoBancario(
            banco="BBVA", cuenta="0123456789",
            fecha=datetime(1, 1, 1),
            concepto="PAGO", cargo=Decimal("1000"), abono=Decimal("0"),
            moneda="MXN", referencia="R1",
        )
        mov._fila_origen = 2
        cedulas = [_cedula_egreso(importe=1000, uuid="", cruce="R1")]
        result = conciliar_banco_first(
            movimientos_bancarios=[mov],
            cedulas_egresos=cedulas, cedulas_ingresos=[], cfdis=[],
        )
        rows = result.filas
        assert len(rows) == 1
        assert rows[0].ESTATUS == EstatusRegistro.SIN_CANDIDATO


# ---------------------------------------------------------------------------
# I10: No doble conteo
# ---------------------------------------------------------------------------
class TestI10NoDobleConteo:
    def test_grupo_con_10_facturas_sin_doble_conteo(self):
        """1 POLIZA, 10 UUID, 10 filas de $10,000, TOTAL_GRUPO = $100,000.
        1 movimiento bancario de $100,000.
        Solo monto → PROPUESTA_REVISAR. Una FILA por cada registro (10 total).
        TOTAL_GRUPO repetido en cada fila = $100,000 (invariante: grupo compartido).
        """
        movs = [_movimiento(cargo=100000, abono=0, ref="REF_BIG", fila=2)]
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
        rows = result.filas
        assert len(rows) == 10, f"1 registro = 1 fila, got {len(rows)}"
        grupo_ids = set(r.GRUPO_ID for r in rows)
        assert len(grupo_ids) == 1, "10 filas con misma POLIZA = 1 grupo"
        total_grupo = rows[0].TOTAL_GRUPO
        assert total_grupo == Decimal("100000"), f"total_grupo={total_grupo}"
        mov_ids = [r.MOVIMIENTO_ID for r in rows if r.MOVIMIENTO_ID]
        assert len(mov_ids) == 0, "solo monto = PROPUESTA_REVISAR = sin MOVIMIENTO_ID"
        for r in rows:
            assert r.ESTATUS == EstatusRegistro.PROPUESTA_REVISAR

    def test_10_facturas_conciliado_totales_no_multiplicados(self):
        """1 POLIZA, 10 filas de $10,000, TOTAL_GRUPO = $100,000.
        1 movimiento de $100,000 con referencia → CONCILIADO.
        Demuestra que TOTAL_LAYOUT_CONCILIADO = $100,000 (no $1,000,000).
        """
        movs = [_movimiento(cargo=100000, abono=0, ref="REF_STRONG", fila=2)]
        cedulas = [
            _cedula_egreso(importe=10000, uuid=f"UUID-{i:03d}",
                           cruce="REF_STRONG", poliza="P001")
            for i in range(10)
        ]
        result = conciliar_banco_first(
            movimientos_bancarios=movs,
            cedulas_egresos=cedulas, cedulas_ingresos=[], cfdis=[],
            config=EngineConfig(tolerancia_monto=Decimal("0.01")),
        )
        rows = result.filas
        assert len(rows) == 10
        unique_grupos = {}
        for r in rows:
            unique_grupos[r.GRUPO_ID] = r
        total_layout_conciliado = sum(
            r.TOTAL_GRUPO for r in unique_grupos.values()
            if r.ESTATUS == EstatusRegistro.CONCILIADO
        )
        mov_unicos = {}
        for r in rows:
            if r.MOVIMIENTO_ID and r.MOVIMIENTO_ID not in mov_unicos:
                mov_unicos[r.MOVIMIENTO_ID] = r
        total_banco_usado = sum(r.CARGO for r in mov_unicos.values())
        assert total_layout_conciliado == Decimal("100000"), \
            f"TOTAL_LAYOUT_CONCILIADO={total_layout_conciliado} (esperado 100000)"
        assert total_banco_usado == Decimal("100000"), \
            f"TOTAL_BANCO_USADO={total_banco_usado} (esperado 100000)"
        assert total_layout_conciliado == total_banco_usado

    def test_candidato_movimiento_id_en_propuesta(self):
        """PROPUESTA_REVISAR tiene CANDIDATO_MOVIMIENTO_ID lleno, MOVIMIENTO_ID vacio."""
        movs = [_movimiento(cargo=5000, abono=0, ref="REF_P", fila=2)]
        cedulas = [_cedula_egreso(importe=5000, cruce="", poliza="P1")]
        result = conciliar_banco_first(
            movimientos_bancarios=movs,
            cedulas_egresos=cedulas, cedulas_ingresos=[], cfdis=[],
        )
        for r in result.filas:
            if r.ESTATUS == EstatusRegistro.PROPUESTA_REVISAR:
                assert r.MOVIMIENTO_ID == ""
                assert r.CANDIDATO_MOVIMIENTO_ID != ""

    def test_ambiguo_sin_candidato_id(self):
        """AMBIGUO tiene ambos campos vacios."""
        movs = [
            _movimiento(cargo=5000, abono=0, ref="R1", fila=2),
            _movimiento(cargo=5000, abono=0, ref="R2", fila=3),
        ]
        cedulas = [_cedula_egreso(importe=5000, cruce="", poliza="P1")]
        result = conciliar_banco_first(
            movimientos_bancarios=movs,
            cedulas_egresos=cedulas, cedulas_ingresos=[], cfdis=[],
        )
        for r in result.filas:
            if r.ESTATUS == EstatusRegistro.AMBIGUO:
                assert r.MOVIMIENTO_ID == ""
                assert r.CANDIDATO_MOVIMIENTO_ID == ""


# ---------------------------------------------------------------------------
# MOVIMIENTO_ID determinístico
# ---------------------------------------------------------------------------
class TestMovimientoIdDeterministico:
    def test_mismo_movimiento_mismo_id(self):
        mov1 = _movimiento(cargo=1000, ref="R1", fila=2)
        mov2 = _movimiento(cargo=1000, ref="R1", fila=2)
        id1 = _movimiento_id(mov1, "banco.xlsx")
        id2 = _movimiento_id(mov2, "banco.xlsx")
        assert id1 == id2

    def test_misma_fecha_monto_distinta_fila_id_diferente(self):
        mov1 = _movimiento(cargo=1000, ref="R1", fila=2)
        mov2 = _movimiento(cargo=1000, ref="R1", fila=3)
        id1 = _movimiento_id(mov1, "banco.xlsx")
        id2 = _movimiento_id(mov2, "banco.xlsx")
        assert id1 != id2

    def test_misma_fila_distinto_archivo_id_diferente(self):
        mov1 = _movimiento(cargo=1000, ref="R1", fila=2)
        mov2 = _movimiento(cargo=1000, ref="R1", fila=2)
        id1 = _movimiento_id(mov1, "banco1.xlsx")
        id2 = _movimiento_id(mov2, "banco2.xlsx")
        assert id1 != id2

    def test_id_no_depende_de_id_objeto(self):
        mov1 = _movimiento(cargo=1000, ref="R1", fila=2)
        mov2 = _movimiento(cargo=1000, ref="R1", fila=2)
        id1 = _movimiento_id(mov1, "banco.xlsx")
        id2 = _movimiento_id(mov2, "banco.xlsx")
        assert id1 == id2
        assert id1 == _movimiento_id(mov1, "banco.xlsx")

    def test_hash_deterministico(self):
        mov1 = _movimiento(cargo=1000, ref="R1", fila=2)
        h1 = _movimiento_id_hash(mov1, "banco.xlsx")
        h2 = _movimiento_id_hash(mov1, "banco.xlsx")
        assert h1 == h2
        assert len(h1) == 16


# ---------------------------------------------------------------------------
# Archivo y fila obligatorios
# ---------------------------------------------------------------------------
class TestArchivoFilaObligatorios:
    def test_movimiento_real_tiene_fila_y_archivo(self):
        movs = [_movimiento(cargo=1000, abono=0, ref="R1", fila=5)]
        cedulas = [_cedula_egreso(importe=1000, uuid="", cruce="R1")]
        result = conciliar_banco_first(
            movimientos_bancarios=movs,
            cedulas_egresos=cedulas, cedulas_ingresos=[], cfdis=[],
        )
        rows = result.filas
        conciliados = [r for r in rows if r.ESTATUS == EstatusRegistro.CONCILIADO]
        for r in conciliados:
            assert r.ARCHIVO_BANCO, "ARCHIVO_BANCO no puede estar vacío"
            assert r.FILA_BANCO > 0, "FILA_BANCO debe ser > 0"
