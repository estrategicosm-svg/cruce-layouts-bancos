"""Tests for cedula layout parsers (egresos + ingresos) with official layouts.

Covers all 9 requirements from the dictamen:
1. Detect layout of egresos
2. Detect layout of ingresos
3. Detect header in row 2
4. Read all rows of egresos
5. Read all rows of ingresos
6. Don't require literal 'importe' column
7. Egresos uses FECHA_PAGO
8. Ingresos uses FECHA_COBRO
9. MXN uses TOTAL_PESOS, USD uses TOTAL_DLS
10. Preserve POLIZA, UUID, EMPRESA
11. Readable error if missing real column
"""
from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pandas as pd
import pytest

from parsers.cedula_parser import CedulaParser
from parsers.cedula_ingresos_parser import CedulaIngresosParser
from parsers.layout_detector import (
    LayoutType,
    detectar_layout,
    _detect_layout_by_columns,
    _find_header_row,
)

ASSETS = Path(__file__).parent.parent / "assets" / "plantillas"
LAYOUT_EGRESOS = ASSETS / "LAYOUT_CARGA_EGRESOS.xlsx"
LAYOUT_INGRESOS = ASSETS / "LAYOUT_CEDULA_INGRESOS.xlsx"


# =========================================================================
# 1. Layout Detection
# =========================================================================
class TestLayoutDetection:
    def test_detect_egresos_by_columns(self):
        """EGRESOS layout detected by FECHA_PAGO + PROVEEDOR columns."""
        cols = ["EMPRESA", "POLIZA", "UUID", "RFC_PROVEEDOR", "PROVEEDOR",
                "FECHA_FACTURA", "FECHA_PAGO", "MONEDA", "TOTAL PESOS", "TOTAL DLS", "BANCO"]
        assert _detect_layout_by_columns(cols) == LayoutType.EGRESOS

    def test_detect_ingresos_by_columns(self):
        """INGRESOS layout detected by FECHA_COBRO + CLIENTE columns."""
        cols = ["EMPRESA", "POLIZA", "UUID", "RFC_CLIENTE", "CLIENTE",
                "FECHA_FACTURA", "FECHA_COBRO", "MONEDA", "TOTAL PESOS", "TOTAL DLS", "BANCO"]
        assert _detect_layout_by_columns(cols) == LayoutType.INGRESOS

    def test_detect_unknown_columns(self):
        """Unknown layout returns DESCONOCIDO."""
        cols = ["A", "B", "C"]
        assert _detect_layout_by_columns(cols) == LayoutType.DESCONOCIDO

    def test_detect_header_row_skips_numeric(self):
        """Header row detection skips numeric row 1 in official layouts."""
        raw = pd.read_excel(LAYOUT_EGRESOS, header=None, nrows=10)
        header_idx = _find_header_row(raw)
        assert header_idx == 1, f"Expected header at row 1, got {header_idx}"


# =========================================================================
# 2. Official Layout - Egresos
# =========================================================================
class TestLayoutEgresosOficial:
    def test_detect_layout_type(self):
        """Layout EGRESOS detected from official file."""
        with open(LAYOUT_EGRESOS, "rb") as f:
            det = detectar_layout(f, "EGRESOS")
        assert det.layout_type == LayoutType.EGRESOS
        assert det.header_row == 1
        assert det.columns_recognized == 11
        assert len(det.missing_required) == 0

    def test_read_all_rows(self):
        """Reads all 756 data rows from official EGRESOS layout."""
        parser = CedulaParser()
        with open(LAYOUT_EGRESOS, "rb") as f:
            regs = parser.parsear_excel(f, "EGRESOS")
        assert len(regs) == 756
        assert len(parser.errores) == 0

    def test_empresa_preserved(self):
        """EMPRESA field preserved from layout."""
        parser = CedulaParser()
        with open(LAYOUT_EGRESOS, "rb") as f:
            regs = parser.parsear_excel(f, "EGRESOS")
        empresas = {r.empresa for r in regs if r.empresa}
        assert len(empresas) > 0
        assert any(e.lower() in ("intra", "csc", "icold", "transtruces") for e in empresas)

    def test_poliza_preserved(self):
        """POLIZA field preserved from layout."""
        parser = CedulaParser()
        with open(LAYOUT_EGRESOS, "rb") as f:
            regs = parser.parsear_excel(f, "EGRESOS")
        polizas = [r.poliza for r in regs if r.poliza]
        assert len(polizas) > 0
        assert all("/" in p for p in polizas[:5])

    def test_uuid_preserved(self):
        """UUID field preserved and normalized."""
        parser = CedulaParser()
        with open(LAYOUT_EGRESOS, "rb") as f:
            regs = parser.parsear_excel(f, "EGRESOS")
        uuids = [r.uuid for r in regs if r.uuid]
        assert len(uuids) > 0
        assert all(len(u) == 36 and u.count("-") == 4 for u in uuids[:5])

    def test_fecha_pago_used(self):
        """EGRESOS uses FECHA_PAGO as fecha_operacion."""
        parser = CedulaParser()
        with open(LAYOUT_EGRESOS, "rb") as f:
            regs = parser.parsear_excel(f, "EGRESOS")
        fechas = [r.fecha_pago for r in regs]
        validas = [f for f in fechas if f.year >= 2024]
        assert len(validas) > 0, "Expected valid dates from FECHA_PAGO"

    def test_importe_not_required(self):
        """No literal 'importe' column needed; TOTAL PESOS is used."""
        parser = CedulaParser()
        with open(LAYOUT_EGRESOS, "rb") as f:
            regs = parser.parsear_excel(f, "EGRESOS")
        importes = [r.importe for r in regs]
        assert all(i > 0 for i in importes[:5])

    def test_mxn_uses_total_pesos(self):
        """MXN records use TOTAL PESOS for importe."""
        parser = CedulaParser()
        with open(LAYOUT_EGRESOS, "rb") as f:
            regs = parser.parsear_excel(f, "EGRESOS")
        mxn = [r for r in regs if r.moneda.upper() == "MXN"]
        assert len(mxn) > 0
        assert all(r.importe > 0 for r in mxn[:5])


