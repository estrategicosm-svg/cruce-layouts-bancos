"""E2E with agent3 engine + operational Excel (5 sheets).

Loads real data, runs agent3 engine (grouping by póliza),
generates CEDULA_CONCILIACION_OPERATIVA_AGENT3_H3.xlsx.
"""
from __future__ import annotations

import hashlib
import io
import os
import sys
import tempfile
import time
import zipfile
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import openpyxl
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))

from agent3.engine import (
    EngineConfig,
    conciliar_banco_first,
)
from agent3.models import EstatusRegistro, COLUMNS_ORDER
from core.models import CedulaIngresoRegistro, CedulaRegistro, MovimientoBancario
from core.utils import normalizar_referencia, normalizar_uuid, to_decimal, to_datetime
from parsers.banco_parser import BancoParser
from parsers.cedula_parser import CedulaParser
from parsers.cedula_ingresos_parser import CedulaIngresosParser
from parsers.xml_parser import XMLParser

PAQUETE = Path(r"C:\Users\USER\Downloads\PAQUETE PARA SUBIR")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def _to_decimal(v) -> Decimal:
    if v is None:
        return Decimal("0")
    try:
        return Decimal(str(v).replace(",", "").strip())
    except Exception:
        return Decimal("0")


def _to_datetime(v) -> datetime:
    if v is None:
        return datetime(2024, 1, 1)
    if isinstance(v, datetime):
        return v
    return to_datetime(v)


def _load_egresos() -> list[CedulaRegistro]:
    parser = CedulaParser()
    with open(PAQUETE / "LAYOUT_CARGA_EGRESOS.xlsx", "rb") as f:
        regs = parser.parsear_excel(f, "EGRESOS")
    print(f"    Egresos detection: layout={parser.detection.layout_type.value}, "
          f"header_row={parser.detection.header_row + 1}, "
          f"columns={parser.detection.columns_recognized}")
    if parser.errores:
        print(f"    Egresos errors: {parser.errores[:3]}")
    return regs


def _load_ingresos() -> list[CedulaIngresoRegistro]:
    parser = CedulaIngresosParser()
    with open(PAQUETE / "LAYOUT_CEDULA_INGRESOS.xlsx", "rb") as f:
        regs = parser.parsear_excel(f, "INGRESOS")
    print(f"    Ingresos detection: layout={parser.detection.layout_type.value}, "
          f"header_row={parser.detection.header_row + 1}, "
          f"columns={parser.detection.columns_recognized}")
    if parser.errores:
        print(f"    Ingresos errors: {parser.errores[:3]}")
    return regs


