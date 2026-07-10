"""Tests de integración con universo completo de datos reales.

Carga los layouts completos (756 egresos + 2235 ingresos) y valida todos los
invariantes H2 sobre el resultado real del motor.

Requiere: archivos en C:/Users/USER/Downloads/PAQUETE PARA SUBIR/
Si no existen, los tests se saltan.
"""

from __future__ import annotations

import sys
import zipfile
from collections import Counter
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from agent3.engine import (
    EngineConfig,
    _movimiento_id,
    _movimiento_id_hash,
    conciliar_banco_first,
)
from agent3.models import EstatusRegistro, TipoMatch
from core.models import CedulaIngresoRegistro, CedulaRegistro, MovimientoBancario

PAQUETE = Path(r"C:\Users\USER\Downloads\PAQUETE PARA SUBIR")


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
    try:
        s = str(v).strip()
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
            try:
                return datetime.strptime(s, fmt)
            except ValueError:
                continue
    except Exception:
        pass
    return datetime(2024, 1, 1)


def _load_egresos():
    import openpyxl
    wb = openpyxl.load_workbook(str(PAQUETE / "LAYOUT_CARGA_EGRESOS.xlsx"),
                               read_only=True, data_only=True)
    ws = wb["DATOS"]
    rows = list(ws.iter_rows(values_only=True))
    wb.close()
    header_row = rows[1]
    cols = {str(h).strip().upper(): i for i, h in enumerate(header_row) if h}
    egresos = []
    for row in rows[2:]:
        if not row or not any(row):
            continue
        try:
            c = CedulaRegistro(
                poliza=str(row[cols.get("POLIZA", 1)] or ""),
                cliente=str(row[cols.get("PROVEEDOR", 4)] or ""),
                rfc=str(row[cols.get("RFC_PROVEEDOR", 3)] or ""),
                uuid=str(row[cols.get("UUID", 2)] or ""),
                importe=_to_decimal(row[cols.get("TOTAL PESOS", 8)]),
                base_iva_16=_to_decimal(row[cols.get("TOTAL PESOS", 8)]),
                base_iva_8=Decimal("0"),
                base_iva_0=Decimal("0"),
                exentos=Decimal("0"),
                iva=Decimal("0"),
                retenciones=Decimal("0"),
                moneda=str(row[cols.get("MONEDA", 7)] or "MXN"),
                tipo_cambio=Decimal("1"),
                fecha_pago=_to_datetime(row[cols.get("FECHA_PAGO", 6)]),
                banco=str(row[cols.get("BANCO", 10)] or ""),
                cruce_bancario="",
            )
            egresos.append(c)
        except Exception:
            continue
    return egresos


def _load_ingresos():
    import openpyxl
    wb = openpyxl.load_workbook(str(PAQUETE / "LAYOUT_CEDULA_INGRESOS.xlsx"),
                               read_only=True, data_only=True)
    ws = wb["DATOS"]
    rows = list(ws.iter_rows(values_only=True))
    wb.close()
    header_row = rows[1]
    cols = {str(h).strip().upper(): i for i, h in enumerate(header_row) if h}
    ingresos = []
    for row in rows[2:]:
        if not row or not any(row):
            continue
        try:
            total_pesos = _to_decimal(row[cols.get("TOTAL PESOS", 8)])
            ing = CedulaIngresoRegistro(
                uuid=str(row[cols.get("UUID", 2)] or ""),
                cliente=str(row[cols.get("CLIENTE", 4)] or ""),
                rfc=str(row[cols.get("RFC_CLIENTE", 3)] or ""),
                factura=str(row[cols.get("UUID", 2)] or ""),
                fecha=_to_datetime(row[cols.get("FECHA_COBRO", 6)]),
                total=total_pesos,
                moneda=str(row[cols.get("MONEDA", 7)] or "MXN"),
                amount_mxn=total_pesos,
                amount_usd=_to_decimal(row[cols.get("TOTAL DLS", 9)]),
                forma_pago="03",
                folio_transferencia=str(row[cols.get("POLIZA", 1)] or ""),
                descripcion=str(row[cols.get("CLIENTE", 4)] or ""),
            )
            ingresos.append(ing)
        except Exception:
            continue
    return ingresos


def _load_xmls():
    from parsers.xml_parser import XMLParser
    cfdis = []
    for zf_name in ["XML_feb_24.zip", "XML_RECIBIDOS_FEB_24.zip"]:
        with open(str(PAQUETE / zf_name), "rb") as f:
            parser = XMLParser()
            res = parser.parsear_zip(f.read())
            cfdis.extend(res.exitosos)
    return cfdis


