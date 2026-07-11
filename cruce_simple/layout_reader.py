"""Lee layouts de egresos e ingresos y produce FilaLayout."""
from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path
from typing import BinaryIO

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cruce_simple.models import FilaLayout, normalizar_empresa
from parsers.layout_detector import LayoutType, detectar_layout
from core.utils import normalizar_uuid, to_decimal


def _buscar_col(columns, candidatos: list[str]) -> str | None:
    norm_map = {}
    for c in columns:
        norm_map[c.lower().strip().replace("  ", " ")] = c
    for cand in candidatos:
        cn = cand.lower().strip().replace("  ", " ")
        if cn in norm_map:
            return norm_map[cn]
    for cand in candidatos:
        cn = cand.lower().strip()
        for col_norm, col_orig in norm_map.items():
            if cn in col_norm:
                return col_orig
    return None


def leer_layout(archivo: BinaryIO, nombre: str, hint: str = "") -> list[FilaLayout]:
    detection = detectar_layout(archivo, hint)
    if not detection.valido:
        return []

    archivo.seek(0)
    import pandas as pd
    df = pd.read_excel(archivo, header=detection.header_row)

    filas: list[FilaLayout] = []
    col_empresa = _buscar_col(df.columns, ["empresa"])
    col_poliza = _buscar_col(df.columns, ["poliza", "numero de poliza contable"])
    col_uuid = _buscar_col(df.columns, ["uuid", "folio fiscal", "uuid a"])
    col_rfc = _buscar_col(df.columns, ["rfc", "rfc proveedor", "rfc cliente"])
    col_nombre = _buscar_col(df.columns, ["proveedor", "cliente", "nombre"])
    col_fecha = _buscar_col(df.columns, ["fecha factura", "fecha pago", "fecha cobro", "fecha de pago", "fecha de cobro"])
    col_moneda = _buscar_col(df.columns, ["moneda"])
    col_tp = _buscar_col(df.columns, ["total pesos", "importe mxn", "monto mxn"])
    col_td = _buscar_col(df.columns, ["total dls", "total usd", "importe usd", "monto usd"])
    col_banco = _buscar_col(df.columns, ["banco"])

    for _, row in df.iterrows():
        empresa_raw = str(row[col_empresa]).strip() if col_empresa and pd.notna(row.get(col_empresa)) else ""
        poliza_raw = str(row[col_poliza]).strip() if col_poliza and pd.notna(row.get(col_poliza)) else ""
        uuid_raw = str(row[col_uuid]).strip() if col_uuid and pd.notna(row.get(col_uuid)) else ""
        rfc_raw = str(row[col_rfc]).strip() if col_rfc and pd.notna(row.get(col_rfc)) else ""
        nombre_raw = str(row[col_nombre]).strip() if col_nombre and pd.notna(row.get(col_nombre)) else ""
        fecha_raw = str(row[col_fecha]).strip() if col_fecha and pd.notna(row.get(col_fecha)) else ""
        moneda_raw = str(row[col_moneda]).strip() if col_moneda and pd.notna(row.get(col_moneda)) else "MXN"
        tp = to_decimal(row[col_tp]) if col_tp and pd.notna(row.get(col_tp)) else Decimal("0")
        td = to_decimal(row[col_td]) if col_td and pd.notna(row.get(col_td)) else Decimal("0")
        banco_raw = str(row[col_banco]).strip() if col_banco and pd.notna(row.get(col_banco)) else ""

        filas.append(FilaLayout(
            empresa=normalizar_empresa(empresa_raw),
            poliza=poliza_raw,
            uuid=normalizar_uuid(uuid_raw),
            rfc=rfc_raw,
            nombre=nombre_raw,
            fecha=fecha_raw,
            moneda=moneda_raw.upper().strip(),
            total_pesos=tp,
            total_dls=td,
            banco=banco_raw,
            archivo_origen=nombre,
        ))

    return filas
