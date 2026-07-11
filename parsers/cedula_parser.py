"""Parser for cedula de egresos layout.

Supports 2-row headers, auto-detects layout, and maps to CedulaRegistro.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import BinaryIO

import pandas as pd

from core.models import CedulaRegistro
from core.utils import normalizar_referencia, normalizar_uuid, to_datetime, to_decimal
from parsers.layout_detector import (
    LayoutDetection,
    LayoutType,
    detectar_layout,
)


@dataclass
class ParseResult:
    registros: list[CedulaRegistro] = field(default_factory=list)
    detection: LayoutDetection | None = None
    errores: list[str] = field(default_factory=list)
    filas_leidas: int = 0


class CedulaParser:
    def __init__(self) -> None:
        self.errores: list[str] = []
        self.detection: LayoutDetection | None = None

    def parsear_excel(self, archivo: BinaryIO, layout_hint: str = "") -> list[CedulaRegistro]:
        """Parse egresos layout file. Auto-detects header row and layout type."""
        detection = detectar_layout(archivo, layout_hint or "EGRESOS")
        self.detection = detection

        if not detection.valido:
            self.errores.extend(detection.errores)
            return []

        df = pd.read_excel(archivo, header=detection.header_row)

        # Rename to internal names
        rename_map = {v: k for k, v in detection.column_mapping.items()}
        df = df.rename(columns=rename_map)

        return self.parsear_dataframe(df, detection)

    def parsear_dataframe(
        self, df: pd.DataFrame, detection: LayoutDetection | None = None,
    ) -> list[CedulaRegistro]:
        """Parse DataFrame with columns already renamed to internal names.

        Required internal columns: uuid, fecha_operacion (mapped from fecha_pago),
        total_pesos (mapped from importe concept).
        """
        # Build column map from DataFrame columns
        columns = list(df.columns)

        col_empresa = _find_col(columns, ["empresa", "empresa"])
        col_poliza = _find_col(columns, ["poliza", "numero de poliza contable", "numero poliza"])
        col_uuid = _find_col(columns, ["uuid", "folio fiscal", "uuid a"])
        col_rfc = _find_col(columns, ["rfc", "rfc proveedor"])
        col_nombre = _find_col(columns, ["nombre", "proveedor", "nombre del cliente/proveedor"])
        col_fecha_factura = _find_col(columns, ["fecha_factura", "fecha factura"])
        col_fecha_operacion = _find_col(columns, ["fecha_operacion", "fecha pago", "fecha de pago", "fecha"])
        col_moneda = _find_col(columns, ["moneda"])
        col_total_pesos = _find_col(columns, ["total_pesos", "total pesos", "importe", "total", "importe mxn"])
        col_total_dls = _find_col(columns, ["total_dls", "total dls", "total usd", "importe usd"])
        col_banco = _find_col(columns, ["banco"])

        # Validate required columns
        required = {
            "uuid": col_uuid,
            "fecha_operacion": col_fecha_operacion,
            "total_pesos": col_total_pesos,
        }
        faltantes = [name for name, col in required.items() if col is None]
        if faltantes:
            layout_info = f"Layout {detection.layout_type.value}" if detection else "Layout desconocido"
            raise ValueError(
                f"{layout_info}: columnas requeridas no encontradas en DataFrame: {', '.join(faltantes)}. "
                f"Columnas disponibles: {columns}"
            )

        registros: list[CedulaRegistro] = []
        for idx, fila in df.iterrows():
            try:
                def _get(col_name, default=""):
                    return fila[col_name] if col_name and col_name in df.columns else default

                empresa = str(_get(col_empresa, ""))
                moneda = str(_get(col_moneda, "MXN") or "MXN")
                total_pesos = to_decimal(_get(col_total_pesos, 0))
                total_dls = to_decimal(_get(col_total_dls, 0))

                # Importe: MXN uses total_pesos, USD uses total_dls
                if moneda.upper() == "USD" and total_dls > 0:
                    importe = total_dls
                else:
                    importe = total_pesos

                registros.append(
                    CedulaRegistro(
                        poliza=str(_get(col_poliza, "")),
                        cliente=str(_get(col_nombre, "")),
                        rfc=str(_get(col_rfc, "")),
                        uuid=normalizar_uuid(_get(col_uuid, "")),
                        importe=importe,
                        base_iva_16=importe,
                        base_iva_8=Decimal("0"),
                        base_iva_0=Decimal("0"),
                        exentos=Decimal("0"),
                        iva=Decimal("0"),
                        retenciones=Decimal("0"),
                        moneda=moneda,
                        tipo_cambio=Decimal("1"),
                        fecha_pago=to_datetime(_get(col_fecha_operacion)),
                        banco=str(_get(col_banco, "")),
                        cruce_bancario=normalizar_referencia(_get(col_banco, "")),
                        empresa=empresa,
                    )
                )
            except Exception as exc:
                self.errores.append(f"Fila {idx + 2}: {exc}")

        return registros


def _find_col(columns: list[str], candidates: list[str]) -> str | None:
    """Find a column by normalized name matching.

    Priority: exact normalized match > substring containment.
    All exact matches are checked before any substring matches.
    """
    norm_map = {}
    for c in columns:
        norm = str(c).strip().lower()
        norm_map[norm] = c

    # Pass 1: exact match for all candidates
    for cand in candidates:
        norm_cand = cand.strip().lower()
        if norm_cand in norm_map:
            return norm_map[norm_cand]

    # Pass 2: substring containment (only if no exact match)
    for cand in candidates:
        norm_cand = cand.strip().lower()
        if not norm_cand:
            continue
        for norm_col, orig in norm_map.items():
            if norm_cand and (norm_cand in norm_col or norm_col in norm_cand):
                return orig
    return None


from decimal import Decimal
