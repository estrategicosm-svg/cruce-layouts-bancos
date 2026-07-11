"""Layout detector for cedula Excel files.

Auto-detects:
- Header row (skips numeric/informational rows)
- Layout type (EGRESOS vs INGRESOS) by column names
- Maps columns to internal schema
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

import pandas as pd

from core.utils import normalizar_texto


class LayoutType(str, Enum):
    EGRESOS = "EGRESOS"
    INGRESOS = "INGRESOS"
    DESCONOCIDO = "DESCONOCIDO"


# Internal field -> list of candidates (normalized matches)
EGRESOS_COLUMNS = {
    "empresa": ["empresa"],
    "poliza": ["poliza", "numero de poliza contable"],
    "uuid": ["uuid", "folio fiscal", "uuid a"],
    "rfc": ["rfc proveedor", "rfc"],
    "nombre": ["proveedor", "nombre del cliente/proveedor", "nombre"],
    "fecha_factura": ["fecha factura"],
    "fecha_operacion": ["fecha pago", "fecha de pago"],
    "moneda": ["moneda"],
    "total_pesos": ["total pesos", "importe mxn", "monto mxn"],
    "total_dls": ["total dls", "total usd", "importe usd", "monto usd"],
    "banco": ["banco"],
}

INGRESOS_COLUMNS = {
    "empresa": ["empresa"],
    "poliza": ["poliza", "numero de poliza contable"],
    "uuid": ["uuid", "folio fiscal", "uuid a"],
    "rfc": ["rfc cliente", "rfc"],
    "nombre": ["cliente", "nombre del cliente", "nombre"],
    "fecha_factura": ["fecha factura"],
    "fecha_operacion": ["fecha cobro", "fecha de cobro"],
    "moneda": ["moneda"],
    "total_pesos": ["total pesos", "importe mxn", "monto mxn"],
    "total_dls": ["total dls", "total usd", "importe usd", "monto usd"],
    "banco": ["banco"],
}

# Required columns for each layout (must all be found)
EGRESOS_REQUIRED = {"uuid", "fecha_operacion", "total_pesos"}
INGRESOS_REQUIRED = {"uuid", "fecha_operacion", "total_pesos"}


def _find_header_row(raw_df: pd.DataFrame, max_scan: int = 10) -> int:
    """Inspect first max_scan rows to find the real header row.

    Heuristic: the header row is the first row where most cells are non-empty strings.
    Row 0 in official layouts is numeric (column indices).
    """
    scan_rows = min(max_scan, len(raw_df))
    best_row = 0
    best_score = -1

    for row_idx in range(scan_rows):
        row_values = raw_df.iloc[row_idx]
        str_count = sum(
            1 for v in row_values
            if v is not None and isinstance(v, str) and len(v.strip()) > 0
        )
        if str_count > best_score:
            best_score = str_count
            best_row = row_idx

    return best_row


def _detect_layout_by_columns(columns: list[str]) -> LayoutType:
    """Detect layout type by checking if column names match egresos or ingresos patterns."""
    norm_cols = [normalizar_texto(c) for c in columns]
    norm_set = set(norm_cols)

    # Check for distinctive columns
    has_proveedor = any("proveedor" in c and "rfc" not in c for c in norm_set)
    has_cliente = any("cliente" in c and "rfc" not in c for c in norm_set)
    has_fecha_pago = any("fecha pago" in c or "fecha de pago" in c for c in norm_set)
    has_fecha_cobro = any("fecha cobro" in c or "fecha de cobro" in c for c in norm_set)

    if has_proveedor and has_fecha_pago:
        return LayoutType.EGRESOS
    if has_cliente and has_fecha_cobro:
        return LayoutType.INGRESOS

    # Fallback: check if UUID + POLIZA + MONEDA exist
    has_uuid = any("uuid" in c for c in norm_set)
    has_moneda = any("moneda" in c for c in norm_set)
    if has_uuid and has_moneda:
        if has_fecha_pago:
            return LayoutType.EGRESOS
        if has_fecha_cobro:
            return LayoutType.INGRESOS

    return LayoutType.DESCONOCIDO


@dataclass
class LayoutDetection:
    layout_type: LayoutType
    header_row: int
    columns_recognized: int
    rows_data: int
    column_mapping: dict[str, str] = field(default_factory=dict)
    missing_required: list[str] = field(default_factory=list)
    errores: list[str] = field(default_factory=list)

    @property
    def valido(self) -> bool:
        return (
            self.layout_type != LayoutType.DESCONOCIDO
            and len(self.missing_required) == 0
            and self.columns_recognized > 0
        )


def detectar_layout(archivo, layout_hint: str = "") -> LayoutDetection:
    """Detect layout from a file-like object.

    Args:
        archivo: BinaryIO file-like object (e.g., Streamlit UploadedFile)
        layout_hint: Optional hint ("EGRESOS" or "INGRESOS") to force layout type

    Returns:
        LayoutDetection with all metadata
    """
    raw_df = pd.read_excel(archivo, header=None, nrows=15)
    header_idx = _find_header_row(raw_df)

    df_with_header = pd.read_excel(archivo, header=header_idx)
    columns = list(df_with_header.columns)

    if layout_hint:
        layout_type = LayoutType.EGRESOS if "EGRESO" in layout_hint.upper() else LayoutType.INGRESOS
    else:
        layout_type = _detect_layout_by_columns(columns)

    column_candidates = EGRESOS_COLUMNS if layout_type == LayoutType.EGRESOS else INGRESOS_COLUMNS
    required = EGRESOS_REQUIRED if layout_type == LayoutType.EGRESOS else INGRESOS_REQUIRED

    mapping = {}
    missing_required = []
    errores = []

    for field_name, candidates in column_candidates.items():
        matched_col = _find_column(columns, candidates)
        if matched_col:
            mapping[field_name] = matched_col
        elif field_name in required:
            missing_required.append(field_name)

    if missing_required:
        errores.append(
            f"Layout {layout_type.value}: columnas requeridas no encontradas: "
            f"{', '.join(missing_required)}"
        )

    return LayoutDetection(
        layout_type=layout_type,
        header_row=header_idx,
        columns_recognized=len(mapping),
        rows_data=len(df_with_header),
        column_mapping=mapping,
        missing_required=missing_required,
        errores=errores,
    )


def _find_column(columns: list[str], candidates: list[str]) -> str | None:
    """Find a column from candidates list using normalized matching."""
    norm_map = {normalizar_texto(c): c for c in columns}

    # Pass 1: exact match
    for cand in candidates:
        norm_cand = normalizar_texto(cand)
        if norm_cand in norm_map:
            return norm_map[norm_cand]

    # Pass 2: substring containment
    for cand in candidates:
        norm_cand = normalizar_texto(cand)
        if not norm_cand:
            continue
        for norm_col, orig_col in norm_map.items():
            if norm_cand in norm_col or norm_col in norm_cand:
                return orig_col

    return None


def parsear_layout(
    archivo,
    layout_hint: str = "",
) -> tuple[pd.DataFrame, LayoutDetection]:
    """Parse a cedula layout file into a DataFrame with proper headers.

    Returns:
        (DataFrame with correct headers and data, LayoutDetection metadata)
    """
    detection = detectar_layout(archivo, layout_hint)

    if not detection.valido:
        return pd.DataFrame(), detection

    df = pd.read_excel(archivo, header=detection.header_row)

    # Rename columns to internal names where mapped
    rename_map = {v: k for k, v in detection.column_mapping.items()}
    df = df.rename(columns=rename_map)

    return df, detection
