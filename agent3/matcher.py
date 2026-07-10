"""Matcher con scoring de confianza para el motor banco-first.

Reglas de scoring:
  ALTA  = referencia fuerte + monto exacto + filtros compatibles
  MEDIA = referencia fuerte + diferencia dentro de tolerancia
  BAJA  = solo monto (exacto o dentro de tolerancia) → PROPUESTA_REVISAR
  NINGUNO = no cumple criterios

UUID no es referencia bancaria. Se usa solo para validar layout contra XML.
El UUID del CFDI NO aparece normalmente en el concepto bancario.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Optional

from agent3.models import TipoMatch


class Naturaleza(str, Enum):
    EGRESOS = "EGRESOS"
    INGRESOS = "INGRESOS"


@dataclass
class MatchCandidate:
    movimiento_id: str
    archivo_banco: str
    fila_banco: int
    fecha_banco: str
    cargo: Decimal
    abono: Decimal
    monto_comparar: Decimal
    diferencia: Decimal
    tipo_match: TipoMatch
    confianza: str


def _monto_para_comparar(mov, naturaleza: Naturaleza) -> Decimal:
    """EGRESOS → CARGO, INGRESOS → ABONO."""
    if naturaleza == Naturaleza.EGRESOS:
        return Decimal(str(mov.cargo))
    return Decimal(str(mov.abono))


def _es_elegible(mov, naturaleza: Naturaleza) -> bool:
    """Un movimiento es elegible solo si tiene el signo correcto.

    EGRESOS: cargo > 0, abono = 0.
    INGRESOS: abono > 0, cargo = 0.
    Movimiento con cargo y abono simultáneos no es elegible para ninguno.
    """
    cargo = Decimal(str(mov.cargo))
    abono = Decimal(str(mov.abono))
    if naturaleza == Naturaleza.EGRESOS:
        return cargo > Decimal("0") and abono == Decimal("0")
    return abono > Decimal("0") and cargo == Decimal("0")


def _candidate_elegible(c: MatchCandidate, naturaleza: Naturaleza) -> bool:
    """Elegibilidad de un MatchCandidate (no un MovimientoBancario)."""
    if naturaleza == Naturaleza.EGRESOS:
        return c.cargo > Decimal("0") and c.abono == Decimal("0")
    return c.abono > Decimal("0") and c.cargo == Decimal("0")


def score_candidate(
    grupo_total: Decimal,
    tolerancia: Decimal,
    tiene_referencia: bool = False,
    monto_comparar: Decimal = Decimal("0"),
) -> tuple[str, TipoMatch]:
    """Determina nivel de confianza y tipo de match.

    Reglas:
      referencia fuerte + monto exacto      → ALTA  / REFERENCIA
      referencia fuerte + dentro tolerancia  → MEDIA / REFERENCIA
      solo monto exacto                      → BAJA  / MONTO  → PROPUESTA_REVISAR
      solo monto dentro tolerancia           → BAJA  / MONTO  → PROPUESTA_REVISAR
      ninguno                                → NINGUNO
    """
    diff = abs(monto_comparar - grupo_total)
    monto_exacto = diff == Decimal("0")

    if tiene_referencia and monto_exacto:
        return ("ALTA", TipoMatch.REFERENCIA)
    if tiene_referencia and diff <= tolerancia:
        return ("MEDIA", TipoMatch.REFERENCIA)
    if monto_exacto:
        return ("BAJA", TipoMatch.MONTO)
    if diff <= tolerancia:
        return ("BAJA", TipoMatch.MONTO)
    return ("NINGUNO", TipoMatch.NINGUNO)


def select_best_candidate(
    candidates: list[MatchCandidate],
    grupo_total: Decimal,
    tolerancia: Decimal,
    naturaleza: Naturaleza = Naturaleza.EGRESOS,
) -> Optional[MatchCandidate]:
    """Selecciona el mejor candidato o None si hay ambigüedad.

    EGRESOS → compara contra CARGO.
    INGRESOS → compara contra ABONO.
    Filtra movimientos no elegibles (signo incorrecto).
    """
    if not candidates:
        return None

    elegibles = []
    for c in candidates:
        if not _candidate_elegible(c, naturaleza):
            continue
        diff = abs(c.monto_comparar - grupo_total)
        if diff <= tolerancia:
            elegibles.append(c)

    if len(elegibles) == 0:
        return None

    if len(elegibles) > 1:
        refs = [x for x in elegibles if x.tipo_match == TipoMatch.REFERENCIA]
        if len(refs) == 1:
            return refs[0]
        return None

    return elegibles[0]


def es_cargo(mov) -> bool:
    return Decimal(str(mov.cargo)) > Decimal("0") and Decimal(str(mov.abono)) == Decimal("0")


def es_abono(mov) -> bool:
    return Decimal(str(mov.abono)) > Decimal("0") and Decimal(str(mov.cargo)) == Decimal("0")


def monto_neto(mov) -> Decimal:
    return Decimal(str(mov.abono)) - Decimal(str(mov.cargo))
