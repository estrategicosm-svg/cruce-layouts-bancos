"""Lee ZIP de estados de cuenta y produce MovimientoBanco."""
from __future__ import annotations

import io
import os
import re
import shutil
import sys
import tempfile
import zipfile
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cruce_layouts_bancos.models import (
    ErrorArchivo,
    MovimientoBanco,
    ResultadoLecturaBanco,
    normalizar_empresa,
    normalizar_banco,
)

TESSERACT_DISPONIBLE = shutil.which("tesseract") is not None

if TESSERACT_DISPONIBLE:
    from parsers.pdf_parser import BancoPDFParser

from parsers.banco_parser import BancoParser


def _extraer_info(nombre: str) -> dict:
    upper = nombre.upper()
    parts = nombre.replace("\\", "/").split("/")
    fname = parts[-1] if parts else nombre
    stem = Path(fname).stem

    empresa = ""
    for p in stem.split("_"):
        if p.upper() in ("CSC", "INTRA", "ICOLD", "TRANS", "TRANSCRUCS", "TRANSCRUCES"):
            empresa = p.upper()
            break

    banco = ""
    for p in stem.split("_"):
        if p.upper() in ("BANAMEX", "BBVA", "BAJIO", "BANREGIO", "IBC", "MONEX", "AMEX"):
            banco = p.upper()
            break

    cuenta = ""
    for p in stem.split("_"):
        if p.upper().startswith("CTA"):
            cuenta = p.upper()
            break

    moneda = ""
    for p in stem.split("_"):
        if p.upper() in ("MXN", "USD", "EUR"):
            moneda = p.upper()
            break

    mes = ""
    for p in stem.split("_"):
        m = re.search(r"(ENE|FEB|MAR|ABR|MAY|JUN|JUL|AGO|SEP|OCT|NOV|DIC)(\d{4})", p.upper())
        if m:
            mes = m.group(0)
            break

    cuenta_ultimos_4 = cuenta.replace("CTA", "")[-4:] if cuenta else ""

    es_tdc = "-TDC" in upper or "_TDC" in upper

    return {
        "empresa": normalizar_empresa(empresa) if empresa else "",
        "banco": banco,
        "cuenta": cuenta,
        "cuenta_ultimos_4": cuenta_ultimos_4,
        "moneda": moneda or "MXN",
        "mes": mes,
        "es_tdc": es_tdc,
    }


def _clasificar_tipo_movimiento(cargo: Decimal, abono: Decimal, concepto: str) -> str:
    concepto_upper = (concepto or "").upper()
    if cargo > 0 and "IVA" in concepto_upper and "COMISION" in concepto_upper:
        return "IVA_COMISION"
    if cargo > 0 and ("COMISION" in concepto_upper or "COMISI" in concepto_upper):
        return "COMISION"
    if cargo > 0:
        return "CARGO"
    if abono > 0:
        return "ABONO"
    return ""


def _procesar_pdf(data: bytes, fname: str, info: dict) -> list[tuple]:
    if not TESSERACT_DISPONIBLE:
        raise RuntimeError(
            f"No fue posible procesar '{fname}' porque falta Tesseract OCR en el servidor. "
            "Instala tesseract-ocr o usa archivos Excel."
        )
    parser = BancoPDFParser()
    df_pdf, validacion = parser.parsear_pdf(data, fname)
    if df_pdf is None or df_pdf.empty:
        advertencias = validacion.get("advertencias", []) if validacion else []
        msg = f"'{fname}': parser devolvió DataFrame vacío"
        if advertencias:
            msg += f" ({'; '.join(advertencias)})"
        raise ValueError(msg)
    return df_pdf, validacion


def _procesar_excel(data: bytes, fname: str, info: dict) -> tuple[list, list[str]]:
    import pandas as pd
    bp = BancoParser()
    df = pd.read_excel(io.BytesIO(data))
    if df.empty:
        return [], [f"'{fname}': archivo Excel vacio o sin datos"]
    movs = bp.parsear_dataframe(df)
    if not movs:
        detail = "; ".join(bp.errores[:5]) if bp.errores else "columnas no reconocidas"
        return [], [
            f"'{fname}': {len(df)} filas leidas, 0 movimientos extraidos ({detail})",
            f"  Columnas encontradas: {list(df.columns)}",
        ]
    if bp.errores:
        return movs, [f"'{fname}': {len(bp.errores)} filas con error de {len(df)} totales: {'; '.join(bp.errores[:3])}"]
    return movs, []