# =========================================================================
# 3. Official Layout - Ingresos
# =========================================================================
class TestLayoutIngresosOficial:
    def test_detect_layout_type(self):
        """Layout INGRESOS detected from official file."""
        with open(LAYOUT_INGRESOS, "rb") as f:
            det = detectar_layout(f, "INGRESOS")
        assert det.layout_type == LayoutType.INGRESOS
        assert det.header_row == 1
        assert det.columns_recognized == 11
        assert len(det.missing_required) == 0

    def test_read_all_rows(self):
        """Reads all 2235 data rows from official INGRESOS layout."""
        parser = CedulaIngresosParser()
        with open(LAYOUT_INGRESOS, "rb") as f:
            regs = parser.parsear_excel(f, "INGRESOS")
        assert len(regs) == 2235
        assert len(parser.errores) == 0

    def test_empresa_preserved(self):
        """EMPRESA field preserved from layout."""
        parser = CedulaIngresosParser()
        with open(LAYOUT_INGRESOS, "rb") as f:
            regs = parser.parsear_excel(f, "INGRESOS")
        empresas = {r.descripcion for r in regs if r.descripcion}
        assert len(empresas) > 0

    def test_poliza_preserved(self):
        """POLIZA (as factura) field preserved from layout."""
        parser = CedulaIngresosParser()
        with open(LAYOUT_INGRESOS, "rb") as f:
            regs = parser.parsear_excel(f, "INGRESOS")
        facturas = [r.factura for r in regs if r.factura]
        assert len(facturas) > 0

    def test_uuid_preserved(self):
        """UUID field preserved and normalized."""
        parser = CedulaIngresosParser()
        with open(LAYOUT_INGRESOS, "rb") as f:
            regs = parser.parsear_excel(f, "INGRESOS")
        uuids = [r.uuid for r in regs if r.uuid]
        assert len(uuids) > 0
        assert all(len(u) == 36 and u.count("-") == 4 for u in uuids[:5])

    def test_fecha_cobro_used(self):
        """INGRESOS uses FECHA_COBRO as fecha_operacion."""
        parser = CedulaIngresosParser()
        with open(LAYOUT_INGRESOS, "rb") as f:
            regs = parser.parsear_excel(f, "INGRESOS")
        fechas = [r.fecha for r in regs]
        validas = [f for f in fechas if f.year >= 2024]
        assert len(validas) > 0, "Expected valid dates from FECHA_COBRO"

    def test_usd_uses_total_dls(self):
        """USD records use TOTAL DLS for total."""
        parser = CedulaIngresosParser()
        with open(LAYOUT_INGRESOS, "rb") as f:
            regs = parser.parsear_excel(f, "INGRESOS")
        usd = [r for r in regs if r.moneda.upper() == "USD"]
        assert len(usd) > 0
        assert all(r.amount_usd > 0 for r in usd[:5])

    def test_mxn_uses_total_pesos(self):
        """MXN records use TOTAL PESOS for total."""
        parser = CedulaIngresosParser()
        with open(LAYOUT_INGRESOS, "rb") as f:
            regs = parser.parsear_excel(f, "INGRESOS")
        mxn = [r for r in regs if r.moneda.upper() == "MXN"]
        assert len(mxn) > 0
        assert all(r.amount_mxn > 0 for r in mxn[:5])


# =========================================================================
# 4. Error handling
# =========================================================================
class TestErrorHandling:
    def test_missing_columns_readable_error(self):
        """Error message includes layout type and missing columns."""
        parser = CedulaIngresosParser()
        df = pd.DataFrame([{"Cliente": "X"}])
        with pytest.raises(ValueError, match="columnas requeridas no encontradas"):
            parser.parsear_dataframe(df)

    def test_empty_dataframe_error(self):
        """Empty DataFrame raises appropriate error."""
        parser = CedulaParser()
        df = pd.DataFrame()
        with pytest.raises(ValueError):
            parser.parsear_dataframe(df)


# =========================================================================
# 5. App-level integration
# =========================================================================
class TestAppIntegration:
    def test_egresos_feeds_conciliador(self):
        """Egresos parser output feeds into Conciliador without error."""
        from conciliacion.conciliador import Conciliador
        parser = CedulaParser()
        with open(LAYOUT_EGRESOS, "rb") as f:
            regs = parser.parsear_excel(f, "EGRESOS")
        conciliador = Conciliador()
        resultado = conciliador.conciliar(regs, [], [])
        assert resultado.total_registros == 756
        assert len(resultado.errores) == 0

    def test_ingresos_feeds_conciliador_ingresos(self):
        """Ingresos parser output feeds into ConciliadorIngresos without error."""
        from conciliacion.conciliador_ingresos import ConciliadorIngresos
        parser = CedulaIngresosParser()
        with open(LAYOUT_INGRESOS, "rb") as f:
            regs = parser.parsear_excel(f, "INGRESOS")
        conciliador = ConciliadorIngresos()
        resultado = conciliador.conciliar(regs, [], [])
        assert resultado.total_registros == 2235
        assert len(resultado.errores) == 0
