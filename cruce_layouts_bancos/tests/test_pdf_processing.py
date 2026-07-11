"""Pruebas para procesamiento PDF y manejo de errores de archivos."""
from __future__ import annotations

import io
import shutil
import tempfile
import zipfile
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock, patch

from cruce_layouts_bancos.models import (
    ErrorArchivo,
    MovimientoBanco,
    ResultadoLecturaBanco,
)
from cruce_layouts_bancos.bank_reader import (
    TESSERACT_DISPONIBLE,
    _extraer_info,
    _clasificar_tipo_movimiento,
    leer_zip_bancos,
)


class TestTesseractDetection:
    def test_tesseract_var_is_boolean(self):
        assert isinstance(TESSERACT_DISPONIBLE, bool)

    def test_tesseract_detected_when_binary_exists(self):
        assert TESSERACT_DISPONIBLE == (shutil.which("tesseract") is not None)


class TestExtraerInfo:
    def test_empresa_from_filename(self):
        info = _extraer_info("INTRA_BANAMEX_CTA0688_MXN_FEB2024.pdf")
        assert info["empresa"] == "INTRA"

    def test_empresa_csc(self):
        info = _extraer_info("CSC_BBVA_CTA1234_MXN_ENE2024.pdf")
        assert info["empresa"] == "CSC"

    def test_empresa_transscruc_es_trans(self):
        info = _extraer_info("TRANSCRUCES_BANREGIO_CTA5678_MXN_MAR2024.pdf")
        assert info["empresa"] == "TRANS"

    def test_banco_from_filename(self):
        info = _extraer_info("INTRA_BBVA_CTA0688_MXN_FEB2024.pdf")
        assert info["banco"] == "BBVA"

    def test_moneda_default_mxn(self):
        info = _extraer_info("INTRA_BANAMEX_CTA0688_FEB2024.pdf")
        assert info["moneda"] == "MXN"

    def test_moneda_usd(self):
        info = _extraer_info("INTRA_BANAMEX_CTA0688_USD_FEB2024.pdf")
        assert info["moneda"] == "USD"

    def test_es_tdc_hyphen(self):
        info = _extraer_info("INTRA_BANAMEX-TDC_CTA0688_MXN_FEB2024.pdf")
        assert info["es_tdc"] is True

    def test_es_tdc_underscore(self):
        info = _extraer_info("INTRA_BANAMEX_TDC_CTA0688_MXN_FEB2024.pdf")
        assert info["es_tdc"] is True

    def test_no_es_tdc(self):
        info = _extraer_info("INTRA_BANAMEX_CTA0688_MXN_FEB2024.pdf")
        assert info["es_tdc"] is False


class TestClasificarMovimiento:
    def test_cargo(self):
        assert _clasificar_tipo_movimiento(Decimal("100"), Decimal("0"), "PAGO") == "CARGO"

    def test_abono(self):
        assert _clasificar_tipo_movimiento(Decimal("0"), Decimal("100"), "DEPOSITO") == "ABONO"

    def test_comision(self):
        assert _clasificar_tipo_movimiento(Decimal("50"), Decimal("0"), "COMISION BANCARIA") == "COMISION"

    def test_iva_comision(self):
        assert _clasificar_tipo_movimiento(Decimal("10"), Decimal("0"), "IVA POR COMISION") == "IVA_COMISION"

    def test_vacio(self):
        assert _clasificar_tipo_movimiento(Decimal("0"), Decimal("0"), "") == ""


class TestResultadoLecturaBanco:
    def test_default_values(self):
        r = ResultadoLecturaBanco()
        assert r.movimientos == []
        assert r.archivos_totales == 0
        assert r.archivos_pdf_ok == 0
        assert r.archivos_pdf_fallidos == 0
        assert r.errores == []
        assert r.advertencias == []
        assert r.tesseract_disponible is False

    def test_error_archivo_dataclass(self):
        e = ErrorArchivo(archivo="test.pdf", tipo="PDF", error="timeout")
        assert e.archivo == "test.pdf"
        assert e.tipo == "PDF"
        assert e.error == "timeout"