def leer_zip_bancos(zip_bytes: bytes, nombre_zip: str = "ESTADOS.zip") -> ResultadoLecturaBanco:
    resultado = ResultadoLecturaBanco(tesseract_disponible=TESSERACT_DISPONIBLE)
    banco_parser = BancoParser()
    _SYSTEM = {"__MACOSX", ".DS_Store", "Thumbs.db", "__pycache__"}
    movimientos_raw = []

    with tempfile.TemporaryDirectory() as tmpdir:
        zip_path = os.path.join(tmpdir, "estados.zip")
        with open(zip_path, "wb") as f:
            f.write(zip_bytes)

        with zipfile.ZipFile(zip_path) as zf:
            compatible = [
                n for n in zf.namelist()
                if not any(p.startswith(".") or p.startswith("__") or p in _SYSTEM
                           for p in Path(n).parts)
                and not n.endswith("/")
                and any(n.lower().endswith(ext) for ext in (".pdf", ".xlsx", ".xls"))
            ]

            resultado.archivos_totales = len(compatible)

            pdf_files = [n for n in compatible if n.lower().endswith(".pdf")]
            xlsx_files = [n for n in compatible if n.lower().endswith((".xlsx", ".xls"))]
            resultado.archivos_pdf_total = len(pdf_files)

            for name in compatible:
                data = zf.read(name)
                fname = Path(name).name
                ext = Path(name).suffix.lower()
                info = _extraer_info(fname)
                ruta_zip = name

                try:
                    if ext == ".pdf":
                        if not TESSERACT_DISPONIBLE:
                            raise RuntimeError(
                                f"'{fname}': Tesseract OCR no está instalado en el servidor. "
                                "No se puede procesar PDF escaneado. "
                                "Instala tesseract-ocr en packages.txt o usa archivos Excel."
                            )
                        df_pdf, validacion = _procesar_pdf(data, fname, info)
                        movs = banco_parser.parsear_dataframe(df_pdf)
                        for m in movs:
                            movimientos_raw.append((ruta_zip, fname, info, m))
                        resultado.archivos_pdf_ok += 1
                    else:
                        movs, adv = _procesar_excel(data, fname, info)
                        for m in movs:
                            movimientos_raw.append((ruta_zip, fname, info, m))
                        if movs:
                            resultado.archivos_xlsx_ok += 1
                        else:
                            resultado.archivos_xlsx_fallidos += 1
                        for a in adv:
                            resultado.advertencias.append(a)
                except Exception as exc:
                    resultado.archivos_pdf_fallidos += 1 if ext == ".pdf" else 0
                    resultado.errores.append(ErrorArchivo(
                        archivo=fname,
                        tipo="PDF" if ext == ".pdf" else "Excel",
                        error=str(exc),
                    ))

    if not TESSERACT_DISPONIBLE and resultado.archivos_pdf_total > 0:
        resultado.advertencias.append(
            f"Se encontraron {resultado.archivos_pdf_total} archivo(s) PDF en el ZIP "
            "pero Tesseract OCR no está disponible. Los PDFs no fueron procesados."
        )

    if resultado.archivos_totales > 0 and resultado.archivos_xlsx_ok == 0 and resultado.archivos_pdf_ok == 0:
        resultado.advertencias.append(
            "Ningún archivo del ZIP fue procesado exitosamente."
        )

    for ruta_zip, fname, info, m in movimientos_raw:
        cargo = m.cargo if m.cargo else Decimal("0")
        abono = m.abono if m.abono else Decimal("0")
        concepto = str(m.concepto) if m.concepto else ""
        fecha = ""
        if m.fecha:
            try:
                fecha = m.fecha.strftime("%Y-%m-%d")
            except Exception:
                fecha = str(m.fecha)

        resultado.movimientos.append(MovimientoBanco(
            archivo_origen=fname,
            ruta_interna_zip=ruta_zip,
            empresa_detectada=info["empresa"],
            banco_detectado=info["banco"],
            cuenta_detectada=info["cuenta"],
            cuenta_ultimos_4=info["cuenta_ultimos_4"],
            moneda_detectada=info["moneda"],
            mes_detectado=info["mes"],
            fecha_movimiento=fecha,
            descripcion_original=concepto,
            referencia_usada=m.referencia if m.referencia else "",
            clave_rastreo=m.clave_rastreo if m.clave_rastreo else "",
            autorizacion=m.autorizacion if m.autorizacion else "",
            cargo=cargo,
            abono=abono,
            saldo=Decimal("0"),
            tipo_movimiento=_clasificar_tipo_movimiento(cargo, abono, concepto),
            es_tdc=info["es_tdc"],
        ))

    return resultado
