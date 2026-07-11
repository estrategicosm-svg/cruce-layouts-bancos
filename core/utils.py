from __future__ import annotations

import re
import unicodedata
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

import pandas as pd


def normalizar_texto(valor: Any) -> str:
    if valor is None or (isinstance(valor, float) and pd.isna(valor)):
        return ""
    texto = str(valor).strip().lower()
    texto = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii")
    texto = re.sub(r"[^a-z0-9]+", " ", texto)
    return re.sub(r"\s+", " ", texto).strip()


def normalizar_uuid(valor: Any) -> str:
    return str(valor or "").strip().upper()


def normalizar_referencia(valor: Any) -> str:
    return re.sub(r"\s+", "", str(valor or "").strip().upper())


def to_decimal(valor: Any, default: str = "0") -> Decimal:
    if valor is None or pd.isna(valor):
        return Decimal(default)
    texto = str(valor).replace("$", "").replace(",", "").strip()
    if not texto:
        return Decimal(default)
    try:
        return Decimal(texto)
    except (InvalidOperation, ValueError):
        return Decimal(default)


_DATE_FORMATS = (
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d",
    "%d/%m/%Y %H:%M:%S",
    "%d/%m/%Y",
    "%d-%m-%Y %H:%M:%S",
    "%d-%m-%Y",
    "%d/%b/%Y",
    "%d/%b %Y",
    "%d %b %Y",
    "%d %B %Y",
)


def to_datetime(valor: Any) -> datetime:
    if isinstance(valor, datetime):
        return valor
    if valor is None or pd.isna(valor):
        return datetime.min
    s = str(valor).strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    fecha = pd.to_datetime(valor, errors="coerce", dayfirst=True)
    if pd.isna(fecha):
        return datetime.min
    return fecha.to_pydatetime()


def encontrar_columna(columnas: list[str], candidatos: list[str]) -> str | None:
    normalizadas = {normalizar_texto(col): col for col in columnas}
    for candidato in candidatos:
        llave = normalizar_texto(candidato)
        if llave in normalizadas:
            return normalizadas[llave]
    for candidato in candidatos:
        llave = normalizar_texto(candidato)
        for normalizada, original in normalizadas.items():
            if llave and (llave in normalizada or normalizada in llave):
                return original
    return None
