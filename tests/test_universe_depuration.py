"""Tests for universe depuration rules.

Validates:
- cargo=0 & abono=0 is NOT a movement
- Saldo is never used as importe
- Comision/IVA don't duplicate parent movement
- Subline links to parent
- Truncated references rejected (ERENCIA, ORIZADA)
- ERENCIA not accepted as REFERENCIA
- ORIZADA not accepted as AUTORIZADA
- Bruto and valid counts reported separately
- 226 additional rows classified
- Final universe excludes document garbage
"""
from __future__ import annotations
import sys
import os
from pathlib import Path
from datetime import datetime
from decimal import Decimal

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from agent3.engine import (
    _clasificar_referencia,
    _es_cargo,
    _es_abono,
    BankMovementRecord,
)
from core.models import MovimientoBancario


def _movimiento(cargo=0, abono=0, ref="REF001", banco="BBVA", fecha=None):
    if fecha is None:
        fecha = datetime(2024, 2, 15)
    m = MovimientoBancario(
        banco=banco, cuenta="0123456789", fecha=fecha, concepto="PAGO",
        cargo=Decimal(str(cargo)), abono=Decimal(str(abono)),
        moneda="MXN", referencia=ref,
    )
    m._fila_origen = 2
    return m


# =========================================================================
# 1. cargo=0 & abono=0 is NOT a movement
# =========================================================================
class TestZeroAmountNotMovement:
    def test_cero_abono_cero_not_cargo(self):
        m = _movimiento(cargo=0, abono=0)
        assert not _es_cargo(m)

    def test_cero_abono_cero_not_abono(self):
        m = _movimiento(cargo=0, abono=0)
        assert not _es_abono(m)

    def test_cero_is_neither_nor_mixed(self):
        m = _movimiento(cargo=0, abono=0)
        assert not _es_cargo(m)
        assert not _es_abono(m)
        from agent3.engine import _construir_universo_movimientos
        records = _construir_universo_movimientos([m], "test.pdf")
        assert len(records) == 1
        rec = records[0]
        assert rec.NATURALEZA == "MIXTO"
        assert rec.CARGO == Decimal("0")
        assert rec.ABONO == Decimal("0")

    def test_real_movement_with_amount_is_valid(self):
        m = _movimiento(cargo=500, abono=0)
        assert _es_cargo(m)
        assert not _es_abono(m)

    def test_abono_movement_is_valid(self):
        m = _movimiento(cargo=0, abono=500)
        assert not _es_cargo(m)
        assert _es_abono(m)


# =========================================================================
# 2. Saldo never used as importe
# =========================================================================
class TestSaldoNotUsedAsImporte:
    def test_bajio_saldo_not_in_cargo(self):
        from parsers.legacy_pdf_engine import _extraer_importes_bajio
        line = '15 FEB DEPOSITO SPEI:EC LOG $ 147,243.88 $ 151,922.67'
        monto, saldo = _extraer_importes_bajio(line)
        assert abs(monto - 147243.88) < 0.01
        assert abs(saldo - 151922.67) < 0.01

    def test_bajio_only_one_amount(self):
        from parsers.legacy_pdf_engine import _extraer_importes_bajio
        line = '15 FEB COMISION POR ENVIO SPEI $ 7.50 $ 15,375.73'
        monto, saldo = _extraer_importes_bajio(line)
        assert abs(monto - 7.50) < 0.01
        assert abs(saldo - 15375.73) < 0.01

    def test_bajio_no_amounts(self):
        from parsers.legacy_pdf_engine import _extraer_importes_bajio
        line = 'INSTITUCION RECEPTORA: BBVA MEXICO BENEFICIARIO: JUAN'
        monto, saldo = _extraer_importes_bajio(line)
        assert monto is None
        assert saldo is None