def _load_movimientos_zip() -> tuple[list[MovimientoBancario], pd.DataFrame]:
    banco_parser = BancoParser()
    movimientos = []
    control_rows = []

    _SYSTEM_DIRS = {"__MACOSX", ".DS_Store", "Thumbs.db", "__pycache__"}

    def _es_ruta_segura(nombre: str) -> bool:
        parts = Path(nombre).parts
        return not any(
            p.startswith(".") or p.startswith("__") or p in _SYSTEM_DIRS
            for p in parts
        )

    with tempfile.TemporaryDirectory() as tmpdir:
        zip_path = os.path.join(tmpdir, "estados.zip")
        with open(zip_path, "wb") as f:
            f.write((PAQUETE / "ESTADOS_DE_CTA_RENOMBRADO.zip").read_bytes())

        with zipfile.ZipFile(zip_path) as zf:
            compatible = [
                n for n in zf.namelist()
                if _es_ruta_segura(n)
                and not n.startswith("__")
                and not n.endswith("/")
                and any(n.lower().endswith(ext) for ext in (".pdf", ".xlsx", ".xls"))
            ]

            for name in compatible:
                data = zf.read(name)
                fname = Path(name).name
                ext = Path(name).suffix.lower()
                empresa = Path(name).parts[0] if len(Path(name).parts) > 1 else ""
                error_archivo = ""
                movs_count = 0
                parser_tipo = ""
                moneda_detectada = ""
                fechas_validas = 0
                fechas_0001 = 0
                fecha_minima = ""
                fecha_maxima = ""
                fecha_causa = ""

                try:
                    if ext == ".pdf":
                        from parsers.pdf_parser import BancoPDFParser
                        parser_tipo = "BancoPDFParser"
                        df_pdf, val = BancoPDFParser().parsear_pdf(data, fname)
                        if df_pdf is not None and not df_pdf.empty:
                            movs = banco_parser.parsear_dataframe(df_pdf)
                            for mv in movs:
                                mv._archivo_origen = fname
                            movimientos.extend(movs)
                            movs_count = len(movs)
                            if not df_pdf.empty:
                                moneda_detectada = str(df_pdf.iloc[0].get("Moneda", ""))
                            # Date diagnostics
                            fechas = [m.fecha for m in movs]
                            fechas_validas = sum(1 for f in fechas if f and f != datetime.min)
                            fechas_0001 = sum(1 for f in fechas if not f or f == datetime.min)
                            if fechas_validas > 0:
                                valid_fechas = [f for f in fechas if f and f != datetime.min]
                                fecha_minima = min(valid_fechas).strftime("%Y-%m-%d") if valid_fechas else ""
                                fecha_maxima = max(valid_fechas).strftime("%Y-%m-%d") if valid_fechas else ""
                            if fechas_0001 > 0:
                                fecha_causa = f"{fechas_0001} fechas 0001-01-01 (sin año en formato)"
                        else:
                            error_archivo = "sin movimientos"
                            fecha_causa = "parser no extrajo movimientos"
                    else:
                        parser_tipo = "BancoParser"
                        df = pd.read_excel(io.BytesIO(data))
                        movs = banco_parser.parsear_dataframe(df)
                        for mv in movs:
                            mv._archivo_origen = fname
                        movimientos.extend(movs)
                        movs_count = len(movs)
                        if not df.empty:
                            mon_col = next((c for c in df.columns if "moneda" in c.lower()), None)
                            if mon_col:
                                moneda_detectada = str(df.iloc[0].get(mon_col, ""))
                        # Date diagnostics
                        fechas = [m.fecha for m in movs]
                        fechas_validas = sum(1 for f in fechas if f and f != datetime.min)
                        fechas_0001 = sum(1 for f in fechas if not f or f == datetime.min)
                        if fechas_validas > 0:
                            valid_fechas = [f for f in fechas if f and f != datetime.min]
                            fecha_minima = min(valid_fechas).strftime("%Y-%m-%d") if valid_fechas else ""
                            fecha_maxima = max(valid_fechas).strftime("%Y-%m-%d") if valid_fechas else ""
                        if fechas_0001 > 0:
                            fecha_causa = f"{fechas_0001} fechas 0001-01-01"
                except Exception as exc:
                    error_archivo = str(exc)
                    fecha_causa = str(exc)

                control_rows.append({
                    "ARCHIVO": fname,
                    "EMPRESA": empresa,
                    "TIPO_DOCUMENTO": ext.upper().lstrip("."),
                    "PARSER": parser_tipo,
                    "MOVIMIENTOS_EXTRAIDOS": movs_count,
                    "FECHAS_VALIDAS": fechas_validas,
                    "FECHAS_0001": fechas_0001,
                    "FECHA_MINIMA": fecha_minima,
                    "FECHA_MAXIMA": fecha_maxima,
                    "MONEDA_DETECTADA": moneda_detectada or "NO_DETERMINADA",
                    "CAUSA": fecha_causa,
                    "ERROR": error_archivo,
                    "ESTATUS": "OK" if not error_archivo else "ERROR",
                })

    control_df = pd.DataFrame(control_rows) if control_rows else pd.DataFrame()
    return movimientos, control_df


