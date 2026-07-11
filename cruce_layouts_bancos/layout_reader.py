"""Lee layouts de egresos e ingresos y produce FilaLayout."""
from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path
from typing import BinaryIO

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cruce_layouts_bancos.models import FilaLayout, normalizar_empresa
from parsers.layout_detector import detectar_layout
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
    col_emp = _buscar_col(df.columns, ["empresa"])
    col_pol = _buscar_col(df.columns, ["poliza", "numero de poliza contable"])
    col_uuid = _buscar_col(df.columns, ["uuid", "folio fiscal", "uuid a"])
    col_rfc = _buscar_col(df.columns, ["rfc", "rfc proveedor", "rfc cliente"])
    col_nom = _buscar_col(df.columns, ["proveedor", "cliente", "nombre"])
    col_ff = _buscar_col(df.columns, ["fecha factura"])
    col_fo = _buscar_col(df.columns, ["fecha pago", "fecha cobro", "fecha de pago", "fecha de cobro"])
    col_mon = _buscar_col(df.columns, ["moneda"])
    col_tp = _buscar_col(df.columns, ["total pesos", "importe mxn", "monto mxn"])
    col_td = _buscar_col(df.columns, ["total dls", "total usd", "importe usd", "monto usd"])
    col_ban = _buscar_col(df.columns, ["banco"])

    for _, row in df.iterrows():
        empresa = str(row[col_emp]).strip() if col_emp and pd.notna(row.get(col_emp)) else ""
        poliza = str(row[col_pol]).strip() if col_pol and pd.notna(row.get(col_pol)) else ""
        uuid = str(row[col_uuid]).strip() if col_uuid and pd.notna(row.get(col_uuid)) else ""
        rfc = str(row[col_rfc]).strip() if col_rfc and pd.notna(row.get(col_rfc)) else ""
        nombre = str(row[col_nom]).strip() if col_nom and pd.notna(row.get(col_nom)) else ""
        ff = str(row[col_ff]).strip() if col_ff and pd.notna(row.get(col_ff)) else ""
        fo = str(row[col_fo]).strip() if col_fo and pd.notna(row.get(col_fo)) else ""
        moneda = str(row[col_mon]).strip() if col_mon and pd.notna(row.get(col_mon)) else "MXN"
        tp = to_decimal(row[col_tp]) if col_tp and pd.notna(row.get(col_tp)) else Decimal("0")
        td = to_decimal(row[col_td]) if col_td and pd.notna(row.get(col_td)) else Decimal("0")
        banco = str(row[col_ban]).strip() if col_ban and pd.notna(row.get(col_ban)) else ""

        filas.append(FilaLayout(
            empresa=normalizar_empresa(empresa),
            poliza=poliza,
            uuid=normalizar_uuid(uuid),
            rfc=rfc,
            nombre=nombre,
            fecha_factura=ff,
            fecha_operacion=fo,
            moneda=moneda.upper().strip(),
            total_pesos=tp,
            total_dls=td,
            banco=banco,
        ))

    return filas
