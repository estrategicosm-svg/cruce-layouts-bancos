"""Modelos para la tabla intermedia auditable del motor banco-first."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from typing import Optional


class TipoMatch(str, Enum):
    UUID = "UUID"
    REFERENCIA = "REFERENCIA"
    MONTO = "MONTO"
    NINGUNO = "NINGUNO"


class EstatusRegistro(str, Enum):
    CONCILIADO = "CONCILIADO"
    PROPUESTA_REVISAR = "PROPUESTA_REVISAR"
    AMBIGUO = "AMBIGUO"
    SIN_CANDIDATO = "SIN_CANDIDATO"
    DIFERENCIA = "DIFERENCIA"
    DUPLICADO = "DUPLICADO"


@dataclass
class TablaIntermediateRow:
    """Una fila de la tabla intermedia auditable.

    CRUCE_ID = identificador corto operativo (EMPRESA-TIPO-BANCO-CONSECUTIVO).
    MOVIMIENTO_ID = hash del movimiento asignado definitivamente (CONCILIADO/DIFERENCIA).
    CANDIDATO_CRUCE_ID = CRUCE_ID del candidato evaluado (PROPUESTA/AMBIGUO).
    CANDIDATO_MOVIMIENTO_ID = hash del candidato evaluado (PROPUESTA/AMBIGUO).
    """

    GRUPO_ID: str
    POLIZA: str
    EMPRESA: str
    BANCO: str
    MONEDA: str
    FECHA_LAYOUT: str
    TOTAL_GRUPO: Decimal
    NUM_XML_GRUPO: int
    CRUCE_ID: str
    CANDIDATO_CRUCE_ID: str
    MOVIMIENTO_ID: str
    CANDIDATO_MOVIMIENTO_ID: str
    ARCHIVO_BANCO: str
    FILA_BANCO: int
    FECHA_BANCO: str
    CARGO: Decimal
    ABONO: Decimal
    DIFERENCIA: Decimal
    TIPO_MATCH: TipoMatch
    NIVEL_CONFIANZA: str
    ESTATUS: EstatusRegistro

    def to_dict(self) -> dict:
        return {
            "GRUPO_ID": self.GRUPO_ID,
            "POLIZA": self.POLIZA,
            "EMPRESA": self.EMPRESA,
            "BANCO": self.BANCO,
            "MONEDA": self.MONEDA,
            "FECHA_LAYOUT": self.FECHA_LAYOUT,
            "TOTAL_GRUPO": str(self.TOTAL_GRUPO),
            "NUM_XML_GRUPO": self.NUM_XML_GRUPO,
            "CRUCE_ID": self.CRUCE_ID,
            "CANDIDATO_CRUCE_ID": self.CANDIDATO_CRUCE_ID,
            "MOVIMIENTO_ID": self.MOVIMIENTO_ID,
            "CANDIDATO_MOVIMIENTO_ID": self.CANDIDATO_MOVIMIENTO_ID,
            "ARCHIVO_BANCO": self.ARCHIVO_BANCO,
            "FILA_BANCO": self.FILA_BANCO,
            "FECHA_BANCO": self.FECHA_BANCO,
            "CARGO": str(self.CARGO),
            "ABONO": str(self.ABONO),
            "DIFERENCIA": str(self.DIFERENCIA),
            "TIPO_MATCH": self.TIPO_MATCH.value,
            "NIVEL_CONFIANZA": self.NIVEL_CONFIANZA,
            "ESTATUS": self.ESTATUS.value,
        }


COLUMNS_ORDER = [
    "GRUPO_ID",
    "POLIZA",
    "EMPRESA",
    "BANCO",
    "MONEDA",
    "FECHA_LAYOUT",
    "TOTAL_GRUPO",
    "NUM_XML_GRUPO",
    "CRUCE_ID",
    "CANDIDATO_CRUCE_ID",
    "MOVIMIENTO_ID",
    "CANDIDATO_MOVIMIENTO_ID",
    "ARCHIVO_BANCO",
    "FILA_BANCO",
    "FECHA_BANCO",
    "CARGO",
    "ABONO",
    "DIFERENCIA",
    "TIPO_MATCH",
    "NIVEL_CONFIANZA",
    "ESTATUS",
]