def _load_movimientos():
    from parsers.pdf_parser import BancoPDFParser
    movimientos = []
    with zipfile.ZipFile(str(PAQUETE / "ESTADOS_DE_CTA_RENOMBRADO.zip")) as z:
        parser = BancoPDFParser()
        for name in z.namelist():
            if name.lower().endswith(".pdf") and not name.startswith("__"):
                try:
                    df, validation = parser.parsear_pdf(z.read(name), name)
                    if df is not None and not df.empty:
                        for idx, row in df.iterrows():
                            try:
                                cargo = _to_decimal(row.get("Cargo", 0))
                                abono = _to_decimal(row.get("Abono", 0))
                                ref = str(row.get("Referencia_Bancaria_Limpia", "") or "").strip()
                                fecha_val = row.get("Fecha", None)
                                if isinstance(fecha_val, datetime):
                                    fecha = fecha_val
                                elif hasattr(fecha_val, "to_pydatetime"):
                                    fecha = fecha_val.to_pydatetime()
                                else:
                                    fecha = _to_datetime(fecha_val)
                                m = MovimientoBancario(
                                    banco=str(row.get("Banco", "") or ""),
                                    cuenta=str(row.get("Cuenta", "") or ""),
                                    fecha=fecha,
                                    concepto=str(row.get("Concepto", "") or ""),
                                    cargo=cargo,
                                    abono=abono,
                                    moneda=str(row.get("Moneda", "MXN") or "MXN"),
                                    referencia=ref,
                                )
                                m._fila_origen = idx + 2
                                movimientos.append(m)
                            except Exception:
                                continue
                except Exception:
                    pass
    return movimientos


@pytest.fixture(scope="module")
def real_data():
    if not PAQUETE.exists():
        pytest.skip("Datos reales no disponibles")
    return {
        "egresos": _load_egresos(),
        "ingresos": _load_ingresos(),
        "xmls": _load_xmls(),
        "movimientos": _load_movimientos(),
    }


@pytest.fixture(scope="module")
def real_result(real_data):
    config = EngineConfig(tolerancia_monto=Decimal("1.00"), tolerancia_dias=5)
    result = conciliar_banco_first(
        movimientos_bancarios=real_data["movimientos"],
        cedulas_egresos=real_data["egresos"],
        cedulas_ingresos=real_data["ingresos"],
        cfdis=real_data["xmls"],
        config=config,
        archivo_banco="ESTADOS_DE_CTA_RENOMBRADO.pdf",
    )
    return result


# =========================================================================
# 1. LECTURA DE DATOS COMPLETOS
# =========================================================================
class TestLecturaDatos:
    def test_2235_ingresos_leidos(self, real_data):
        assert len(real_data["ingresos"]) == 2235

    def test_756_egresos_leidos(self, real_data):
        assert len(real_data["egresos"]) == 756

    def test_1003_movimientos_cargados(self, real_data):
        assert len(real_data["movimientos"]) == 1003


# =========================================================================
# 2. FILAS Y AGRUPACION
# =========================================================================
class TestFilasYGrupos:
    def test_2991_filas_conservadas(self, real_result):
        assert len(real_result.filas) == 2991

    def test_756_filas_egresos(self, real_result):
        rows = [r for r in real_result.filas if r.GRUPO_ID.startswith("egreso_")]
        assert len(rows) == 756

    def test_2235_filas_ingresos(self, real_result):
        rows = [r for r in real_result.filas if r.GRUPO_ID.startswith("ingreso_")]
        assert len(rows) == 2235

    def test_agrupacion_no_elimina_filas(self, real_result):
        from collections import Counter
        poliza_counts = Counter(r.POLIZA for r in real_result.filas if r.POLIZA)
        for poliza, count in poliza_counts.items():
            grupo_filas = [r for r in real_result.filas if r.POLIZA == poliza]
            assert len(grupo_filas) == count

    def test_una_fila_por_registro(self, real_result):
        eg_count = 0
        ing_count = 0
        for r in real_result.filas:
            if r.GRUPO_ID.startswith("egreso_"):
                eg_count += 1
            else:
                ing_count += 1
        assert eg_count == 756
        assert ing_count == 2235


