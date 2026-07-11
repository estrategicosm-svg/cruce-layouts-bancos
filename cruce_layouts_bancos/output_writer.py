"""Genera Excel usando los templates exactos y llenando CRUCE BANCARIO."""
from __future__ import annotations

import hashlib
from copy import copy
from io import BytesIO
from pathlib import Path

from openpyxl import load_workbook

from cruce_layouts_bancos.models import MovimientoBanco

ASSETS = Path(__file__).parent / "assets"


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _copy_row(src_ws, dst_ws, src_row, dst_row):
    for col in range(1, src_ws.max_column + 1):
        src_cell = src_ws.cell(src_row, col)
        dst_cell = dst_ws.cell(dst_row, col)
        dst_cell.value = src_cell.value
        if src_cell.has_style:
            dst_cell.font = copy(src_cell.font)
            dst_cell.fill = copy(src_cell.fill)
            dst_cell.border = copy(src_cell.border)
            dst_cell.alignment = copy(src_cell.alignment)
            dst_cell.number_format = src_cell.number_format
        if src_cell.hyperlink:
            dst_cell.hyperlink = src_cell.hyperlink
        if src_cell.comment:
            dst_cell.comment = src_cell.comment


def _write_movimientos_sheet(ws, movimientos: list[MovimientoBanco], cruce_map: dict[str, str]):
    mov_by_archivo: dict[str, list[MovimientoBanco]] = {}
    for m in movimientos:
        fname = Path(m.archivo_origen).name
        mov_by_archivo.setdefault(fname, []).append(m)

    for row_idx in range(2, ws.max_row + 1):
        archivo = str(ws.cell(row_idx, 1).value or "")
        cargo_val = ws.cell(row_idx, 14).value
        abono_val = ws.cell(row_idx, 16).value
        fname = Path(archivo).name

        for m in mov_by_archivo.get(fname, []):
            matched = False
            if m.cruce_cargo and cargo_val:
                try:
                    if abs(float(cargo_val) - float(m.cargo)) < 0.01:
                        ws.cell(row_idx, 15).value = m.cruce_cargo
                        if m.poliza_relacionada:
                            ws.cell(row_idx, 20).value = m.poliza_relacionada
                        matched = True
                except (ValueError, TypeError):
                    pass
            if not matched and m.cruce_abono and abono_val:
                try:
                    if abs(float(abono_val) - float(m.abono)) < 0.01:
                        ws.cell(row_idx, 17).value = m.cruce_abono
                        if m.poliza_relacionada:
                            ws.cell(row_idx, 20).value = m.poliza_relacionada
                except (ValueError, TypeError):
                    pass
            if matched:
                break


def _rebuild_summary(ws, data_start: int, data_end: int):
    """Rebuild the RESUMEN POR BANCO section with correct formula ranges."""
    fr_cargo = f"$N${data_start}:$N${data_end}"
    fr_abono = f"$P${data_start}:$P${data_end}"
    rb = f"$B${data_start}:$B${data_end}"
    rc = f"$C${data_start}:$C${data_end}"
    rg = f"$G${data_start}:$G${data_end}"

    summary_title_row = data_end + 2
    summary_header_row = data_end + 3
    summary_data_start = data_end + 4

    ws.cell(summary_title_row, 1).value = "RESUMEN POR BANCO/CUENTA/MONEDA"

    headers = ["Banco", "Cuenta", "Moneda", "Total cargos", "Total abonos",
               "Neto", "Cantidad movimientos", "Validacion"]
    for i, h in enumerate(headers, 1):
        ws.cell(summary_header_row, i).value = h

    archivos_unicos: dict[str, tuple[str, str, str]] = {}
    for row_idx in range(data_start, data_end + 1):
        archivo = ws.cell(row_idx, 1).value
        empresa = ws.cell(row_idx, 3).value
        moneda = ws.cell(row_idx, 7).value
        if archivo and empresa:
            fname = str(archivo).strip()
            if fname not in archivos_unicos:
                archivos_unicos[fname] = (str(empresa).strip(), str(moneda).strip())

    for i, (fname, (empresa, moneda)) in enumerate(sorted(archivos_unicos.items())):
        r = summary_data_start + i
        ws.cell(r, 1).value = fname
        ws.cell(r, 2).value = empresa
        ws.cell(r, 3).value = moneda
        ws.cell(r, 4).value = f"=SUMIFS({fr_cargo},{rb},$A{r},{rc},$C{r},{rg},$A{r})"
        ws.cell(r, 5).value = f"=SUMIFS({fr_abono},{rb},$A{r},{rc},$C{r},{rg},$A{r})"
        ws.cell(r, 6).value = f"=E{r}-D{r}"
        ws.cell(r, 7).value = f"=COUNTIFS({rb},$A{r},{rc},$C{r},{rg},$A{r})"
        ws.cell(r, 8).value = f'=IF(E{r}-D{r}=0,"CUADRA","NO CUADRA")'

    return summary_data_start + len(archivos_unicos)


