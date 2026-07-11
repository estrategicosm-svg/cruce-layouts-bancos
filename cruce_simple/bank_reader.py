"""Lee ZIP de estados de cuenta y produce MovimientoBanco."""
from __future__ import annotations

import io
import os
import sys
import tempfile
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cruce_simple.models import MovimientoBanco, normalizar_empresa, normalizar_banco
from parsers.banco_parser import BancoParser
from parsers.pdf_parser import BancoPDFParser


def _extraer_info_archivo(nombre: str) -> dict:
    upper = nombre.upper()
    parts = nombre.replace("\\", "/").split("/")
    fname = parts[-1] if parts else nombre
    stem = Path(fname).stem

    empresa = ""
    for part in stem.split("_"):
        clean = part.upper().strip()
        if clean in ("CSC", "INTRA", "ICOLD", "TRANS", "TRANSCRUCES"):
            empresa = clean
            break

    banco = ""
    for part in stem.split("_"):
        clean = part.upper().strip()
        if clean in ("BANAMEX", "BBVA", "BAJIO", "BANREGIO", "IBC", "MONEX", "AMEX", "BANCO"):
            banco = clean
            break

    cuenta = ""
    for part in stem.split("_"):
        if part.upper().startswith("CTA"):
            cuenta = part
            break

    moneda = ""
    for part in stem.split("_"):
        if part.upper() in ("MXN", "USD", "EUR"):
            moneda = part.upper()
            break

    es_tdc = "-TDC" in upper or "_TDC" in upper or "TARJETA" in upper

    return {
        "empresa": normalizar_empresa(empresa) if empresa else "",
        "banco": normalizar_banco(banco) if banco else "",
        "cuenta": cuenta,
        "moneda": moneda or "MXN",
        "es_tdc": es_tdc,
    }


def leer_zip_bancos(zip_bytes: bytes, nombre_zip: str = "ESTADOS.zip") -> list[MovimientoBanco]:
    movimientos: list[MovimientoBanco] = []
    banco_parser = BancoParser()

    _SYSTEM = {"__MACOSX", ".DS_Store", "Thumbs.db", "__pycache__"}

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
                info = _extraer_info_archivo(fname)

                try:
                    if ext == ".pdf":
                        df_pdf, _ = BancoPDFParser().parsear_pdf(data, fname)
                        if df_pdf is not None and not df_pdf.empty:
                            movs = banco_parser.parsear_dataframe(df_pdf)
                            for mv in movs:
                                mv._archivo_origen = fname
                                mv._info_archivo = info
                            movimientos.extend(movs)
                    else:
                        import pandas as pd
                        df = pd.read_excel(io.BytesIO(data))
                        movs = banco_parser.parsear_dataframe(df)
                        for mv in movs:
                            mv._archivo_origen = fname
                            mv._info_archivo = info
                        movimientos.extend(movs)
                except Exception:
                    pass

    resultado: list[MovimientoBanco] = []
    for m in movimientos:
        info = getattr(m, "_info_archivo", {})
        archivo = getattr(m, "_archivo_origen", nombre_zip)
        resultado.append(MovimientoBanco(
            archivo=archivo,
            empresa=info.get("empresa", ""),
            banco=info.get("banco", ""),
            cuenta=info.get("cuenta", ""),
            moneda=info.get("moneda", str(m.moneda) if m.moneda else "MXN"),
            fecha=str(m.fecha.strftime("%Y-%m-%d")) if m.fecha else "",
            concepto=str(m.concepto) if m.concepto else "",
            cargo=m.cargo if m.cargo else __import__("decimal").Decimal("0"),
            abono=m.abono if m.abono else __import__("decimal").Decimal("0"),
            referencia=m.referencia if m.referencia else "",
            es_tdc=info.get("es_tdc", False),
        ))

    return resultado