def main() -> None:
    print("=" * 80)
    print("E2E AGENT3 ENGINE + EXCEL OPERATIVO")
    print("=" * 80)
    t0 = time.time()

    # ── Load data ──
    print("\n[1] CARGANDO DATOS...")
    cedula_egresos = _load_egresos()
    cedula_ingresos = _load_ingresos()
    print(f"    FILAS_EGRESOS = {len(cedula_egresos)}")
    print(f"    FILAS_INGRESOS = {len(cedula_ingresos)}")

    # ── Load XMLs ──
    print("\n[2] CARGANDO XMLs...")
    xml_parser = XMLParser()
    cfdis_emitidos = xml_parser.parsear_zip(
        (PAQUETE / "XML_feb_24.zip").read_bytes(), origen_xml="EMITIDO"
    ).exitosos
    cfdis_recibidos = xml_parser.parsear_zip(
        (PAQUETE / "XML_RECIBIDOS_FEB_24.zip").read_bytes(), origen_xml="RECIBIDO"
    ).exitosos
    cfdis = cfdis_emitidos + cfdis_recibidos
    print(f"    XML_EMITIDOS = {len(cfdis_emitidos)}")
    print(f"    XML_RECIBIDOS = {len(cfdis_recibidos)}")
    print(f"    XML_TOTALES = {len(cfdis)}")

    # ── Load bank movements ──
    print("\n[3] CARGANDO MOVIMIENTOS BANCARIOS...")
    movimientos, control_df = _load_movimientos_zip()
    print(f"    MOVIMIENTOS_BANCARIOS_BRUTOS = {len(movimientos)}")

    # Filter zero amounts
    movimientos_validos = [
        m for m in movimientos
        if Decimal(str(m.cargo)) > Decimal("0") or Decimal(str(m.abono)) > Decimal("0")
    ]
    movimientos_descartados = len(movimientos) - len(movimientos_validos)
    print(f"    MOVIMIENTOS_BANCARIOS_VALIDOS = {len(movimientos_validos)}")
    print(f"    MOVIMIENTOS_DESCARTADOS = {movimientos_descartados}")
    print(f"    ARCHIVOS_BANCARIOS = {len(control_df)}")

    # Extract period per file
    from agent3.engine import _extraer_periodo
    periodos_por_archivo: dict[str, tuple[int, int]] = {}
    for _, crow in control_df.iterrows():
        fname = crow["ARCHIVO"]
        periodo = _extraer_periodo(fname)
        if periodo:
            periodos_por_archivo[fname] = periodo

    if not control_df.empty:
        print("\n[3b] REPORTE DE FECHAS POR ARCHIVO:")
        total_0001 = control_df["FECHAS_0001"].sum() if "FECHAS_0001" in control_df.columns else 0
        print(f"    TOTAL FECHAS_0001 = {total_0001}")
        for _, crow in control_df.iterrows():
            status_mark = "OK" if crow.get("FECHAS_0001", 0) == 0 else f"FECHAS_0001={crow['FECHAS_0001']}"
            p = periodos_por_archivo.get(crow['ARCHIVO'])
            p_str = f"{p[0]:02d}/{p[1]}" if p else "N/A"
            print(f"    {crow['ARCHIVO']}: MOVS={crow.get('MOVIMIENTOS_EXTRAIDOS', 0)} "
                  f"FECHAS_VALIDAS={crow.get('FECHAS_VALIDAS', 0)} {status_mark} "
                  f"RANGO={crow.get('FECHA_MINIMA', '')}..{crow.get('FECHA_MAXIMA', '')} "
                  f"PERIODO_ESPERADO={p_str} "
                  f"PARSER={crow.get('PARSER', '')} CAUSA={crow.get('CAUSA', '')}")

    # ── Run agent3 engine ──
    print("\n[4] EJECUTANDO MOTOR AGENT3...")
    config = EngineConfig(tolerancia_monto=Decimal("1.00"), tolerancia_dias=5)
    result = conciliar_banco_first(
        movimientos_bancarios=movimientos_validos,
        cedulas_egresos=cedula_egresos,
        cedulas_ingresos=cedula_ingresos,
        cfdis=cfdis,
        config=config,
        archivo_banco="ESTADOS_DE_CTA_RENOMBRADO",
        empresa_cedula="CSC",
        periodos_por_archivo=periodos_por_archivo,
    )

    # ── Metrics ──
    print("\n[5] METRICAS DEL MOTOR:")
    print(f"    FILAS_EGRESOS = {len(cedula_egresos)}")
    print(f"    FILAS_INGRESOS = {len(cedula_ingresos)}")
    print(f"    GRUPOS_EGRESOS = {len({f.GRUPO_ID for f in result.filas if f.GRUPO_ID.startswith('egreso_')})}")
    print(f"    GRUPOS_INGRESOS = {len({f.GRUPO_ID for f in result.filas if f.GRUPO_ID.startswith('ingreso_')})}")
    print(f"    XML_EMITIDOS = {len(cfdis_emitidos)}")
    print(f"    XML_RECIBIDOS = {len(cfdis_recibidos)}")
    print(f"    XML_TOTALES = {len(cfdis)}")
    print(f"    MOVIMIENTOS_BANCARIOS_BRUTOS = {result.movimientos_bancarios_totales}")
    print(f"    MOVIMIENTOS_BANCARIOS_VALIDOS = {len(movimientos_validos)}")
    print(f"    MOVIMIENTOS_DESCARTADOS = {movimientos_descartados}")
    estatus = result.estatus_grupos_por_tipo()
    print(f"    GRUPOS_CONCILIADOS = {estatus.get('CONCILIADO', 0)}")
    print(f"    GRUPOS_PROPUESTA = {estatus.get('PROPUESTA_REVISAR', 0)}")
    print(f"    GRUPOS_AMBIGUOS = {estatus.get('AMBIGUO', 0)}")
    print(f"    GRUPOS_SIN_CANDIDATO = {estatus.get('SIN_CANDIDATO', 0)}")
    print(f"    MOVIMIENTOS_TDC_EXCLUIDOS = {result.movimientos_tdc_excluidos}")
    print(f"    MOVIMIENTOS_FUERA_PERIODO = {result.movimientos_fuera_periodo}")
    print(f"    MOVIMIENTOS_FECHA_INVALIDA = {result.movimientos_fecha_invalida}")
    suma_verificacion = len(cedula_egresos) + len(cedula_ingresos)
    print(f"    SUMA_FILAS_CEDULA = {suma_verificacion}")
    total_grupos = sum(estatus.values())
    print(f"    TOTAL_GRUPO_IDS = {total_grupos}")
    print(f"    SUMA_ESTATUS = {estatus.get('CONCILIADO', 0) + estatus.get('PROPUESTA_REVISAR', 0) + estatus.get('AMBIGUO', 0) + estatus.get('SIN_CANDIDATO', 0)}")

    # ── Control de archivos ──
    print("\n[5b] CONTROL DE ARCHIVOS (tabla de control por archivo):")
    for rec in result.movimientos_universo[:1]:
        # Just show first to confirm it has PARTICIPA_UNIVERSO
        print(f"    Sample PARTICIPA_UNIVERSO={rec.PARTICIPA_UNIVERSO} CAUSA={rec.CAUSA_EXCLUSION}")

    participa_true = sum(1 for r in result.movimientos_universo if r.PARTICIPA_UNIVERSO)
    participa_false = sum(1 for r in result.movimientos_universo if not r.PARTICIPA_UNIVERSO)
    print(f"    UNIVERSO_TOTAL = {len(result.movimientos_universo)}")
    print(f"    UNIVERSO_PARTICIPA = {participa_true}")
    print(f"    UNIVERSO_EXCLUIDOS = {participa_false}")

    # ── Group examples ──
    print("\n[6] EJEMPLOS DE AGRUPACION POR POLIZA (20 primeros grupos):")
    from collections import defaultdict
    grupos = defaultdict(list)
    for f in result.filas:
        grupos[f.GRUPO_ID].append(f)

    example_count = 0
    for gid, filas in sorted(grupos.items()):
        if example_count >= 20:
            break
        f0 = filas[0]
        uuids = [f.POLIZA for f in filas]
        print(f"    {gid}: POLIZA={f0.POLIZA} EMPRESA={f0.EMPRESA} BANCO={f0.BANCO} "
              f"MONEDA={f0.MONEDA} NUM_XML={len(filas)} TOTAL_GRUPO={f0.TOTAL_GRUPO} "
              f"CRUCE_ID={f0.CRUCE_ID} MOVIMIENTO_ID={f0.MOVIMIENTO_ID[:16] if f0.MOVIMIENTO_ID else ''} "
              f"DIFERENCIA={f0.DIFERENCIA} ESTATUS={f0.ESTATUS.value}")
        example_count += 1

    # ── Generate operational Excel ──
    print("\n[7] GENERANDO EXCEL OPERATIVO...")

    # RESUMEN sheet
    egreso_groups = {f.GRUPO_ID for f in result.filas if f.GRUPO_ID.startswith("egreso_")}
    ingreso_groups = {f.GRUPO_ID for f in result.filas if f.GRUPO_ID.startswith("ingreso_")}
    estatus = result.estatus_grupos_por_tipo()
    conciliados = estatus.get("CONCILIADO", 0)
    propuesta = estatus.get("PROPUESTA_REVISAR", 0)
    ambiguos = estatus.get("AMBIGUO", 0)
    sin_candidato = estatus.get("SIN_CANDIDATO", 0)

    resumen_data = [
        {"METRICA": "FILAS_EGRESOS", "VALOR": len(cedula_egresos)},
        {"METRICA": "FILAS_INGRESOS", "VALOR": len(cedula_ingresos)},
        {"METRICA": "GRUPOS_EGRESOS", "VALOR": len(egreso_groups)},
        {"METRICA": "GRUPOS_INGRESOS", "VALOR": len(ingreso_groups)},
        {"METRICA": "XML_EMITIDOS", "VALOR": len(cfdis_emitidos)},
        {"METRICA": "XML_RECIBIDOS", "VALOR": len(cfdis_recibidos)},
        {"METRICA": "XML_TOTALES", "VALOR": len(cfdis)},
        {"METRICA": "MOVIMIENTOS_BANCARIOS_BRUTOS", "VALOR": result.movimientos_bancarios_totales},
        {"METRICA": "MOVIMIENTOS_BANCARIOS_VALIDOS", "VALOR": len(movimientos_validos)},
        {"METRICA": "MOVIMIENTOS_DESCARTADOS", "VALOR": movimientos_descartados},
        {"METRICA": "ARCHIVOS_BANCARIOS", "VALOR": len(control_df)},
        {"METRICA": "CONCILIADOS_POR_GRUPO", "VALOR": conciliados},
        {"METRICA": "PROPUESTA_POR_GRUPO", "VALOR": propuesta},
        {"METRICA": "AMBIGUOS_POR_GRUPO", "VALOR": ambiguos},
        {"METRICA": "SIN_CANDIDATO_POR_GRUPO", "VALOR": sin_candidato},
        {"METRICA": "TOTAL_GRUPOS", "VALOR": conciliados + propuesta + ambiguos + sin_candidato},
        {"METRICA": "MOVIMIENTOS_TDC_EXCLUIDOS", "VALOR": result.movimientos_tdc_excluidos},
        {"METRICA": "MOVIMIENTOS_FUERA_PERIODO", "VALOR": result.movimientos_fuera_periodo},
        {"METRICA": "MOVIMIENTOS_FECHA_INVALIDA", "VALOR": result.movimientos_fecha_invalida},
        {"METRICA": "SUMA_FILAS_CEDULA", "VALOR": len(cedula_egresos) + len(cedula_ingresos)},
    ]
    df_resumen = pd.DataFrame(resumen_data)

    # RESULTADO_EGRESOS sheet (from agent3 engine filas)
    egreso_rows = [f for f in result.filas if f.GRUPO_ID.startswith("egreso_")]
    df_egresos = pd.DataFrame([
        {
            "GRUPO_ID": f.GRUPO_ID,
            "POLIZA": f.POLIZA,
            "EMPRESA": f.EMPRESA,
            "BANCO": f.BANCO,
            "MONEDA": f.MONEDA,
            "FECHA_LAYOUT": f.FECHA_LAYOUT,
            "NUM_XML_GRUPO": f.NUM_XML_GRUPO,
            "TOTAL_GRUPO": str(f.TOTAL_GRUPO),
            "CRUCE_ID": f.CRUCE_ID,
            "CANDIDATO_CRUCE_ID": f.CANDIDATO_CRUCE_ID,
            "MOVIMIENTO_ID": f.MOVIMIENTO_ID,
            "CANDIDATO_MOVIMIENTO_ID": f.CANDIDATO_MOVIMIENTO_ID,
            "ARCHIVO_BANCO": f.ARCHIVO_BANCO,
            "FILA_BANCO": f.FILA_BANCO,
            "FECHA_BANCO": f.FECHA_BANCO,
            "CARGO": str(f.CARGO),
            "ABONO": str(f.ABONO),
            "DIFERENCIA": str(f.DIFERENCIA),
            "TIPO_MATCH": f.TIPO_MATCH.value,
            "NIVEL_CONFIANZA": f.NIVEL_CONFIANZA,
            "ESTATUS": f.ESTATUS.value,
        }
        for f in egreso_rows
    ])

    # RESULTADO_INGRESOS sheet
    ingreso_rows = [f for f in result.filas if f.GRUPO_ID.startswith("ingreso_")]
    df_ingresos = pd.DataFrame([
        {
            "GRUPO_ID": f.GRUPO_ID,
            "POLIZA": f.POLIZA,
            "EMPRESA": f.EMPRESA,
            "BANCO": f.BANCO,
            "MONEDA": f.MONEDA,
            "FECHA_LAYOUT": f.FECHA_LAYOUT,
            "NUM_XML_GRUPO": f.NUM_XML_GRUPO,
            "TOTAL_GRUPO": str(f.TOTAL_GRUPO),
            "CRUCE_ID": f.CRUCE_ID,
            "CANDIDATO_CRUCE_ID": f.CANDIDATO_CRUCE_ID,
            "MOVIMIENTO_ID": f.MOVIMIENTO_ID,
            "CANDIDATO_MOVIMIENTO_ID": f.CANDIDATO_MOVIMIENTO_ID,
            "ARCHIVO_BANCO": f.ARCHIVO_BANCO,
            "FILA_BANCO": f.FILA_BANCO,
            "FECHA_BANCO": f.FECHA_BANCO,
            "CARGO": str(f.CARGO),
            "ABONO": str(f.ABONO),
            "DIFERENCIA": str(f.DIFERENCIA),
            "TIPO_MATCH": f.TIPO_MATCH.value,
            "NIVEL_CONFIANZA": f.NIVEL_CONFIANZA,
            "ESTATUS": f.ESTATUS.value,
        }
        for f in ingreso_rows
    ])

    # CEDULA_BANCOS sheet (only participating bank movements with CRUCE_ID)
    cruce_id_map = {}
    for rec in result.movimientos_universo:
        cruce_id_map[rec.MOVIMIENTO_ID] = rec.CRUCE_ID

    df_bancos = pd.DataFrame([
        {
            "MOVIMIENTO_ID": rec.MOVIMIENTO_ID,
            "CRUCE_ID": rec.CRUCE_ID,
            "EMPRESA": rec.EMPRESA,
            "TIPO": rec.NATURALEZA,
            "BANCO": rec.BANCO,
            "CUENTA": rec.CUENTA,
            "MONEDA": rec.MONEDA,
            "FECHA": rec.FECHA,
            "CONCEPTO": rec.CONCEPTO,
            "CARGO": str(rec.CARGO),
            "ABONO": str(rec.ABONO),
            "REFERENCIA": rec.REFERENCIA,
            "ARCHIVO_ORIGEN": rec.ARCHIVO_BANCO,
            "FILA_ORIGEN": rec.FILA_BANCO,
            "PARTICIPA_UNIVERSO": rec.PARTICIPA_UNIVERSO,
            "CAUSA_EXCLUSION": rec.CAUSA_EXCLUSION,
            "ESTATUS": "VALIDO" if rec.PARTICIPA_UNIVERSO else "EXCLUIDO",
        }
        for rec in result.movimientos_universo
    ])

    # CONTROL_ARCHIVOS sheet
    control_archivos_data = []
    archivos_movs = {}
    for rec in result.movimientos_universo:
        archivos_movs.setdefault(rec.ARCHIVO_BANCO, []).append(rec)
    for archivo, recs in sorted(archivos_movs.items()):
        total = len(recs)
        participa = sum(1 for r in recs if r.PARTICIPA_UNIVERSO)
        excluidos = total - participa
        periodo = periodos_por_archivo.get(archivo)
        periodo_str = f"{periodo[0]:02d}/{periodo[1]}" if periodo else "N/A"
        control_archivos_data.append({
            "ARCHIVO": archivo,
            "MOVIMIENTOS_TOTALES": total,
            "PARTICIPA": participa,
            "EXCLUIDOS": excluidos,
            "PERIODO_ESPERADO": periodo_str,
        })
    df_control_archivos = pd.DataFrame(control_archivos_data)

    # REVISION_MANUAL sheet — 1 row per GRUPO_ID+CANDIDATO, deduplicated
    revision_grupos: dict[str, object] = {}
    for f in result.filas:
        if f.ESTATUS in (EstatusRegistro.PROPUESTA_REVISAR, EstatusRegistro.AMBIGUO, EstatusRegistro.SIN_CANDIDATO):
            key = f"{f.GRUPO_ID}|{f.CANDIDATO_CRUCE_ID or ''}|{f.CANDIDATO_MOVIMIENTO_ID or ''}"
            if key not in revision_grupos:
                revision_grupos[key] = f
    revision_rows = list(revision_grupos.values())
    df_revision = pd.DataFrame([
        {
            "GRUPO_ID": f.GRUPO_ID,
            "POLIZA": f.POLIZA,
            "EMPRESA": f.EMPRESA,
            "BANCO": f.BANCO,
            "MONEDA": f.MONEDA,
            "TOTAL_GRUPO": str(f.TOTAL_GRUPO),
            "CANDIDATO_CRUCE_ID": f.CANDIDATO_CRUCE_ID,
            "CANDIDATO_MOVIMIENTO_ID": f.CANDIDATO_MOVIMIENTO_ID,
            "DIFERENCIA": str(f.DIFERENCIA),
            "TIPO_MATCH": f.TIPO_MATCH.value,
            "ESTATUS": f.ESTATUS.value,
        }
        for f in revision_rows
    ])

    # Write Excel
    excel_path = Path(__file__).parent.parent / "outputs" / "CEDULA_CONCILIACION_OPERATIVA_AGENT3_H3.xlsx"
    excel_path.parent.mkdir(parents=True, exist_ok=True)

    with pd.ExcelWriter(str(excel_path), engine="openpyxl") as writer:
        df_resumen.to_excel(writer, sheet_name="RESUMEN", index=False)
        df_egresos.to_excel(writer, sheet_name="RESULTADO_EGRESOS", index=False)
        df_ingresos.to_excel(writer, sheet_name="RESULTADO_INGRESOS", index=False)
        df_bancos.to_excel(writer, sheet_name="CEDULA_BANCOS", index=False)
        df_revision.to_excel(writer, sheet_name="REVISION_MANUAL", index=False)
        df_control_archivos.to_excel(writer, sheet_name="CONTROL_ARCHIVOS", index=False)

    excel_bytes = excel_path.read_bytes()
    excel_hash = sha256_bytes(excel_bytes)
    excel_size = len(excel_bytes)

    # Verify sheets
    wb_check = openpyxl.load_workbook(io.BytesIO(excel_bytes))
    sheet_names = wb_check.sheetnames

    print(f"\n    NOMBRE = {excel_path.name}")
    print(f"    RUTA = {excel_path}")
    print(f"    TAMAÑO = {excel_size:,} bytes")
    print(f"    SHA256 = {excel_hash}")
    print(f"    FECHA_GENERACION = {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"    HOJAS = {sheet_names}")

    # Verify columns
    for sheet_name, df in [("RESULTADO_EGRESOS", df_egresos), ("RESULTADO_INGRESOS", df_ingresos), ("CEDULA_BANCOS", df_bancos)]:
        cols = list(df.columns)
        print(f"    COLUMNAS_{sheet_name} = {cols}")

    # Verify CRUCE_ID presence
    for col in ["CRUCE_ID", "MOVIMIENTO_ID", "CANDIDATO_CRUCE_ID", "CANDIDATO_MOVIMIENTO_ID"]:
        in_egresos = col in df_egresos.columns
        in_ingresos = col in df_ingresos.columns
        in_bancos = col in df_bancos.columns
        print(f"    {col}: EGRESOS={'OK' if in_egresos else 'FALTA'} INGRESOS={'OK' if in_ingresos else 'FALTA'} BANCOS={'OK' if in_bancos else 'FALTA'}")

    # Verify GRUPO_ID, NUM_XML_GRUPO, TOTAL_GRUPO, etc.
    for col in ["GRUPO_ID", "TOTAL_GRUPO", "POLIZA"]:
        in_egresos = col in df_egresos.columns
        print(f"    {col} en RESULTADO_EGRESOS: {'OK' if in_egresos else 'FALTA'}")

    # Print 10 sample rows from RESULTADO_EGRESOS with CRUCE_ID
    print("\n[8] 10 FILAS REALES DE RESULTADO_EGRESOS:")
    sample = df_egresos.head(10)
    for _, row in sample.iterrows():
        print(f"    GRUPO={row['GRUPO_ID']} POLIZA={row['POLIZA']} CRUCE_ID={row['CRUCE_ID']} "
              f"MOV_ID={row['MOVIMIENTO_ID'][:16] if row['MOVIMIENTO_ID'] else 'N/A'} "
              f"TOTAL={row['TOTAL_GRUPO']} DIF={row['DIFERENCIA']} STATUS={row['ESTATUS']}")

    # Print 10 sample rows from CEDULA_BANCOS
    print("\n[9] 10 FILAS REALES DE CEDULA_BANCOS:")
    sample_banco = df_bancos.head(10)
    for _, row in sample_banco.iterrows():
        print(f"    CRUCE_ID={row['CRUCE_ID']} EMP={row['EMPRESA']} TIPO={row['TIPO']} "
              f"BANCO={row['BANCO']} MONEDA={row['MONEDA']} CARGO={row['CARGO']} ABONO={row['ABONO']} "
              f"ARCHIVO={row['ARCHIVO_ORIGEN']} FILA={row['FILA_ORIGEN']}")

    elapsed = time.time() - t0
    print(f"\n    E2E completado en {elapsed:.1f}s")
    print("=" * 80)


if __name__ == "__main__":
    main()
