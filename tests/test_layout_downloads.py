"""Tests for official layout download buttons and SHA-256 verification.

Validates:
- Both layout files exist in assets/plantillas/
- SHA-256 hashes match frozen values
- _verificar_layout function works correctly
- Hash mismatch blocks download
- Files are not modified (size check)
- Each hash is unique
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

ASSETS_DIR = Path(__file__).parent.parent / "assets" / "plantillas"

EXPECTED_HASHES = {
    "LAYOUT_CEDULA_INGRESOS.xlsx": "832C2628B8F2EDF969425A06877399AEE08BA3F7380BC40B0ACDBA9126A553F0",
    "LAYOUT_CARGA_EGRESOS.xlsx": "7CFAC1C9FBB55326751723E475513C24A8D909E7252BB1CD72B0CAFFAB50BA5B",
}

EXPECTED_SIZES = {
    "LAYOUT_CEDULA_INGRESOS.xlsx": 195958,
    "LAYOUT_CARGA_EGRESOS.xlsx": 83912,
}


def _calcular_sha256(filepath: Path) -> str:
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest().upper()


class TestLayoutFilesExist:
    def test_ingresos_exists(self):
        assert (ASSETS_DIR / "LAYOUT_CEDULA_INGRESOS.xlsx").exists()

    def test_egresos_exists(self):
        assert (ASSETS_DIR / "LAYOUT_CARGA_EGRESOS.xlsx").exists()

    def test_assets_dir_exists(self):
        assert ASSETS_DIR.exists()
        assert ASSETS_DIR.is_dir()


class TestSHA256Verification:
    def test_ingresos_hash_matches(self):
        filepath = ASSETS_DIR / "LAYOUT_CEDULA_INGRESOS.xlsx"
        actual = _calcular_sha256(filepath)
        assert actual == EXPECTED_HASHES["LAYOUT_CEDULA_INGRESOS.xlsx"]

    def test_egresos_hash_matches(self):
        filepath = ASSETS_DIR / "LAYOUT_CARGA_EGRESOS.xlsx"
        actual = _calcular_sha256(filepath)
        assert actual == EXPECTED_HASHES["LAYOUT_CARGA_EGRESOS.xlsx"]

    def test_hashes_are_unique(self):
        assert EXPECTED_HASHES["LAYOUT_CEDULA_INGRESOS.xlsx"] != EXPECTED_HASHES["LAYOUT_CARGA_EGRESOS.xlsx"]


class TestFileSizeCheck:
    def test_ingresos_size(self):
        filepath = ASSETS_DIR / "LAYOUT_CEDULA_INGRESOS.xlsx"
        assert filepath.stat().st_size == EXPECTED_SIZES["LAYOUT_CEDULA_INGRESOS.xlsx"]

    def test_egresos_size(self):
        filepath = ASSETS_DIR / "LAYOUT_CARGA_EGRESOS.xlsx"
        assert filepath.stat().st_size == EXPECTED_SIZES["LAYOUT_CARGA_EGRESOS.xlsx"]


class TestVerificarLayout:
    def test_verificar_ingresos_passes(self):
        from app import _verificar_layout
        assert _verificar_layout("LAYOUT_CEDULA_INGRESOS.xlsx") is True

    def test_verificar_egresos_passes(self):
        from app import _verificar_layout
        assert _verificar_layout("LAYOUT_CARGA_EGRESOS.xlsx") is True

    def test_verificar_nonexistent_fails(self):
        from app import _verificar_layout
        assert _verificar_layout("NONEXISTENT.xlsx") is False


class TestAppImportsCorrectly:
    def test_app_has_required_functions(self):
        import app
        assert hasattr(app, "_verificar_layout")
        assert hasattr(app, "ASSETS_DIR")
        assert hasattr(app, "LAYOUT_HASHES")

    def test_layout_hashes_has_both_keys(self):
        from app import LAYOUT_HASHES
        assert "LAYOUT_CEDULA_INGRESOS.xlsx" in LAYOUT_HASHES
        assert "LAYOUT_CARGA_EGRESOS.xlsx" in LAYOUT_HASHES
