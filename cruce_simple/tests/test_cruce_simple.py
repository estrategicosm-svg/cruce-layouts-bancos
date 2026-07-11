"""Pruebas obligatorias para cruce_simple."""
from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from cruce_simple.models import (
    EstatusCruce,
    FilaLayout,
    GrupoPoliza,
    MovimientoBanco,
    ResultadoCruce,
    normalizar_banco,
    normalizar_empresa,
)
from cruce_simple.matcher import agrupar_por_poliza, asignar_cruces, buscar_candidatos, cruzar_grupos


def _fila(empresa="INTRA", poliza="PBNK01/2024/00365", uuid="UUID-1",
          moneda="MXN", tp=Decimal("100"), td=Decimal("0"),
          banco="BANAMEX", **kw) -> FilaLayout:
    return FilaLayout(
        empresa=empresa, poliza=poliza, uuid=uuid,
        rfc="RFC", nombre="NOM", fecha="2024-02-15",
        moneda=moneda, total_pesos=tp, total_dls=td,
        banco=banco, **kw,
    )


def _mov(empresa="INTRA", banco="BNMX", moneda="MXN",
         cargo=Decimal("100"), abono=Decimal("0"),
         archivo="INTRA_BANAMEX_CTA0688_MXN_FEB2024.pdf",
         es_tdc=False, **kw) -> MovimientoBanco:
    return MovimientoBanco(
        archivo=archivo, empresa=empresa, banco=banco,
        cuenta="CTA0688", moneda=moneda, fecha="2024-02-15",
        concepto="PAGO", cargo=cargo, abono=abono,
        referencia="REF001", es_tdc=es_tdc, **kw,
    )


class TestAgrupacionPorEmpresaPoliza:
    def test_agrupa_por_empresa_y_poliza(self):
        filas = [
            _fila(empresa="INTRA", poliza="P001", uuid="U1"),
            _fila(empresa="INTRA", poliza="P001", uuid="U2"),
            _fila(empresa="INTRA", poliza="P001", uuid="U3"),
            _fila(empresa="INTRA", poliza="P001", uuid="U4"),
        ]
        grupos = agrupar_por_poliza(filas)
        assert len(grupos) == 1
        key = "INTRA|P001"
        assert key in grupos
        assert len(grupos[key].filas) == 4

    def test_uuid_distintos_no_separan_grupo(self):
        filas = [
            _fila(uuid="UUID-A"),
            _fila(uuid="UUID-B"),
            _fila(uuid="UUID-C"),
        ]
        grupos = agrupar_por_poliza(filas)
        assert len(grupos) == 1
        assert len(list(grupos.values())[0].filas) == 3

    def test_misma_poliza_empresas_distintas_grupos_distintos(self):
        filas = [
            _fila(empresa="INTRA", poliza="P001"),
            _fila(empresa="CSC", poliza="P001"),
        ]
        grupos = agrupar_por_poliza(filas)
        assert len(grupos) == 2
        assert "INTRA|P001" in grupos
        assert "CSC|P001" in grupos

    def test_totales_correctos_mxn(self):
        filas = [
            _fila(tp=Decimal("1000"), td=Decimal("0"), moneda="MXN"),
            _fila(tp=Decimal("2000"), td=Decimal("0"), moneda="MXN"),
        ]
        grupos = agrupar_por_poliza(filas)
        g = list(grupos.values())[0]
        assert g.total_mxn == Decimal("3000")
        assert g.total_grupo == Decimal("3000")

    def test_totales_correctos_usd(self):
        filas = [
            _fila(moneda="USD", tp=Decimal("100"), td=Decimal("50")),
            _fila(moneda="USD", tp=Decimal("200"), td=Decimal("80")),
        ]
        grupos = agrupar_por_poliza(filas)
        g = list(grupos.values())[0]
        assert g.total_usd == Decimal("130")
        assert g.total_grupo == Decimal("130")
        assert g.moneda_dominante == "USD"

    def test_monedas_mixtas(self):
        filas = [
            _fila(moneda="MXN", tp=Decimal("1000"), td=Decimal("0")),
            _fila(moneda="USD", tp=Decimal("500"), td=Decimal("50")),
        ]
        grupos = agrupar_por_poliza(filas)
        g = list(grupos.values())[0]
        assert g.tiene_mixed is True