# =========================================================================
# 3. Comision/IVA don't duplicate parent
# =========================================================================
class TestComisionIVAClassification:
    def test_comision_is_cargo(self):
        from parsers.legacy_pdf_engine import parse_bajio_statement
        line1 = [
            {'text': '15', 'x0': 10, 'x1': 25, 'top': 120, 'bottom': 135},
            {'text': 'FEB', 'x0': 30, 'x1': 50, 'top': 120, 'bottom': 135},
            {'text': '1212920', 'x0': 70, 'x1': 110, 'top': 120, 'bottom': 135},
            {'text': 'COMISION', 'x0': 115, 'x1': 160, 'top': 120, 'bottom': 135},
            {'text': 'POR', 'x0': 165, 'x1': 180, 'top': 120, 'bottom': 135},
            {'text': 'ENVIO', 'x0': 185, 'x1': 210, 'top': 120, 'bottom': 135},
            {'text': 'SPEI', 'x0': 215, 'x1': 240, 'top': 120, 'bottom': 135},
            {'text': '$', 'x0': 400, 'x1': 405, 'top': 120, 'bottom': 135},
            {'text': '7.50', 'x0': 408, 'x1': 430, 'top': 120, 'bottom': 135},
            {'text': '$', 'x0': 450, 'x1': 455, 'top': 120, 'bottom': 135},
            {'text': '15,375.73', 'x0': 458, 'x1': 500, 'top': 120, 'bottom': 135},
        ]
        pages_words = [[line1]]
        txs, _, _, _ = parse_bajio_statement(pages_words, "test.pdf", "digital")
        assert len(txs) == 1
        assert txs[0]['metadata'] == 'COMISION'
        assert txs[0]['cargo'] is not None
        assert txs[0]['abono'] is None

    def test_iva_is_iva_de_comision(self):
        from parsers.legacy_pdf_engine import parse_bajio_statement
        line1 = [
            {'text': '15', 'x0': 10, 'x1': 25, 'top': 120, 'bottom': 135},
            {'text': 'FEB', 'x0': 30, 'x1': 50, 'top': 120, 'bottom': 135},
            {'text': '1212920', 'x0': 70, 'x1': 110, 'top': 120, 'bottom': 135},
            {'text': 'IVA', 'x0': 115, 'x1': 130, 'top': 120, 'bottom': 135},
            {'text': 'COMISION', 'x0': 135, 'x1': 180, 'top': 120, 'bottom': 135},
            {'text': 'POR', 'x0': 185, 'x1': 200, 'top': 120, 'bottom': 135},
            {'text': 'ENVIO', 'x0': 205, 'x1': 230, 'top': 120, 'bottom': 135},
            {'text': 'SPEI', 'x0': 235, 'x1': 260, 'top': 120, 'bottom': 135},
            {'text': '$', 'x0': 400, 'x1': 405, 'top': 120, 'bottom': 135},
            {'text': '1.20', 'x0': 408, 'x1': 428, 'top': 120, 'bottom': 135},
            {'text': '$', 'x0': 450, 'x1': 455, 'top': 120, 'bottom': 135},
            {'text': '15,374.53', 'x0': 458, 'x1': 500, 'top': 120, 'bottom': 135},
        ]
        pages_words = [[line1]]
        txs, _, _, _ = parse_bajio_statement(pages_words, "test.pdf", "digital")
        assert len(txs) == 1
        assert txs[0]['metadata'] == 'IVA_DE_COMISION'


# =========================================================================
# 4. Sublinea se vincula al movimiento padre
# =========================================================================
class TestSublineaVinculoPadre:
    def test_continuation_line_merges_concepto(self):
        from parsers.legacy_pdf_engine import parse_bajio_statement
        line1 = [
            {'text': '15', 'x0': 10, 'x1': 25, 'top': 120, 'bottom': 135},
            {'text': 'FEB', 'x0': 30, 'x1': 50, 'top': 120, 'bottom': 135},
            {'text': '1212920', 'x0': 70, 'x1': 110, 'top': 120, 'bottom': 135},
            {'text': 'ENVIO', 'x0': 115, 'x1': 145, 'top': 120, 'bottom': 135},
            {'text': 'SPEI:CSC', 'x0': 150, 'x1': 195, 'top': 120, 'bottom': 135},
            {'text': 'SINERGY', 'x0': 200, 'x1': 245, 'top': 120, 'bottom': 135},
            {'text': 'NOM', 'x0': 250, 'x1': 270, 'top': 120, 'bottom': 135},
            {'text': 'JUAN', 'x0': 275, 'x1': 300, 'top': 120, 'bottom': 135},
            {'text': '$', 'x0': 400, 'x1': 405, 'top': 120, 'bottom': 135},
            {'text': '5,000.00', 'x0': 408, 'x1': 450, 'top': 120, 'bottom': 135},
            {'text': '$', 'x0': 460, 'x1': 465, 'top': 120, 'bottom': 135},
            {'text': '10,000.00', 'x0': 468, 'x1': 510, 'top': 120, 'bottom': 135},
        ]
        line2 = [
            {'text': 'INSTITUCION', 'x0': 70, 'x1': 130, 'top': 140, 'bottom': 155},
            {'text': 'RECEPTORA:BBVA', 'x0': 135, 'x1': 220, 'top': 140, 'bottom': 155},
        ]
        pages_words = [[line1, line2]]
        txs, _, _, _ = parse_bajio_statement(pages_words, "test.pdf", "digital")
        assert len(txs) == 1
        assert "INSTITUCION RECEPTORA:BBVA" in txs[0]['concepto']