class TestLeerZipSinPDFs:
    def test_zip_vacio(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("dummy.txt", "not a bank file")
        buf.seek(0)
        r = leer_zip_bancos(buf.getvalue(), "vacio.zip")
        assert r.archivos_totales == 0
        assert r.movimientos == []

    def _make_excel_bytes(self, df) -> bytes:
        out = io.BytesIO()
        df.to_excel(out, index=False)
        return out.getvalue()

    def test_zip_con_excel(self):
        import pandas as pd
        df = pd.DataFrame({
            "Fecha": ["2024-02-15"],
            "Concepto": ["PAGO PROVEEDOR"],
            "Cargo": [1000],
            "Abono": [0],
            "Referencia": ["REF001"],
        })
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("INTRA_BANAMEX_CTA0688_MXN_FEB2024.xlsx", self._make_excel_bytes(df))
        buf.seek(0)
        r = leer_zip_bancos(buf.getvalue(), "test.zip")
        assert r.archivos_xlsx_ok == 1
        assert r.archivos_pdf_total == 0
        assert len(r.errores) == 0


class TestLeerZipConPDFs:
    @patch("cruce_layouts_bancos.bank_reader.TESSERACT_DISPONIBLE", False)
    def test_pdf_sin_tesseract_genera_error(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("INTRA_BANAMEX_CTA0688_MXN_FEB2024.pdf", b"%PDF-fake")
        buf.seek(0)
        r = leer_zip_bancos(buf.getvalue(), "test.zip")
        assert r.archivos_pdf_total == 1
        assert r.archivos_pdf_fallidos == 1
        assert len(r.errores) == 1
        assert "Tesseract" in r.errores[0].error

    @patch("cruce_layouts_bancos.bank_reader.TESSERACT_DISPONIBLE", False)
    def test_pdf_sin_tesseract_genera_advertencia(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("INTRA_BANAMEX_CTA0688_MXN_FEB2024.pdf", b"%PDF-fake")
        buf.seek(0)
        r = leer_zip_bancos(buf.getvalue(), "test.zip")
        assert len(r.advertencias) >= 1
        assert any("Tesseract" in a for a in r.advertencias)

    @patch("cruce_layouts_bancos.bank_reader.TESSERACT_DISPONIBLE", False)
    def test_pdf_sin_tesseract_no_oeulta_exito(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("INTRA_BANAMEX_CTA0688_MXN_FEB2024.pdf", b"%PDF-fake")
        buf.seek(0)
        r = leer_zip_bancos(buf.getvalue(), "test.zip")
        assert r.archivos_pdf_ok == 0


class TestLeerZipCombinado:
    @patch("cruce_layouts_bancos.bank_reader.TESSERACT_DISPONIBLE", False)
    def test_excel_ok_y_pdf_fallido(self):
        import pandas as pd
        df = pd.DataFrame({
            "Fecha": ["2024-02-15"],
            "Concepto": ["PAGO PROVEEDOR"],
            "Cargo": [1000],
            "Abono": [0],
            "Referencia": ["REF001"],
        })
        out = io.BytesIO()
        df.to_excel(out, index=False)
        xlsx_bytes = out.getvalue()
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("INTRA_BANAMEX_CTA0688_MXN_FEB2024.xlsx", xlsx_bytes)
            zf.writestr("CSC_BBVA_CTA1234_MXN_ENE2024.pdf", b"%PDF-fake")
        buf.seek(0)
        r = leer_zip_bancos(buf.getvalue(), "test.zip")
        assert r.archivos_xlsx_ok == 1
        assert r.archivos_pdf_fallidos == 1
        assert len(r.movimientos) >= 1

    @patch("cruce_layouts_bancos.bank_reader.TESSERACT_DISPONIBLE", False)
    def test_todos_los_archivos_fallan(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("INTRA_BANAMEX_CTA0688_MXN_FEB2024.pdf", b"%PDF-fake")
            zf.writestr("CSC_BBVA_CTA1234_MXN_ENE2024.pdf", b"%PDF-fake")
        buf.seek(0)
        r = leer_zip_bancos(buf.getvalue(), "test.zip")
        assert r.archivos_pdf_fallidos == 2
        assert r.archivos_pdf_ok == 0
        assert r.archivos_xlsx_ok == 0
        assert len(r.errores) == 2


class TestLeerZipMarcadores:
    @patch("cruce_layouts_bancos.bank_reader.TESSERACT_DISPONIBLE", False)
    def test_archivos_totales_cuenta_correctamente(self):
        import pandas as pd
        df = pd.DataFrame({
            "Fecha": ["2024-02-15"],
            "Concepto": ["PAGO PROVEEDOR"],
            "Cargo": [1000],
            "Abono": [0],
            "Referencia": ["REF001"],
        })
        out = io.BytesIO()
        df.to_excel(out, index=False)
        xlsx_bytes = out.getvalue()
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("INTRA.xlsx", xlsx_bytes)
            zf.writestr("CSC.pdf", b"%PDF-fake")
            zf.writestr("TRANS.xlsx", xlsx_bytes)
        buf.seek(0)
        r = leer_zip_bancos(buf.getvalue(), "test.zip")
        assert r.archivos_totales == 3
        assert r.archivos_xlsx_ok == 2
        assert r.archivos_pdf_total == 1
        assert r.archivos_pdf_fallidos == 1

    def test_tesseract_disponible_se_registra(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("dummy.txt", "skip")
        buf.seek(0)
        r = leer_zip_bancos(buf.getvalue(), "test.zip")
        assert r.tesseract_disponible == TESSERACT_DISPONIBLE


class TestAppNoImportaXML:
    def test_bank_reader_no_importa_xml(self):
        import cruce_layouts_bancos.bank_reader as mod
        source = open(mod.__file__).read()
        assert "xml_parser" not in source.lower()
        assert "CFDI" not in source

    def test_app_modulo_no_importa_xml(self):
        import cruce_layouts_bancos.app as mod
        source = open(mod.__file__).read()
        assert "xml" not in source.lower()
        assert "CFDI" not in source