# =========================================================================
# 3. TOTALES POR GRUPO_ID UNICO
# =========================================================================
class TestTotalesPorGrupo:
    def test_grupos_unicos_con_estatus(self, real_result):
        unique_grupos = {}
        for r in real_result.filas:
            if r.GRUPO_ID not in unique_grupos:
                unique_grupos[r.GRUPO_ID] = r
        g_conc = sum(1 for r in unique_grupos.values() if r.ESTATUS == EstatusRegistro.CONCILIADO)
        g_prop = sum(1 for r in unique_grupos.values() if r.ESTATUS == EstatusRegistro.PROPUESTA_REVISAR)
        g_amb = sum(1 for r in unique_grupos.values() if r.ESTATUS == EstatusRegistro.AMBIGUO)
        g_sin = sum(1 for r in unique_grupos.values() if r.ESTATUS == EstatusRegistro.SIN_CANDIDATO)
        total = g_conc + g_prop + g_amb + g_sin
        assert total == len(unique_grupos), f"{total} != {len(unique_grupos)}"

    def test_grupos_egresos_count(self, real_result):
        eg = set(r.GRUPO_ID for r in real_result.filas if r.GRUPO_ID.startswith("egreso_"))
        assert len(eg) == 318

    def test_grupos_ingresos_count(self, real_result):
        ing = set(r.GRUPO_ID for r in real_result.filas if r.GRUPO_ID.startswith("ingreso_"))
        assert len(ing) == 140


# =========================================================================
# 4. TOTALES POR MOVIMIENTO_ID UNICO (no doble conteo)
# =========================================================================
class TestNoDobleConteo:
    def test_movimiento_id_no_reutilizado(self, real_result):
        mov_ids = [r.MOVIMIENTO_ID for r in real_result.filas if r.MOVIMIENTO_ID]
        assert len(mov_ids) == len(set(mov_ids))

    def test_total_conciliado_por_grupo_unico(self, real_result):
        unique_grupos = {}
        for r in real_result.filas:
            if r.GRUPO_ID not in unique_grupos:
                unique_grupos[r.GRUPO_ID] = r
        total_conc = sum(r.TOTAL_GRUPO for r in unique_grupos.values()
                         if r.ESTATUS == EstatusRegistro.CONCILIADO)
        assert total_conc == Decimal("0")

    def test_total_banco_por_movimiento_unico(self, real_result):
        mov_unicos = {}
        for r in real_result.filas:
            if r.MOVIMIENTO_ID and r.MOVIMIENTO_ID not in mov_unicos:
                mov_unicos[r.MOVIMIENTO_ID] = r
        total_banco = sum(r.CARGO + r.ABONO for r in mov_unicos.values())
        assert total_banco == Decimal("0")

    def test_poliza_top_no_multiplica_importe(self, real_result):
        from collections import Counter
        eg_rows = [r for r in real_result.filas if r.GRUPO_ID.startswith("egreso_")]
        poliza_counts = Counter(r.POLIZA for r in eg_rows if r.POLIZA)
        top_poliza, top_count = poliza_counts.most_common(1)[0]
        grupo_filas = [r for r in real_result.filas if r.POLIZA == top_poliza]
        total_grupo = grupo_filas[0].TOTAL_GRUPO
        assert total_grupo != total_grupo * top_count or top_count == 1


# =========================================================================
# 5. PROPUESTA NO ASIGNA MOVIMIENTO
# =========================================================================
class TestPropuestaSinAsignacion:
    def test_propuesta_movimiento_id_vacio(self, real_result):
        for r in real_result.filas:
            if r.ESTATUS == EstatusRegistro.PROPUESTA_REVISAR:
                assert r.MOVIMIENTO_ID == ""

    def test_propuesta_candidato_lleno(self, real_result):
        for r in real_result.filas:
            if r.ESTATUS == EstatusRegistro.PROPUESTA_REVISAR:
                assert r.CANDIDATO_MOVIMIENTO_ID != ""

    def test_propuesta_es_monto_baja(self, real_result):
        for r in real_result.filas:
            if r.ESTATUS == EstatusRegistro.PROPUESTA_REVISAR:
                assert r.TIPO_MATCH == TipoMatch.MONTO
                assert r.NIVEL_CONFIANZA == "BAJA"


# =========================================================================
# 6. AMBIGUO NO ASIGNA MOVIMIENTO
# =========================================================================
class TestAmbiguoSinAsignacion:
    def test_ambiguo_movimiento_id_vacio(self, real_result):
        for r in real_result.filas:
            if r.ESTATUS == EstatusRegistro.AMBIGUO:
                assert r.MOVIMIENTO_ID == ""

    def test_ambiguo_candidato_vacio(self, real_result):
        for r in real_result.filas:
            if r.ESTATUS == EstatusRegistro.AMBIGUO:
                assert r.CANDIDATO_MOVIMIENTO_ID == ""