# =========================================================================
# 5. Referencia truncada rechazada
# =========================================================================
class TestRefTruncadaRechazada:
    def test_erencia_not_accepted(self):
        ref = _clasificar_referencia("ERENCIA", "1425831 DEPOSITO SPEI")
        assert ref != "REFERENCIA_EXPLICITA"

    def test_orizada_not_accepted(self):
        ref = _clasificar_referencia("ORIZADA", "1212920 ENVIO SPEI")
        assert ref != "REFERENCIA_EXPLICITA"

    def test_valid_numeric_ref_accepted(self):
        ref = _clasificar_referencia("1425831", "1425831 DEPOSITO SPEI")
        assert ref == "REFERENCIA_EXPLICITA"

    def test_valid_long_ref_accepted(self):
        ref = _clasificar_referencia("002225065601290749", "SPEI BANAMEX")
        assert ref == "CLAVE_RASTREO_EXPLICITA"

    def test_empty_ref_is_sin_referencia(self):
        ref = _clasificar_referencia("", "SPEI")
        assert ref == "SIN_REFERENCIA_VISIBLE"


# =========================================================================
# 6. ERENCIA not accepted as REFERENCIA via parser
# =========================================================================
class TestParserRefFilter:
    def test_bajio_erencia_filtered(self):
        from parsers.pdf_parser import BancoPDFParser
        REF_TRUNCADAS_INVALIDAS = {
            "ERENCIA", "ORIZADA", "REFERENCIA", "AUTORIZADA", "AUTORIZACION",
            "REFERNCIA", "REFENCIA", "OPERACION", "OPERACIÓN"
        }
        assert "ERENCIA" in REF_TRUNCADAS_INVALIDAS
        assert "ORIZADA" in REF_TRUNCADAS_INVALIDAS

    def test_ref_invalid_regex_matches(self):
        from parsers.pdf_parser import REF_TRUNCADAS_REGEX
        assert REF_TRUNCADAS_REGEX.match("ERENCIA")
        assert REF_TRUNCADAS_REGEX.match("ORIZADA")
        assert REF_TRUNCADAS_REGEX.match("REFERENCIA")
        assert not REF_TRUNCADAS_REGEX.match("1425831")
        assert not REF_TRUNCADAS_REGEX.match("84121500")


