"""Lee ZIP de estados de cuenta y produce MovimientoBanco."""
from __future__ import annotations

import io
import os
import re
import sys
import tempfile
import zipfile
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cruce_layouts_bancos.models import MovimientoBanco, normalizar_empresa, normalizar_banco
from parsers.banco_parser import BancoParser
from parsers.pdf_parser import BancoPDFParser


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


def leer_zip_bancos(zip_bytes: bytes, nombre_zip: str = "ESTADOS.zip") -> list[MovimientoBanco]:
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

            for name in compatible:
                data = zf.read(name)
                fname = Path(name).name
                ext = Path(name).suffix.lower()
                info = _extraer_info(fname)
                ruta_zip = name

                try:
                    if ext == ".pdf":
                        df_pdf, _ = BancoPDFParser().parsear_pdf(data, fname)
                        if df_pdf is not None and not df_pdf.empty:
                            movs = banco_parser.parsear_dataframe(df_pdf)
                            for m in movs:
                                movimientos_raw.append((ruta_zip, fname, info, m))
                    else:
                        import pandas as pd
                        df = pd.read_excel(io.BytesIO(data))
                        movs = banco_parser.parsear_dataframe(df)
                        for m in movs:
                            movimientos_raw.append((ruta_zip, fname, info, m))
                except Exception:
                    pass

    resultado: list[MovimientoBanco] = []
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

        resultado.append(MovimientoBanco(
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