def generar_excel(
    filas_egresos: list,
    filas_ingresos: list,
    movimientos: list[MovimientoBanco],
    cruce_map: dict[str, str],
    archivo_salida: str | None = None,
) -> dict:
    wb = load_workbook(ASSETS / "LAYOUT_CARGA_EGRESOS_OUTPUT.xlsx")
    ws_eg = wb["DATOS"]
    ws_eg.title = "EGRESOS"

    idx_eg = {}
    for f in filas_egresos:
        key = (f.empresa.upper().strip(), f.poliza.strip(), f.uuid.strip())
        idx_eg[key] = f"{f.empresa}|{f.poliza}"

    col_cruce = ws_eg.max_column
    for row_idx in range(3, ws_eg.max_row + 1):
        emp = str(ws_eg.cell(row_idx, 1).value or "").strip()
        pol = str(ws_eg.cell(row_idx, 2).value or "").strip()
        uuid_val = str(ws_eg.cell(row_idx, 3).value or "").strip()
        grupo_id = idx_eg.get((emp.upper(), pol, uuid_val))
        if grupo_id and grupo_id in cruce_map:
            ws_eg.cell(row_idx, col_cruce).value = cruce_map[grupo_id]

    # --- INGRESOS ---
    wb_ing_src = load_workbook(ASSETS / "LAYOUT_CEDULA_INGRESOS_OUTPUT.xlsx")
    ws_ing_src = wb_ing_src["DATOS"]
    ws_ing = wb.create_sheet("INGRESOS")
    for row_idx in range(1, ws_ing_src.max_row + 1):
        for col_idx in range(1, ws_ing_src.max_column + 1):
            ws_ing.cell(row_idx, col_idx).value = ws_ing_src.cell(row_idx, col_idx).value
    wb_ing_src.close()

    idx_ing = {}
    for f in filas_ingresos:
        key = (f.empresa.upper().strip(), f.poliza.strip(), f.uuid.strip())
        idx_ing[key] = f"{f.empresa}|{f.poliza}"

    col_cruce_ing = ws_ing.max_column
    for row_idx in range(3, ws_ing.max_row + 1):
        emp = str(ws_ing.cell(row_idx, 1).value or "").strip()
        pol = str(ws_ing.cell(row_idx, 2).value or "").strip()
        uuid_val = str(ws_ing.cell(row_idx, 3).value or "").strip()
        grupo_id = idx_ing.get((emp.upper(), pol, uuid_val))
        if grupo_id and grupo_id in cruce_map:
            ws_ing.cell(row_idx, col_cruce_ing).value = cruce_map[grupo_id]

    # --- MOVIMIENTOS BANCARIOS ---
    wb_mov_src = load_workbook(ASSETS / "MOVIMIENTOS_BANCARIOS_OUTPUT.xlsx")
    ws_mov_src = wb_mov_src["ESTADOS_CUENTA"]

    resumen_row = ws_mov_src.max_row + 1
    for row in range(2, ws_mov_src.max_row + 1):
        v = ws_mov_src.cell(row, 1).value
        if v and "RESUMEN" in str(v).upper():
            resumen_row = row
            break

    src_data_end = 1
    for row in range(2, resumen_row):
        if ws_mov_src.cell(row, 1).value is not None:
            src_data_end = row

    ws_mov = wb.create_sheet("MOVIMIENTOS_BANCARIOS")

    for row_idx in range(1, src_data_end + 1):
        for col_idx in range(1, ws_mov_src.max_column + 1):
            ws_mov.cell(row_idx, col_idx).value = ws_mov_src.cell(row_idx, col_idx).value

    _write_movimientos_sheet(ws_mov, movimientos, cruce_map)
    _rebuild_summary(ws_mov, data_start=2, data_end=src_data_end)

    wb_mov_src.close()

    if "Sheet" in wb.sheetnames:
        del wb["Sheet"]

    buf = BytesIO()
    wb.save(buf)
    raw = buf.getvalue()

    if archivo_salida:
        Path(archivo_salida).parent.mkdir(parents=True, exist_ok=True)
        Path(archivo_salida).write_bytes(raw)

    return {
        "bytes": raw,
        "archivo": archivo_salida,
        "tamaño": len(raw),
        "sha256": _sha256(raw),
        "hojas": wb.sheetnames,
    }