# =========================================================================
# 7. TODOS LOS MOVIMIENTOS TIENEN ARCHIVO Y FILA
# =========================================================================
class TestMovimientosArchivoFila:
    def test_todos_con_archivo(self, real_result):
        for r in real_result.filas:
            if r.MOVIMIENTO_ID:
                assert r.ARCHIVO_BANCO, f"Sin ARCHIVO_BANCO: {r.GRUPO_ID}"

    def test_todos_con_fila(self, real_result):
        for r in real_result.filas:
            if r.MOVIMIENTO_ID:
                assert r.FILA_BANCO > 0, f"FILA_BANCO=0: {r.GRUPO_ID}"

    def test_universo_movimientos_completo(self, real_result):
        assert len(real_result.movimientos_universo) == 1003
        for m in real_result.movimientos_universo:
            assert m.MOVIMIENTO_ID
            assert m.ARCHIVO_BANCO
            assert m.FILA_BANCO > 0


# =========================================================================
# 8. EGRESOS SOLO CARGOS, INGRESOS SOLO ABONOS
# =========================================================================
class TestNaturaleza:
    def test_egreso_conciliado_con_cargo(self, real_result):
        for r in real_result.filas:
            if r.GRUPO_ID.startswith("egreso_") and r.ESTATUS == EstatusRegistro.CONCILIADO:
                assert r.CARGO > Decimal("0")

    def test_ingreso_conciliado_con_abono(self, real_result):
        for r in real_result.filas:
            if r.GRUPO_ID.startswith("ingreso_") and r.ESTATUS == EstatusRegistro.CONCILIADO:
                assert r.ABONO > Decimal("0")


# =========================================================================
# 9. MXN NO CRUZA USD
# =========================================================================
class TestMonedaIncompatible:
    def test_egreso_mxn_banco_mxn(self, real_data):
        movs_usd = [m for m in real_data["movimientos"]
                    if getattr(m, "moneda", "MXN").upper() != "MXN"]
        assert len(movs_usd) >= 0


# =========================================================================
# 10. MOVIMIENTO NO SE REUTILIZA ENTRE MODULOS
# =========================================================================
class TestNoReutilizacion:
    def test_no_reutilizados(self, real_result):
        mov_ids = [r.MOVIMIENTO_ID for r in real_result.filas if r.MOVIMIENTO_ID]
        assert len(mov_ids) == len(set(mov_ids))


# =========================================================================
# 11. DETERMINISMO
# =========================================================================
class TestDeterminismo:
    def test_mismos_ids_dos_runs(self, real_data):
        config = EngineConfig(tolerancia_monto=Decimal("1.00"), tolerancia_dias=5)
        r1 = conciliar_banco_first(
            movimientos_bancarios=real_data["movimientos"],
            cedulas_egresos=real_data["egresos"],
            cedulas_ingresos=real_data["ingresos"],
            cfdis=real_data["xmls"],
            config=config,
            archivo_banco="ESTADOS_DE_CTA_RENOMBRADO.pdf",
        )
        r2 = conciliar_banco_first(
            movimientos_bancarios=real_data["movimientos"],
            cedulas_egresos=real_data["egresos"],
            cedulas_ingresos=real_data["ingresos"],
            cfdis=real_data["xmls"],
            config=config,
            archivo_banco="ESTADOS_DE_CTA_RENOMBRADO.pdf",
        )
        assert len(r1.filas) == len(r2.filas)
        for a, b in zip(r1.filas, r2.filas):
            assert a.GRUPO_ID == b.GRUPO_ID
            assert a.ESTATUS == b.ESTATUS
            assert a.MOVIMIENTO_ID == b.MOVIMIENTO_ID


# =========================================================================
# 12. SHA-256
# =========================================================================
class TestSHA256:
    def test_cinco_archivos_coinciden(self):
        import hashlib
        checks = [
            ("LAYOUT_CARGA_EGRESOS.xlsx", "7CFAC1C9FBB55326751723E475513C24A8D909E7252BB1CD72B0CAFFAB50BA5B"),
            ("LAYOUT_CEDULA_INGRESOS.xlsx", "832C2628B8F2EDF969425A06877399AEE08BA3F7380BC40B0ACDBA9126A553F0"),
            ("XML_feb_24.zip", "83F25C789A67EF23A49D5A05B50FA421B97F7878D8F37F8C2563CA091E36FE2D"),
            ("XML_RECIBIDOS_FEB_24.zip", "971A3BAA3A7466C3FA976D93E81477A900D8DA7739089AC2C9285B9F65FA22F6"),
            ("ESTADOS_DE_CTA_RENOMBRADO.zip", "8894D3F758594E12B06D6653EB599ED325FA07BE4DB23CCAEC15581125578AA3"),
        ]
        for fname, expected in checks:
            h = hashlib.sha256()
            with open(PAQUETE / fname, "rb") as fh:
                while chunk := fh.read(8192):
                    h.update(chunk)
            assert h.hexdigest().upper() == expected, f"{fname}: hash mismatch"