class TestCruceEgresos:
    def test_egresos_buscan_cargo(self):
        filas = [_fila(tp=Decimal("500"))]
        grupos = agrupar_por_poliza(filas)
        movs = [
            _mov(cargo=Decimal("500"), abono=Decimal("0")),
            _mov(cargo=Decimal("0"), abono=Decimal("500")),
        ]
        candidatos = buscar_candidatos(list(grupos.values())[0], movs, usar_cargo=True)
        assert len(candidatos) == 1
        assert candidatos[0].cargo == Decimal("500")

    def test_egresos_no_cruzan_abonos(self):
        filas = [_fila(tp=Decimal("500"))]
        grupos = agrupar_por_poliza(filas)
        movs = [_mov(cargo=Decimal("0"), abono=Decimal("500"))]
        candidatos = buscar_candidatos(list(grupos.values())[0], movs, usar_cargo=True)
        assert len(candidatos) == 0


class TestCruceIngresos:
    def test_ingresos_buscan_abono(self):
        filas = [_fila(tp=Decimal("500"))]
        grupos = agrupar_por_poliza(filas)
        movs = [_mov(cargo=Decimal("0"), abono=Decimal("500"))]
        candidatos = buscar_candidatos(list(grupos.values())[0], movs, usar_cargo=False)
        assert len(candidatos) == 1
        assert candidatos[0].abono == Decimal("500")

    def test_ingresos_no_cruzan_cargos(self):
        filas = [_fila(tp=Decimal("500"))]
        grupos = agrupar_por_poliza(filas)
        movs = [_mov(cargo=Decimal("500"), abono=Decimal("0"))]
        candidatos = buscar_candidatos(list(grupos.values())[0], movs, usar_cargo=False)
        assert len(candidatos) == 0


class TestRestriccionUnAMovimiento:
    def test_un_grupo_usa_max_un_movimiento(self):
        filas = [_fila(tp=Decimal("100"))]
        grupos = agrupar_por_poliza(filas)
        movs = [_mov(cargo=Decimal("100")), _mov(cargo=Decimal("100"))]
        res = cruzar_grupos(grupos, movs, usar_cargo=True)
        assert res[0].estatus == EstatusCruce.MULTIPLES_CANDIDATOS
        assert res[0].movimiento_asignado is None

    def test_un_movimiento_usa_max_un_grupo(self):
        filas1 = [_fila(poliza="P001", tp=Decimal("100"))]
        filas2 = [_fila(poliza="P002", tp=Decimal("100"))]
        grupos = agrupar_por_poliza(filas1 + filas2)
        movs = [_mov(cargo=Decimal("100"))]
        res = cruzar_grupos(grupos, movs, usar_cargo=True)
        encontrados = [r for r in res if r.estatus == EstatusCruce.ENCONTRADO]
        assert len(encontrados) == 1


class TestCoincidenciaUnica:
    def test_asigna_cruce(self):
        filas = [_fila(tp=Decimal("22606.23"))]
        grupos = agrupar_por_poliza(filas)
        movs = [_mov(cargo=Decimal("22606.23"))]
        res = cruzar_grupos(grupos, movs, usar_cargo=True)
        assert res[0].estatus == EstatusCruce.ENCONTRADO
        cruce_map = asignar_cruces(res, [], movs)
        assert "INTRA|PBNK01/2024/00365" in cruce_map
        assert cruce_map["INTRA|PBNK01/2024/00365"] == "INTRA-EGR-BNMX-001"


class TestMultiplesCandidatos:
    def test_genera_revisar(self):
        filas = [_fila(tp=Decimal("100"))]
        grupos = agrupar_por_poliza(filas)
        movs = [_mov(cargo=Decimal("100")), _mov(cargo=Decimal("100"))]
        res = cruzar_grupos(grupos, movs, usar_cargo=True)
        assert res[0].estatus == EstatusCruce.MULTIPLES_CANDIDATOS
        assert len(res[0].candidatos) == 2


class TestSinCandidato:
    def test_deja_cruce_vacio(self):
        filas = [_fila(tp=Decimal("99999"))]
        grupos = agrupar_por_poliza(filas)
        movs = [_mov(cargo=Decimal("100"))]
        res = cruzar_grupos(grupos, movs, usar_cargo=True)
        assert res[0].estatus == EstatusCruce.NO_ENCONTRADO
        assert res[0].cruce_bancario == ""


class TestConsecutivo:
    def test_reinicia_por_empresa_tipo_banco(self):
        filas1 = [_fila(poliza="P001", tp=Decimal("100"))]
        filas2 = [_fila(poliza="P002", tp=Decimal("200"))]
        grupos = agrupar_por_poliza(filas1 + filas2)
        movs = [_mov(cargo=Decimal("100")), _mov(cargo=Decimal("200"))]
        res = cruzar_grupos(grupos, movs, usar_cargo=True)
        cruce_map = asignar_cruces(res, [], movs)
        assert cruce_map["INTRA|P001"] == "INTRA-EGR-BNMX-001"
        assert cruce_map["INTRA|P002"] == "INTRA-EGR-BNMX-002"


