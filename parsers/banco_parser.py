from __future__ import annotations

from typing import BinaryIO

import pandas as pd

from core.models import MovimientoBancario
from core.utils import encontrar_columna, normalizar_referencia, to_datetime, to_decimal


class BancoParser:
    COLUMNAS = {
        "fecha": ["fecha", "fecha operacion", "fecha de operacion"],
        "concepto": ["concepto", "descripcion", "detalle"],
        "cargo": ["cargo", "retiro", "debe"],
        "abono": ["abono", "deposito", "haber"],
        "referencia": ["referencia", "ref", "cruce bancario", "clave rastreo"],
        "cuenta": ["cuenta"],
        "banco": ["banco"],
        "moneda": ["moneda"],
        "clave_rastreo": ["clave rastreo", "rastreo"],
        "autorizacion": ["autorizacion"],
        "num_operacion": ["numero operacion", "num operacion", "operacion"],
    }

    def __init__(self) -> None:
        self.errores: list[str] = []

    def parsear_excel(self, archivo: BinaryIO) -> list[MovimientoBancario]:
        df = pd.read_excel(archivo)
        return self.parsear_dataframe(df)

    def parsear_dataframe(self, df: pd.DataFrame) -> list[MovimientoBancario]:
        columnas = {campo: encontrar_columna(list(df.columns), candidatos) for campo, candidatos in self.COLUMNAS.items()}
        faltantes = [campo for campo in ["fecha", "concepto"] if not columnas.get(campo)]
        if faltantes:
            raise ValueError(f"Faltan columnas requeridas en banco: {', '.join(faltantes)}")

        movimientos: list[MovimientoBancario] = []
        for idx, fila in df.iterrows():
            try:
                get = lambda campo, default="": fila[columnas[campo]] if columnas.get(campo) else default
                referencia = normalizar_referencia(get("referencia", "") or get("clave_rastreo", ""))
                movimientos.append(
                    MovimientoBancario(
                        banco=str(get("banco", "")),
                        cuenta=str(get("cuenta", "")),
                        fecha=to_datetime(get("fecha")),
                        concepto=str(get("concepto", "")),
                        cargo=to_decimal(get("cargo", 0)),
                        abono=to_decimal(get("abono", 0)),
                        moneda=str(get("moneda", "MXN") or "MXN"),
                        referencia=referencia,
                        clave_rastreo=normalizar_referencia(get("clave_rastreo", "")),
                        autorizacion=str(get("autorizacion", "")),
                        num_operacion=str(get("num_operacion", "")),
                        cruce_bancario=referencia,
                    )
                )
            except Exception as exc:
                self.errores.append(f"Fila {idx + 2}: {exc}")
        return movimientos