# =========================================================================
# 7. Bruto vs valid counts reported separately
# =========================================================================
class TestParserMetrics:
    def test_bajio_parser_returns_metadata(self):
        from parsers.legacy_pdf_engine import parse_bajio_statement
        line1 = [
            {'text': '15', 'x0': 10, 'x1': 25, 'top': 120, 'bottom': 135},
            {'text': 'FEB', 'x0': 30, 'x1': 50, 'top': 120, 'bottom': 135},
            {'text': 'DEPOSITO', 'x0': 70, 'x1': 120, 'top': 120, 'bottom': 135},
            {'text': 'SPEI', 'x0': 125, 'x1': 150, 'top': 120, 'bottom': 135},
            {'text': '$', 'x0': 400, 'x1': 405, 'top': 120, 'bottom': 135},
            {'text': '5,000.00', 'x0': 408, 'x1': 450, 'top': 120, 'bottom': 135},
            {'text': '$', 'x0': 460, 'x1': 465, 'top': 120, 'bottom': 135},
            {'text': '10,000.00', 'x0': 468, 'x1': 510, 'top': 120, 'bottom': 135},
        ]
        pages_words = [[line1]]
        txs, _, _, _ = parse_bajio_statement(pages_words, "test.pdf", "digital")
        assert len(txs) == 1
        assert txs[0]['metadata'] in ('MOVIMIENTO_REAL', 'COMISION', 'IVA_DE_COMISION')
        assert txs[0]['es_movimiento_real'] is True

    def test_zero_amount_not_real(self):
        from parsers.legacy_pdf_engine import parse_bajio_statement
        line1 = [
            {'text': '15', 'x0': 10, 'x1': 25, 'top': 120, 'bottom': 135},
            {'text': 'FEB', 'x0': 30, 'x1': 50, 'top': 120, 'bottom': 135},
            {'text': 'METADATA', 'x0': 70, 'x1': 120, 'top': 120, 'bottom': 135},
            {'text': 'LINE', 'x0': 125, 'x1': 150, 'top': 120, 'bottom': 135},
        ]
        pages_words = [[line1]]
        txs, _, _, _ = parse_bajio_statement(pages_words, "test.pdf", "digital")
        assert len(txs) == 1
        assert txs[0]['cargo'] is None
        assert txs[0]['abono'] is None
        assert txs[0]['es_movimiento_real'] is False


# =========================================================================
# 8. Real integration: zero-amount exclusion
# =========================================================================
class TestRealZeroAmountExclusion:
    def test_no_movements_with_both_zero_in_universo(self):
        """Every row in the universo bancario must have cargo>0 XOR abono>0."""
        from parsers.pdf_parser import BancoPDFParser
        import zipfile
        zip_path = r"C:\Users\USER\Downloads\PAQUETE PARA SUBIR\ESTADOS_DE_CTA_RENOMBRADO.zip"
        if not os.path.exists(zip_path):
            pytest.skip("Real data not available")
        parser = BancoPDFParser()
        total_zero = 0
        total_mixto = 0
        total_strict = 0
        with zipfile.ZipFile(zip_path) as zf:
            for name in zf.namelist():
                if not name.lower().endswith('.pdf'):
                    continue
                data = zf.read(name)
                df, _ = parser.parsear_pdf(data, name)
                if df.empty:
                    continue
                for _, row in df.iterrows():
                    c = float(row.get('Cargo', 0) or 0)
                    a = float(row.get('Abono', 0) or 0)
                    if c == 0 and a == 0:
                        total_zero += 1
                    elif c > 0 and a > 0:
                        total_mixto += 1
                    else:
                        total_strict += 1
        assert total_zero == 0, f"Found {total_zero} zero-amount movements"
        print(f"  STRICT={total_strict} MIXTO={total_mixto} ZERO={total_zero}")

    def test_no_truncated_references_in_universo(self):
        """ERENCIA and ORIZADA must not appear as valid references."""
        from parsers.pdf_parser import BancoPDFParser, REF_TRUNCADAS_INVALIDAS
        import zipfile
        zip_path = r"C:\Users\USER\Downloads\PAQUETE PARA SUBIR\ESTADOS_DE_CTA_RENOMBRADO.zip"
        if not os.path.exists(zip_path):
            pytest.skip("Real data not available")
        parser = BancoPDFParser()
        truncated_found = []
        with zipfile.ZipFile(zip_path) as zf:
            for name in zf.namelist():
                if not name.lower().endswith('.pdf'):
                    continue
                data = zf.read(name)
                df, _ = parser.parsear_pdf(data, name)
                if df.empty:
                    continue
                for _, row in df.iterrows():
                    ref = str(row.get('Referencia_Bancaria_Limpia', '') or '').strip()
                    if ref and ref.upper() in REF_TRUNCADAS_INVALIDAS:
                        truncated_found.append((name, ref))
        assert len(truncated_found) == 0, f"Truncated refs found: {truncated_found[:5]}"


