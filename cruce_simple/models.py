"""Modelos simples para cruce de layouts contra estados de cuenta."""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum


class EstatusCruce(str, Enum):
    ENCONTRADO = "ENCONTRADO"
    MULTIPLES_CANDIDATOS = "MULTIPLES_CANDIDATOS"
    NO_ENCONTRADO = "NO_ENCONTRADO"
    MONEDAS_MIXTAS = "MONEDAS_MIXTAS"
    FUERA_DEL_CRUCE = "FUERA_DEL_CRUCE_AUTOMATICO"


EMPRESA_CODES: dict[str, str] = {
    "CSC": "CSC",
    "INTRA": "INTRA",
    "ICOLD": "ICOLD",
    "TRANS": "TRANS",
    "TRANSCRUCES": "TRANS",
}

BANCO_CODES: dict[str, str] = {
    "BANAMEX": "BNMX",
    "BBVA": "BBVA",
    "BAJIO": "BAJIO",
    "BANCO DEL BAJÍO": "BAJIO",
    "BANREGIO": "BREG",
    "IBC": "IBC",
    "MONEX": "MONEX",
    "AMEX": "AMEX",
    "AMERICAN EXPRESS": "AMEX",
}


def normalizar_empresa(nombre: str) -> str:
    upper = nombre.upper().strip()
    return EMPRESA_CODES.get(upper, upper)


def normalizar_banco(nombre: str) -> str:
    upper = nombre.upper().strip()
    return BANCO_CODES.get(upper, upper[:4])


@dataclass
class FilaLayout:
    empresa: str
    poliza: str
    uuid: str
    rfc: str
    nombre: str
    fecha: str
    moneda: str
    total_pesos: Decimal
    total_dls: Decimal
    banco: str
    archivo_origen: str = ""
    cruce_bancario: str = ""

    @property
    def importe_grupo(self) -> Decimal:
        if self.moneda.upper() == "USD" and self.total_dls > 0:
            return self.total_dls
        return self.total_pesos


@dataclass
class GrupoPoliza:
    empresa: str
    poliza: str
    filas: list[FilaLayout] = field(default_factory=list)
    total_mxn: Decimal = Decimal("0")
    total_usd: Decimal = Decimal("0")
    tiene_mixed: bool = False
    moneda_dominante: str = ""

    def calcular_totales(self) -> None:
        self.total_mxn = sum((f.total_pesos for f in self.filas), Decimal("0"))
        self.total_usd = sum((f.total_dls for f in self.filas), Decimal("0"))
        monedas = {f.moneda.upper().strip() for f in self.filas if f.moneda.strip()}
        self.tiene_mixed = len(monedas) > 1
        if len(monedas) == 1:
            self.moneda_dominante = monedas.pop()
        elif "MXN" in monedas:
            self.moneda_dominante = "MXN"
        else:
            self.moneda_dominante = "USD"

    @property
    def total_grupo(self) -> Decimal:
        if self.moneda_dominante == "USD":
            return self.total_usd
        return self.total_mxn

    @property
    def grupo_id(self) -> str:
        return f"{self.empresa}|{self.poliza}"


@dataclass
class MovimientoBanco:
    archivo: str
    empresa: str
    banco: str
    cuenta: str
    moneda: str
    fecha: str
    concepto: str
    cargo: Decimal
    abono: Decimal
    referencia: str
    es_tdc: bool = False
    poliza_relacionada: str = ""
    cruce_cargo: str = ""
    cruce_abono: str = ""
    estatus: str = ""

    @property
    def movimiento_id(self) -> str:
        return f"{self.archivo}|{self.empresa}|{self.banco}|{self.cuenta}|{self.fecha}|{self.referencia}|{self.cargo}|{self.abono}"


@dataclass
class ResultadoCruce:
    grupo: GrupoPoliza
    estatus: EstatusCruce
    causa: str = ""
    movimiento_asignado: MovimientoBanco | None = None
    candidatos: list[MovimientoBanco] = field(default_factory=list)
    cruce_bancario: str = ""
    diferencia: Decimal = Decimal("0")