class TestMismoCruceBancario:
    def test_cruce_aparece_en_layout_y_banco(self):
        filas = [_fila(tp=Decimal("500")), _fila(tp=Decimal("500"))]
        grupos = agrupar_por_poliza(filas)
        movs = [_mov(cargo=Decimal("1000"))]
        res = cruzar_grupos(grupos, movs, usar_cargo=True)
        cruce_map = asignar_cruces(res, [], movs)
        cruce = cruce_map.get("INTRA|PBNK01/2024/00365")
        assert cruce is not None
        assert movs[0].cruce_cargo == cruce


class TestTDC:
    def test_tdc_fuera_cruce_automatico(self):
        filas = [_fila(tp=Decimal("100"))]
        grupos = agrupar_por_poliza(filas)
        movs = [_mov(cargo=Decimal("100"), es_tdc=True)]
        candidatos = buscar_candidatos(list(grupos.values())[0], movs, usar_cargo=True)
        assert len(candidatos) == 0


class TestFormatoArchivo:
    def test_excel_tres_hojas(self):
        from cruce_simple.output_writer import generar_excel
        filas_eg = [_fila(tp=Decimal("100"))]
        filas_ing = [_fila(empresa="CSC", poliza="I001", tp=Decimal("200"))]
        movs = [_mov(cargo=Decimal("100"))]
        res_eg = [ResultadoCruce(
            grupo=list(agrupar_por_poliza(filas_eg).values())[0],
            estatus=EstatusCruce.ENCONTRADO,
            movimiento_asignado=movs[0],
        )]
        cruce_map = {"INTRA|PBNK01/2024/00365": "INTRA-EGR-BNMX-001"}
        info = generar_excel(
            filas_eg, filas_ing, movs, cruce_map, res_eg, [],
            "outputs/test_tres_hojas.xlsx",
        )
        assert len(info["hojas"]) == 3
        assert "EGRESOS" in info["hojas"]
        assert "INGRESOS" in info["hojas"]
        assert "MOVIMIENTOS_BANCARIOS" in info["hojas"]


class TestNoCargaXML:
    def test_no_existe_import_xml(self):
        import cruce_simple.app as app_mod
        source = open(app_mod.__file__).read()
        assert "xml" not in source.lower()
        assert "XML" not in source
        assert "CFDI" not in source


class TestPruebaDeFuego:
    def test_intra_poliza_pbnk01_2024_00365(self):
        filas = [
            _fila(empresa="INTRA", poliza="PBNK01/2024/00365", uuid=f"UUID-{i}",
                  tp=Decimal("5651.5575"), moneda="MXN")
            for i in range(4)
        ]
        grupos = agrupar_por_poliza(filas)
        g = list(grupos.values())[0]
        assert g.empresa == "INTRA"
        assert g.poliza == "PBNK01/2024/00365"
        assert len(g.filas) == 4
        assert abs(g.total_grupo - Decimal("22606.23")) < Decimal("0.01")

        mov = _mov(
            empresa="INTRA", banco="BNMX", moneda="MXN",
            cargo=Decimal("22606.23"), abono=Decimal("0"),
        )
        res = cruzar_grupos(grupos, [mov], usar_cargo=True)
        assert res[0].estatus == EstatusCruce.ENCONTRADO
        assert res[0].movimiento_asignado is mov
        assert res[0].diferencia == Decimal("0")

        cruce_map = asignar_cruces(res, [], [mov])
        cruce = cruce_map["INTRA|PBNK01/2024/00365"]
        assert cruce == "INTRA-EGR-BNMX-001"
        assert mov.cruce_cargo == cruce

        for f in filas:
            assert cruce_map.get(f"{f.empresa}|{f.poliza}") == cruce


class TestNormalizaciones:
    def test_empresa_transscruces(self):
        assert normalizar_empresa("TRANSCRUCES") == "TRANS"

    def test_empresa_intra(self):
        assert normalizar_empresa("INTRA") == "INTRA"

    def test_banco_banamex(self):
        assert normalizar_banco("BANAMEX") == "BNMX"

    def test_banco_bajio(self):
        assert normalizar_banco("BAJIO") == "BAJIO"

    def test_banco_banregio(self):
        assert normalizar_banco("BANREGIO") == "BREG"
