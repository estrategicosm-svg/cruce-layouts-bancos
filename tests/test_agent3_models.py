"""Tests de invariantes I1-I4 y matcher — sin tautologías.

Cada prueba demuestra el comportamiento del motor, no crea datos manualmente
y luego verifica lo mismo que creó.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import pytest

from agent3.matcher import (
    Naturaleza,
    es_abono,
    es_cargo,
    monto_neto,
    score_candidate,
    select_best_candidate,
    _es_elegible,
    _monto_para_comparar,
)
from agent3.models import TipoMatch
from core.models import MovimientoBancario


# ---------------------------------------------------------------------------
# I1: EGRESOS → solo CARGOS (cargo > 0, abono = 0)
# ---------------------------------------------------------------------------
class TestI1SoloCargosEgresos:
    """El motor solo debe aceptar movimientos con cargo para egresos."""

    def _mov(self, cargo: float, abono: float) -> MovimientoBancario:
        return MovimientoBancario(
            banco="BBVA", cuenta="0123456789",
            fecha=datetime(2024, 2, 15), concepto="PAGO",
            cargo=Decimal(str(cargo)), abono=Decimal(str(abono)),
            moneda="MXN", referencia="REF001",
        )

    def test_cargo_puro_es_elegible_egreso(self):
        m = self._mov(cargo=1000, abono=0)
        assert _es_elegible(m, Naturaleza.EGRESOS) is True

    def test_abono_puro_no_es_elegible_egreso(self):
        m = self._mov(cargo=0, abono=1000)
        assert _es_elegible(m, Naturaleza.EGRESOS) is False

    def test_cargo_y_abono_no_es_elegible_egreso(self):
        m = self._mov(cargo=500, abono=500)
        assert _es_elegible(m, Naturaleza.EGRESOS) is False

    def test_cero_no_es_elegible_egreso(self):
        m = self._mov(cargo=0, abono=0)
        assert _es_elegible(m, Naturaleza.EGRESOS) is False

    def test_monto_para_comparar_egreso_usa_cargo(self):
        m = self._mov(cargo=1000, abono=0)
        assert _monto_para_comparar(m, Naturaleza.EGRESOS) == Decimal("1000")

    def test_egreso_no_puede_usar_abono(self):
        m = self._mov(cargo=0, abono=1000)
        assert _monto_para_comparar(m, Naturaleza.EGRESOS) == Decimal("0")


# ---------------------------------------------------------------------------
# I2: INGRESOS → solo ABONOS (abono > 0, cargo = 0)
# ---------------------------------------------------------------------------
class TestI2SoloAbonosIngresos:
    """El motor solo debe aceptar movimientos con abono para ingresos."""

    def _mov(self, cargo: float, abono: float) -> MovimientoBancario:
        return MovimientoBancario(
            banco="BBVA", cuenta="0123456789",
            fecha=datetime(2024, 2, 15), concepto="COBRO",
            cargo=Decimal(str(cargo)), abono=Decimal(str(abono)),
            moneda="MXN", referencia="REF002",
        )

    def test_abono_puro_es_elegible_ingreso(self):
        m = self._mov(cargo=0, abono=5000)
        assert _es_elegible(m, Naturaleza.INGRESOS) is True

    def test_cargo_puro_no_es_elegible_ingreso(self):
        m = self._mov(cargo=5000, abono=0)
        assert _es_elegible(m, Naturaleza.INGRESOS) is False

    def test_cargo_y_abono_no_es_elegible_ingreso(self):
        m = self._mov(cargo=1000, abono=1000)
        assert _es_elegible(m, Naturaleza.INGRESOS) is False

    def test_monto_para_comparar_ingreso_usa_abono(self):
        m = self._mov(cargo=0, abono=5000)
        assert _monto_para_comparar(m, Naturaleza.INGRESOS) == Decimal("5000")

    def test_ingreso_no_puede_usar_cargo(self):
        m = self._mov(cargo=5000, abono=0)
        assert _monto_para_comparar(m, Naturaleza.INGRESOS) == Decimal("0")


# ---------------------------------------------------------------------------
# Matcher scoring — reglas corregidas
# ---------------------------------------------------------------------------
class TestMatcherScoring:
    """Verifica las reglas de scoring del matcher."""

    def test_referencia_monto_exacto_alta(self):
        conf, tipo = score_candidate(
            grupo_total=Decimal("1000"),
            tolerancia=Decimal("1"),
            tiene_referencia=True,
            monto_comparar=Decimal("1000"),
        )
        assert conf == "ALTA"
        assert tipo == TipoMatch.REFERENCIA

    def test_referencia_dentro_tolerancia_media(self):
        conf, tipo = score_candidate(
            grupo_total=Decimal("1000"),
            tolerancia=Decimal("5"),
            tiene_referencia=True,
            monto_comparar=Decimal("1002"),
        )
        assert conf == "MEDIA"
        assert tipo == TipoMatch.REFERENCIA

    def test_monto_exacto_sin_ref_baja(self):
        """Solo monto exacto sin referencia → BAJA / PROPUESTA_REVISAR."""
        conf, tipo = score_candidate(
            grupo_total=Decimal("1000"),
            tolerancia=Decimal("1"),
            tiene_referencia=False,
            monto_comparar=Decimal("1000"),
        )
        assert conf == "BAJA"
        assert tipo == TipoMatch.MONTO

    def test_monto_dentro_tolerancia_sin_ref_baja(self):
        conf, tipo = score_candidate(
            grupo_total=Decimal("1000"),
            tolerancia=Decimal("5"),
            tiene_referencia=False,
            monto_comparar=Decimal("1002"),
        )
        assert conf == "BAJA"
        assert tipo == TipoMatch.MONTO

    def test_fuera_tolerancia_ninguno(self):
        conf, tipo = score_candidate(
            grupo_total=Decimal("1000"),
            tolerancia=Decimal("1"),
            tiene_referencia=False,
            monto_comparar=Decimal("2000"),
        )
        assert conf == "NINGUNO"
        assert tipo == TipoMatch.NINGUNO


# ---------------------------------------------------------------------------
# select_best_candidate con naturaleza
# ---------------------------------------------------------------------------
class TestSelectBestCandidate:
    def _candidate(self, cargo: float, abono: float, ref: str = "REF",
                   tipo: TipoMatch = TipoMatch.REFERENCIA) -> object:
        from agent3.matcher import MatchCandidate
        monto = Decimal(str(cargo)) if cargo > 0 else Decimal(str(abono))
        return MatchCandidate(
            movimiento_id="ID", archivo_banco="banco.xlsx",
            fila_banco=2, fecha_banco="2024-02-15",
            cargo=Decimal(str(cargo)), abono=Decimal(str(abono)),
            monto_comparar=monto, diferencia=Decimal("0"),
            tipo_match=tipo, confianza="ALTA",
        )

    def test_egreso_compara_contra_cargo(self):
        c1 = self._candidate(cargo=1000, abono=0)
        result = select_best_candidate(
            [c1], Decimal("1000"), Decimal("1"),
            naturaleza=Naturaleza.EGRESOS,
        )
        assert result is c1

    def test_ingreso_compara_contra_abono(self):
        c1 = self._candidate(cargo=0, abono=5000)
        result = select_best_candidate(
            [c1], Decimal("5000"), Decimal("1"),
            naturaleza=Naturaleza.INGRESOS,
        )
        assert result is c1

    def test_egreso_rechaza_abono(self):
        c1 = self._candidate(cargo=0, abono=1000)
        result = select_best_candidate(
            [c1], Decimal("1000"), Decimal("1"),
            naturaleza=Naturaleza.EGRESOS,
        )
        assert result is None

    def test_ingreso_rechaza_cargo(self):
        c1 = self._candidate(cargo=1000, abono=0)
        result = select_best_candidate(
            [c1], Decimal("1000"), Decimal("1"),
            naturaleza=Naturaleza.INGRESOS,
        )
        assert result is None

    def test_movimiento_con_cargo_y_abono_no_elegible(self):
        c1 = self._candidate(cargo=500, abono=500)
        result = select_best_candidate(
            [c1], Decimal("500"), Decimal("1"),
            naturaleza=Naturaleza.EGRESOS,
        )
        assert result is None