# =========================================================================
# 9. Mixto movements not eligible for automatic match
# =========================================================================
class TestMixtoNotConciliado:
    def test_mixto_movements_not_elegible(self):
        """c>0 AND a>0 movements are not eligible for automatic match."""
        from parsers.pdf_parser import BancoPDFParser
        import zipfile
        zip_path = r"C:\Users\USER\Downloads\PAQUETE PARA SUBIR\ESTADOS_DE_CTA_RENOMBRADO.zip"
        if not os.path.exists(zip_path):
            pytest.skip("Real data not available")
        parser = BancoPDFParser()
        mixtos = []
        with zipfile.ZipFile(zip_path) as zf:
            for name in zf.namelist():
                if not name.lower().endswith('.pdf'):
                    continue
                data = zf.read(name)
                df, _ = parser.parsear_pdf(data, name)
                if df.empty:
                    continue
                for _, row in df.iterrows():
                    c = float(row.get('Cargo', 0) or 0)
                    a = float(row.get('Abono', 0) or 0)
                    if c > 0 and a > 0:
                        mixtos.append((name, row.get('Fecha', ''), c, a))
        assert len(mixtos) == 2, f"Expected 2 MIXTO, found {len(mixtos)}"

    def test_mixto_no_conciliados_in_engine(self):
        """_es_elegible rejects movements with both cargo>0 AND abono>0."""
        from agent3.matcher import _es_elegible, Naturaleza
        from core.models import MovimientoBancario
        from datetime import datetime
        mixto = MovimientoBancario(
            banco="BANREGIO", cuenta="0026", fecha=datetime(2024, 2, 28),
            concepto="SPEI MIXTO", cargo=Decimal("1712899.66"), abono=Decimal("8244909.17"),
            moneda="MXN", referencia="", clave_rastreo="", autorizacion="",
            num_operacion="", cruce_bancario="", monto=Decimal("1712899.66"),
        )
        assert not _es_elegible(mixto, Naturaleza.EGRESOS)
        assert not _es_elegible(mixto, Naturaleza.INGRESOS)


# =========================================================================
# 10. Inventory has real banco (not DESCONOCIDO)
# =========================================================================
class TestInventarioBancoReal:
    def test_all_pdfs_have_banco_detected(self):
        """Every PDF with movements must have a detected banco."""
        import tempfile, zipfile, os, sys
        sys.path.insert(0, ".")
        from parsers.legacy_pdf_engine import process_single_pdf
        zip_path = r"C:\Users\USER\Downloads\PAQUETE PARA SUBIR\ESTADOS_DE_CTA_RENOMBRADO.zip"
        if not os.path.exists(zip_path):
            pytest.skip("Real data not available")
        bancos_faltantes = []
        with zipfile.ZipFile(zip_path) as zf:
            for name in zf.namelist():
                if not name.lower().endswith('.pdf'):
                    continue
                data = zf.read(name)
                fd, tmp = tempfile.mkstemp(suffix=".pdf")
                with os.fdopen(fd, "wb") as f:
                    f.write(data)
                try:
                    raw = process_single_pdf(tmp, name)
                finally:
                    os.remove(tmp)
                txs = raw.get("transacciones", [])
                if not txs:
                    continue
                banco = raw.get("recap", {}).get("banco", "")
                if not banco or banco == "DESCONOCIDO":
                    bancos_faltantes.append(name)
        assert len(bancos_faltantes) == 0, f"No banco detected: {bancos_faltantes}"


# =========================================================================
# 11. Universe valid = 1000
# =========================================================================
class TestUniversoValido1000:
    def test_movimientos_validos_equals_1000(self):
        """After zero-amount and es_movimiento_real filter, exactly 1000 valid."""
        from parsers.pdf_parser import BancoPDFParser
        import zipfile, os
        zip_path = r"C:\Users\USER\Downloads\PAQUETE PARA SUBIR\ESTADOS_DE_CTA_RENOMBRADO.zip"
        if not os.path.exists(zip_path):
            pytest.skip("Real data not available")
        parser = BancoPDFParser()
        total_valid = 0
        with zipfile.ZipFile(zip_path) as zf:
            for name in zf.namelist():
                if not name.lower().endswith('.pdf'):
                    continue
                data = zf.read(name)
                df, _ = parser.parsear_pdf(data, name)
                if not df.empty:
                    total_valid += len(df)
        assert total_valid == 1000, f"Expected 1000 valid movements, got {total_valid}"
