from __future__ import annotations

from typing import BinaryIO

import pandas as pd

from core.models import CedulaIngresoRegistro
from core.utils import encontrar_columna, normalizar_uuid, to_datetime, to_decimal


class CedulaIngresosParser:
    COLUMNAS = {
        "rfc": ["rfc"],
        "cliente": ["cliente", "nombre del cliente", "nombre"],
        "uuid": ["uuid a", "uuid", "folio fiscal"],
        "factura": ["no factura", "numero factura", "factura", "no. factura"],
        "fecha": ["fecha", "fecha de pago", "fecha pago"],
        "total": ["total"],
        "moneda": ["moneda"],
        "amount_mxn": ["amount mxn", "importe mxn", "monto mxn"],
        "amount_usd": ["amount usd", "importe usd", "monto usd"],
        "forma_pago": ["forma de pago", "forma pago", "medio de pago"],
        "folio_transferencia": ["folio de transferencia o cheque", "folio transferencia", "transferencia", "cheque", "folio"],
        "descripcion": ["descripcion", "descripcion del servicio", "concepto"],
    }

    def __init__(self) -> None:
        self.errores: list[str] = []

    def parsear_excel(self, archivo: BinaryIO) -> list[CedulaIngresoRegistro]:
        df = pd.read_excel(archivo)
        return self.parsear_dataframe(df)

    def parsear_dataframe(self, df: pd.DataFrame) -> list[CedulaIngresoRegistro]:
        columnas = {campo: encontrar_columna(list(df.columns), candidatos) for campo, candidatos in self.COLUMNAS.items()}
        faltantes = [campo for campo in ["uuid", "total", "fecha"] if not columnas.get(campo)]
        if faltantes:
            raise ValueError(f"Faltan columnas requeridas en cedula de ingresos: {', '.join(faltantes)}")

        registros: list[CedulaIngresoRegistro] = []
        for idx, fila in df.iterrows():
            try:
                get = lambda campo, default="": fila[columnas[campo]] if columnas.get(campo) else default
                registros.append(
                    CedulaIngresoRegistro(
                        uuid=normalizar_uuid(get("uuid", "")),
                        cliente=str(get("cliente", "")),
                        rfc=str(get("rfc", "")),
                        factura=str(get("factura", "")),
                        fecha=to_datetime(get("fecha")),
                        total=to_decimal(get("total", 0)),
                        moneda=str(get("moneda", "MXN") or "MXN"),
                        amount_mxn=to_decimal(get("amount_mxn", 0)),
                        amount_usd=to_decimal(get("amount_usd", 0)),
                        forma_pago=str(get("forma_pago", "")),
                        folio_transferencia=str(get("folio_transferencia", "")),
                        descripcion=str(get("descripcion", "")),
                    )
                )
            except Exception as exc:
                self.errores.append(f"Fila {idx + 2}: {exc}")
        return registros
