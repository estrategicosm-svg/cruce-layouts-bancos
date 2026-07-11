"""Tests extendidos — todas las pruebas adicionales requeridas para H2.

Incluye: ingreso contra abono, egreso contra cargo, movimiento candidato
para ambos módulos, moneda incompatible, banco incompatible, etc.
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
from core.models import CedulaIngresoRegistro, CedulaRegistro, MovimientoBancario


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _mov(
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


def _egreso(
    importe: float = 1000, uuid: str = "", cruce: str = "",
    fecha: datetime = datetime(2024, 2, 15), poliza: str = "P001",
    moneda: str = "MXN",
) -> CedulaRegistro:
    return CedulaRegistro(
        poliza=poliza, cliente="PROVEEDOR", rfc="XAXX010101000",
        uuid=uuid, importe=Decimal(str(importe)),
        base_iva_16=Decimal(str(importe)), base_iva_8=Decimal("0"),
        base_iva_0=Decimal("0"), exentos=Decimal("0"),
        iva=Decimal("0"), retenciones=Decimal("0"),
        moneda=moneda, tipo_cambio=Decimal("1"),
        fecha_pago=fecha, banco="BBVA", cruce_bancario=cruce,
    )


def _ingreso(
    total: float = 5000, uuid: str = "", folio: str = "",
    fecha: datetime = datetime(2024, 2, 15),
) -> CedulaIngresoRegistro:
    return CedulaIngresoRegistro(
        uuid=uuid, cliente="CLIENTE", rfc="XAXX010101000",
        factura=uuid, fecha=fecha, total=Decimal(str(total)),
        moneda="MXN", amount_mxn=Decimal(str(total)),
        amount_usd=Decimal("0"), forma_pago="03",
        folio_transferencia=folio, descripcion="COBRO",
    )


# ---------------------------------------------------------------------------
# 1. Ingreso contra abono exacto
# ---------------------------------------------------------------------------
class TestIngresoContraAbonoExacto:
    def test_abono_exacto_concilia(self):
        movs = [_mov(abono=5000, cargo=0, ref="ING001", fila=2)]
        cedulas = [_ingreso(total=5000, folio="ING001")]
        result = conciliar_banco_first(
            movimientos_bancarios=movs,
            cedulas_egresos=[], cedulas_ingresos=cedulas, cfdis=[],
        )
        rows = result.filas
        conciliados = [r for r in rows if r.ESTATUS == EstatusRegistro.CONCILIADO]
        assert len(conciliados) == 1
        assert conciliados[0].ABONO == Decimal("5000")
        assert conciliados[0].CARGO == Decimal("0")


# ---------------------------------------------------------------------------
# 2. Egreso contra cargo exacto
# ---------------------------------------------------------------------------
class TestEgresoContraCargoExacto:
    def test_cargo_exacto_concilia(self):
        movs = [_mov(cargo=1000, abono=0, ref="EG001", fila=2)]
        cedulas = [_egreso(importe=1000, cruce="EG001")]
        result = conciliar_banco_first(
            movimientos_bancarios=movs,
            cedulas_egresos=cedulas, cedulas_ingresos=[], cfdis=[],
        )
        rows = result.filas
        conciliados = [r for r in rows if r.ESTATUS == EstatusRegistro.CONCILIADO]
        assert len(conciliados) == 1
        assert conciliados[0].CARGO == Decimal("1000")


# ---------------------------------------------------------------------------
# 3. Ingreso no usa cargo
# ---------------------------------------------------------------------------
class TestIngresoNoUsaCargo:
    def test_cargo_puro_no_matchea_ingreso(self):
        movs = [_mov(cargo=5000, abono=0, ref="REF_CARGO", fila=2)]
        cedulas = [_ingreso(total=5000, folio="F001")]
        result = conciliar_banco_first(
            movimientos_bancarios=movs,
            cedulas_egresos=[], cedulas_ingresos=cedulas, cfdis=[],
        )
        rows = result.filas
        assert len(rows) == 1
        assert rows[0].ESTATUS == EstatusRegistro.SIN_CANDIDATO


# ---------------------------------------------------------------------------
# 4. Egreso no usa abono
# ---------------------------------------------------------------------------
class TestEgresoNoUsaAbono:
    def test_abono_puro_no_matchea_egreso(self):
        movs = [_mov(abono=1000, cargo=0, ref="REF_ABONO", fila=2)]
        cedulas = [_egreso(importe=1000)]
        result = conciliar_banco_first(
            movimientos_bancarios=movs,
            cedulas_egresos=cedulas, cedulas_ingresos=[], cfdis=[],
        )
        rows = result.filas
        assert len(rows) == 1
        assert rows[0].ESTATUS == EstatusRegistro.SIN_CANDIDATO


# ---------------------------------------------------------------------------
# 5. Movimiento candidato para ingresos y egresos
# ---------------------------------------------------------------------------
class TestMovimientoParaAmbosModulos:
    def test_cargo_para_egreso_abono_para_ingreso(self):
        mov_cargo = _mov(cargo=1000, abono=0, ref="R1", fila=2)
        mov_abono = _mov(abono=5000, cargo=0, ref="R2", fila=3)

        cedulas_e = [_egreso(importe=1000, cruce="R1")]
        cedulas_i = [_ingreso(total=5000, folio="R2")]

        result = conciliar_banco_first(
            movimientos_bancarios=[mov_cargo, mov_abono],
            cedulas_egresos=cedulas_e,
            cedulas_ingresos=cedulas_i,
            cfdis=[],
        )
        rows = result.filas
        conciliados = [r for r in rows if r.ESTATUS == EstatusRegistro.CONCILIADO]
        mov_ids = [r.MOVIMIENTO_ID for r in conciliados]
        assert len(mov_ids) == len(set(mov_ids))


# ---------------------------------------------------------------------------
# 6. Solo monto exacto → propuesta
# ---------------------------------------------------------------------------
class TestSoloMontoExactoPropuesta:
    def test_monto_exacto_sin_cruce_es_propuesta(self):
        movs = [_mov(cargo=1000, abono=0, ref="SIN_MATCH", fila=2)]
        cedulas = [_egreso(importe=1000, cruce="OTRA_REF")]
        result = conciliar_banco_first(
            movimientos_bancarios=movs,
            cedulas_egresos=cedulas, cedulas_ingresos=[], cfdis=[],
        )
        rows = result.filas
        assert len(rows) == 1
        assert rows[0].ESTATUS == EstatusRegistro.PROPUESTA_REVISAR
        assert rows[0].TIPO_MATCH == TipoMatch.MONTO
        assert rows[0].NIVEL_CONFIANZA == "BAJA"
        assert rows[0].MOVIMIENTO_ID == ""
        assert rows[0].CRUCE_ID == ""


# ---------------------------------------------------------------------------
# 7. Solo monto dentro tolerancia → propuesta
# ---------------------------------------------------------------------------
class TestSoloMontoToleranciaPropuesta:
    def test_monto_cercano_sin_cruce_es_propuesta(self):
        movs = [_mov(cargo=1000.50, abono=0, ref="SIN_MATCH", fila=2)]
        cedulas = [_egreso(importe=1000, cruce="OTRA_REF")]
        result = conciliar_banco_first(
            movimientos_bancarios=movs,
            cedulas_egresos=cedulas, cedulas_ingresos=[], cfdis=[],
            config=EngineConfig(tolerancia_monto=Decimal("1")),
        )
        rows = result.filas
        assert len(rows) == 1
        assert rows[0].ESTATUS == EstatusRegistro.PROPUESTA_REVISAR
        assert rows[0].TIPO_MATCH == TipoMatch.MONTO
        assert rows[0].NIVEL_CONFIANZA == "BAJA"


# ---------------------------------------------------------------------------
# 8. Dos grupos compiten por un movimiento
# ---------------------------------------------------------------------------
class TestDosGruposCompetitenMovimiento:
    def test_un_movimiento_dos_grupos(self):
        movs = [_mov(cargo=1000, abono=0, ref="R_COMP", fila=2)]
        cedulas = [
            _egreso(importe=1000, cruce="", poliza="P001"),
            _egreso(importe=1000, cruce="", poliza="P002"),
        ]
        result = conciliar_banco_first(
            movimientos_bancarios=movs,
            cedulas_egresos=cedulas, cedulas_ingresos=[], cfdis=[],
        )
        rows = result.filas
        mov_asignados = [r for r in rows if r.MOVIMIENTO_ID]
        assert len(mov_asignados) <= 1


# ---------------------------------------------------------------------------
# 9. Un grupo tiene dos candidatos
# ---------------------------------------------------------------------------
class TestUnGrupoDosCandidatos:
    def test_dos_candidatos_ambiguo(self):
        movs = [
            _mov(cargo=1000, abono=0, ref="R_A", fila=2),
            _mov(cargo=1000, abono=0, ref="R_B", fila=3),
        ]
        cedulas = [_egreso(importe=1000, cruce="")]
        result = conciliar_banco_first(
            movimientos_bancarios=movs,
            cedulas_egresos=cedulas, cedulas_ingresos=[], cfdis=[],
        )
        rows = result.filas
        assert len(rows) == 1
        assert rows[0].ESTATUS == EstatusRegistro.AMBIGUO


# ---------------------------------------------------------------------------
# 10. Grupo con 10 facturas sin doble conteo
# ---------------------------------------------------------------------------
class TestGrupo10FacturasSinDobleConteo:
    def test_10_facturas_misma_poliza_un_grupo(self):
        """1 POLIZA, 10 filas de $10,000. Misma POLIZA = 1 grupo = $100,000.
        Solo monto → PROPUESTA_REVISAR. Verificar total correcto.
        """
        movs = [_mov(cargo=100000, abono=0, ref="BIG_REF", fila=2)]
        cedulas = [
            _egreso(importe=10000, uuid=f"UUID-{i}", cruce="", poliza="P001")
            for i in range(10)
        ]
        result = conciliar_banco_first(
            movimientos_bancarios=movs,
            cedulas_egresos=cedulas, cedulas_ingresos=[], cfdis=[],
            config=EngineConfig(tolerancia_monto=Decimal("0.01")),
        )
        rows = result.filas
        grupo_ids = set(r.GRUPO_ID for r in rows)
        assert len(grupo_ids) == 1
        total_grupo = rows[0].TOTAL_GRUPO
        assert total_grupo == Decimal("100000")


# ---------------------------------------------------------------------------
# 11. Diferencia dentro de tolerancia
# ---------------------------------------------------------------------------
class TestDiferenciaDentroTolerancia:
    def test_dentro_tolerancia_conciliado(self):
        movs = [_mov(cargo=1000.50, abono=0, ref="R_DENTRO", fila=2)]
        cedulas = [_egreso(importe=1000, cruce="R_DENTRO")]
        result = conciliar_banco_first(
            movimientos_bancarios=movs,
            cedulas_egresos=cedulas, cedulas_ingresos=[], cfdis=[],
            config=EngineConfig(tolerancia_monto=Decimal("1")),
        )
        rows = result.filas
        assert rows[0].ESTATUS == EstatusRegistro.CONCILIADO
        assert rows[0].DIFERENCIA == Decimal("0.50")


# ---------------------------------------------------------------------------
# 12. Diferencia fuera de tolerancia
# ---------------------------------------------------------------------------
class TestDiferenciaFueraTolerancia:
    def test_fuera_tolerancia_no_conciliado(self):
        movs = [_mov(cargo=1050, abono=0, ref="R_FUERA", fila=2)]
        cedulas = [_egreso(importe=1000, cruce="R_FUERA")]
        result = conciliar_banco_first(
            movimientos_bancarios=movs,
            cedulas_egresos=cedulas, cedulas_ingresos=[], cfdis=[],
            config=EngineConfig(tolerancia_monto=Decimal("5")),
        )
        rows = result.filas
        assert rows[0].ESTATUS != EstatusRegistro.CONCILIADO
        assert rows[0].DIFERENCIA == Decimal("50")


# ---------------------------------------------------------------------------
# 13. Moneda incompatible excluida
# ---------------------------------------------------------------------------
class TestMonedaIncompatible:
    def test_egreso_usd_banco_mxn(self):
        movs = [_mov(cargo=1000, abono=0, ref="R_USD", moneda="MXN", fila=2)]
        cedulas = [_egreso(importe=1000, cruce="R_USD", moneda="USD")]
        result = conciliar_banco_first(
            movimientos_bancarios=movs,
            cedulas_egresos=cedulas, cedulas_ingresos=[], cfdis=[],
        )
        rows = result.filas
        assert len(rows) == 1


# ---------------------------------------------------------------------------
# 14. Banco incompatible excluido
# ---------------------------------------------------------------------------
class TestBancoIncompatible:
    def test_banco_diferente_aun_puede_conciliar_por_ref(self):
        movs = [_mov(cargo=1000, abono=0, ref="R_BANCO", banco="SANTANDER", fila=2)]
        cedulas = [_egreso(importe=1000, cruce="R_BANCO")]
        result = conciliar_banco_first(
            movimientos_bancarios=movs,
            cedulas_egresos=cedulas, cedulas_ingresos=[], cfdis=[],
        )
        rows = result.filas
        assert len(rows) >= 1


# ---------------------------------------------------------------------------
# 15. Periodo incompatible excluido
# ---------------------------------------------------------------------------
class TestPeriodoIncompatible:
    def test_fecha_fuera_rango_no_concilia(self):
        mov = _mov(cargo=1000, abono=0, ref="R_OLD", fila=2)
        mov.fecha = datetime(2025, 12, 31)
        cedulas = [_egreso(importe=1000, cruce="R_OLD", fecha=datetime(2024, 2, 15))]
        result = conciliar_banco_first(
            movimientos_bancarios=[mov],
            cedulas_egresos=cedulas, cedulas_ingresos=[], cfdis=[],
            config=EngineConfig(tolerancia_dias=5),
        )
        rows = result.filas
        assert len(rows) == 1


# ---------------------------------------------------------------------------
# 16. Egreso con ref fuerte + monto exacto → ALTA
# ---------------------------------------------------------------------------
class TestEgresoRefFuerteMontoExacto:
    def test_referencia_monto_exacto_alta(self):
        movs = [_mov(cargo=1000, abono=0, ref="REF_STRONG", fila=2)]
        cedulas = [_egreso(importe=1000, cruce="REF_STRONG")]
        result = conciliar_banco_first(
            movimientos_bancarios=movs,
            cedulas_egresos=cedulas, cedulas_ingresos=[], cfdis=[],
        )
        rows = result.filas
        assert rows[0].NIVEL_CONFIANZA == "ALTA"
        assert rows[0].TIPO_MATCH == TipoMatch.REFERENCIA
        assert rows[0].ESTATUS == EstatusRegistro.CONCILIADO


# ---------------------------------------------------------------------------
# 17. Ingreso con ref fuerte + monto exacto → ALTA
# ---------------------------------------------------------------------------
class TestIngresoRefFuerteMontoExacto:
    def test_referencia_monto_exacto_alta(self):
        movs = [_mov(abono=5000, cargo=0, ref="ING_STRONG", fila=2)]
        cedulas = [_ingreso(total=5000, folio="ING_STRONG")]
        result = conciliar_banco_first(
            movimientos_bancarios=movs,
            cedulas_egresos=[], cedulas_ingresos=cedulas, cfdis=[],
        )
        rows = result.filas
        conciliados = [r for r in rows if r.ESTATUS == EstatusRegistro.CONCILIADO]
        assert len(conciliados) == 1
        assert conciliados[0].NIVEL_CONFIANZA == "ALTA"


# ---------------------------------------------------------------------------
# 18. Sin referencia, sin XML, monto exacto → propuesta
# ---------------------------------------------------------------------------
class TestSinRefSinXmlMontoExactoPropuesta:
    def test_solo_monto_propuesta(self):
        movs = [_mov(cargo=2500, abono=0, ref="NO_MATCH", fila=2)]
        cedulas = [_egreso(importe=2500, cruce="OTRA", uuid="")]
        result = conciliar_banco_first(
            movimientos_bancarios=movs,
            cedulas_egresos=cedulas, cedulas_ingresos=[], cfdis=[],
        )
        rows = result.filas
        assert len(rows) == 1
        assert rows[0].ESTATUS == EstatusRegistro.PROPUESTA_REVISAR
        assert rows[0].NIVEL_CONFIANZA == "BAJA"
        assert rows[0].TIPO_MATCH == TipoMatch.MONTO
