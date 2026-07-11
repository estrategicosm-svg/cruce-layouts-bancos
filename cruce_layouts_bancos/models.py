"""Modelos para cruce de layouts contra estados de cuenta."""
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


EMPRESA_CODES = {
    "CSC": "CSC", "INTRA": "INTRA", "ICOLD": "ICOLD",
    "TRANS": "TRANS", "TRANSCRUCES": "TRANS",
}

BANCO_CODES = {
    "BANAMEX": "BNMX", "BBVA": "BBVA", "BAJIO": "BAJIO",
    "BANREGIO": "BREG", "IBC": "IBC", "MONEX": "MONEX",
    "AMEX": "AMEX",
}


def normalizar_empresa(nombre: str) -> str:
    return EMPRESA_CODES.get(nombre.upper().strip(), nombre.upper().strip())


def normalizar_banco(nombre: str) -> str:
    return BANCO_CODES.get(nombre.upper().strip(), nombre.upper().strip()[:4])


@dataclass
class FilaLayout:
    empresa: str
    poliza: str
    uuid: str
    rfc: str
    nombre: str
    fecha_factura: str
    fecha_operacion: str
    moneda: str
    total_pesos: Decimal
    total_dls: Decimal
    banco: str
    cruce_bancario: str = ""

    @property
    def grupo_id(self) -> str:
        return f"{self.empresa}|{self.poliza}"


@dataclass
class GrupoPoliza:
    empresa: str
    poliza: str
    filas: list[FilaLayout] = field(default_factory=list)
    total_mxn: Decimal = Decimal("0")
    total_usd: Decimal = Decimal("0")
    tiene_mixed: bool = False
    moneda_dominante: str = ""

    @property
    def grupo_id(self) -> str:
        return f"{self.empresa}|{self.poliza}"

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


@dataclass
class MovimientoBanco:
    archivo_origen: str
    ruta_interna_zip: str
    empresa_detectada: str
    banco_detectado: str
    cuenta_detectada: str
    cuenta_ultimos_4: str
    moneda_detectada: str
    mes_detectado: str
    fecha_movimiento: str
    descripcion_original: str
    referencia_usada: str
    clave_rastreo: str
    autorizacion: str
    cargo: Decimal
    abono: Decimal
    saldo: Decimal
    tipo_movimiento: str
    es_tdc: bool = False
    cruce_cargo: str = ""
    cruce_abono: str = ""
    poliza_relacionada: str = ""


@dataclass
class ErrorArchivo:
    archivo: str
    tipo: str
    error: str


@dataclass
class ResultadoLecturaBanco:
    movimientos: list[MovimientoBanco] = field(default_factory=list)
    archivos_totales: int = 0
    archivos_xlsx_ok: int = 0
    archivos_xlsx_fallidos: int = 0
    archivos_pdf_total: int = 0
    archivos_pdf_ok: int = 0
    archivos_pdf_fallidos: int = 0
    errores: list[ErrorArchivo] = field(default_factory=list)
    advertencias: list[str] = field(default_factory=list)
    tesseract_disponible: bool = False


@dataclass
class ResultadoCruce:
    grupo: GrupoPoliza
    estatus: EstatusCruce
    causa: str = ""
    movimiento_asignado: MovimientoBanco | None = None
    candidatos: list[MovimientoBanco] = field(default_factory=list)
    diferencia: Decimal = Decimal("0")
