from __future__ import annotations

from decimal import Decimal
from typing import BinaryIO

import pandas as pd

from core.models import CedulaRegistro
from core.utils import encontrar_columna, normalizar_referencia, normalizar_uuid, to_datetime, to_decimal


class CedulaParser:
    COLUMNAS = {
        "poliza": ["poliza", "numero de poliza contable", "numero poliza"],
        "cliente": ["cliente", "proveedor", "nombre del cliente/proveedor", "nombre"],
        "rfc": ["rfc"],
        "uuid": ["uuid", "folio fiscal"],
        "importe": ["importe", "total"],
        "base_iva_16": ["base iva 16", "base 16"],
        "base_iva_8": ["base iva 8", "base 8"],
        "base_iva_0": ["base iva 0", "base 0"],
        "exentos": ["exentos", "exento"],
        "iva": ["iva"],
        "retenciones": ["retenciones", "retencion"],
        "moneda": ["moneda"],
        "tipo_cambio": ["tipo de cambio", "tc"],
        "fecha_pago": ["fecha de pago", "fecha pago", "fecha"],
        "banco": ["banco"],
        "cruce_bancario": ["cruce bancario", "referencia", "ref"],
    }

    def __init__(self) -> None:
        self.errores: list[str] = []

    def parsear_excel(self, archivo: BinaryIO) -> list[CedulaRegistro]:
        df = pd.read_excel(archivo)
        return self.parsear_dataframe(df)

    def parsear_dataframe(self, df: pd.DataFrame) -> list[CedulaRegistro]:
        columnas = {campo: encontrar_columna(list(df.columns), candidatos) for campo, candidatos in self.COLUMNAS.items()}
        faltantes = [campo for campo in ["uuid", "importe", "fecha_pago"] if not columnas.get(campo)]
        if faltantes:
            raise ValueError(f"Faltan columnas requeridas en cedula: {', '.join(faltantes)}")

        registros: list[CedulaRegistro] = []
        for idx, fila in df.iterrows():
            try:
                get = lambda campo, default="": fila[columnas[campo]] if columnas.get(campo) else default
                registros.append(
                    CedulaRegistro(
                        poliza=str(get("poliza", "")),
                        cliente=str(get("cliente", "")),
                        rfc=str(get("rfc", "")),
                        uuid=normalizar_uuid(get("uuid", "")),
                        importe=to_decimal(get("importe", 0)),
                        base_iva_16=to_decimal(get("base_iva_16", 0)),
                        base_iva_8=to_decimal(get("base_iva_8", 0)),
                        base_iva_0=to_decimal(get("base_iva_0", 0)),
                        exentos=to_decimal(get("exentos", 0)),
                        iva=to_decimal(get("iva", 0)),
                        retenciones=to_decimal(get("retenciones", 0)),
                        moneda=str(get("moneda", "MXN") or "MXN"),
                        tipo_cambio=to_decimal(get("tipo_cambio", 1), "1"),
                        fecha_pago=to_datetime(get("fecha_pago")),
                        banco=str(get("banco", "")),
                        cruce_bancario=normalizar_referencia(get("cruce_bancario", "")),
                    )
                )
            except Exception as exc:
                self.errores.append(f"Fila {idx + 2}: {exc}")
        return registros
