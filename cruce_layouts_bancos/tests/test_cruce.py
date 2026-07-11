"""Pruebas para cruce_layouts_bancos."""
from __future__ import annotations

from decimal import Decimal

from cruce_layouts_bancos.models import (
    EstatusCruce, FilaLayout, GrupoPoliza, MovimientoBanco, ResultadoCruce,
    normalizar_empresa, normalizar_banco,
)
from cruce_layouts_bancos.matcher import (
    agrupar_por_poliza, asignar_cruces, buscar_candidatos, cruzar_grupos,
)


def _fila(empresa="INTRA", poliza="P001", uuid="UUID-1",
          moneda="MXN", tp=Decimal("100"), td=Decimal("0"),
          banco="BANAMEX", **kw) -> FilaLayout:
    return FilaLayout(
        empresa=empresa, poliza=poliza, uuid=uuid,
        rfc="RFC", nombre="NOM", fecha_factura="2024-01-01",
        fecha_operacion="2024-02-15", moneda=moneda,
        total_pesos=tp, total_dls=td, banco=banco, **kw,
    )


def _mov(empresa="INTRA", banco="BNMX", moneda="MXN",
         cargo=Decimal("100"), abono=Decimal("0"), es_tdc=False, **kw) -> MovimientoBanco:
    return MovimientoBanco(
        archivo_origen="INTRA_BANAMEX_CTA0688_MXN_FEB2024.pdf",
        ruta_interna_zip="INTRA/INTRA_BANAMEX_CTA0688_MXN_FEB2024.pdf",
        empresa_detectada=empresa, banco_detectado=banco,
        cuenta_detectada="CTA0688", cuenta_ultimos_4="0688",
        moneda_detectada=moneda, mes_detectado="FEB2024",
        fecha_movimiento="2024-02-15", descripcion_original="PAGO",
        referencia_usada="REF001", clave_rastreo="", autorizacion="",
        cargo=cargo, abono=abono, saldo=Decimal("0"),
        tipo_movimiento="CARGO" if cargo > 0 else "ABONO",
        es_tdc=es_tdc, **kw,
    )


class TestAgrupacion:
    def test_agrupa_empresa_poliza(self):
        filas = [_fila(uuid=f"U{i}") for i in range(4)]
        g = agrupar_por_poliza(filas)
        assert len(g) == 1
        assert len(list(g.values())[0].filas) == 4

    def test_uuid_no_separa_grupo(self):
        filas = [_fila(uuid="A"), _fila(uuid="B"), _fila(uuid="C")]
        g = agrupar_por_poliza(filas)
        assert len(g) == 1

    def test_empresas_distintas_grupos_distintos(self):
        filas = [_fila(empresa="INTRA"), _fila(empresa="CSC")]
        g = agrupar_por_poliza(filas)
        assert len(g) == 2

    def test_totales_mxn(self):
        filas = [_fila(tp=Decimal("1000")), _fila(tp=Decimal("2000"))]
        g = list(agrupar_por_poliza(filas).values())[0]
        assert g.total_mxn == Decimal("3000")
        assert g.total_grupo == Decimal("3000")

    def test_totales_usd(self):
        filas = [_fila(moneda="USD", tp=Decimal("100"), td=Decimal("50")),
                 _fila(moneda="USD", tp=Decimal("200"), td=Decimal("80"))]
        g = list(agrupar_por_poliza(filas).values())[0]
        assert g.total_usd == Decimal("130")
        assert g.total_grupo == Decimal("130")

    def test_monedas_mixtas(self):
        filas = [_fila(moneda="MXN", tp=Decimal("1000")),
                 _fila(moneda="USD", tp=Decimal("500"), td=Decimal("50"))]
        g = list(agrupar_por_poliza(filas).values())[0]
        assert g.tiene_mixed is True


class TestCruce:
    def test_egresos_cargo(self):
        g = agrupar_por_poliza([_fila(tp=Decimal("500"))])
        movs = [_mov(cargo=Decimal("500")), _mov(cargo=Decimal("0"), abono=Decimal("500"))]
        cand = buscar_candidatos(list(g.values())[0], movs, usar_cargo=True)
        assert len(cand) == 1 and cand[0].cargo == Decimal("500")

    def test_egresos_no_abono(self):
        g = agrupar_por_poliza([_fila(tp=Decimal("500"))])
        movs = [_mov(cargo=Decimal("0"), abono=Decimal("500"))]
        cand = buscar_candidatos(list(g.values())[0], movs, usar_cargo=True)
        assert len(cand) == 0

    def test_ingresos_abono(self):
        g = agrupar_por_poliza([_fila(tp=Decimal("500"))])
        movs = [_mov(cargo=Decimal("0"), abono=Decimal("500"))]
        cand = buscar_candidatos(list(g.values())[0], movs, usar_cargo=False)
        assert len(cand) == 1 and cand[0].abono == Decimal("500")

    def test_ingresos_no_cargo(self):
        g = agrupar_por_poliza([_fila(tp=Decimal("500"))])
        movs = [_mov(cargo=Decimal("500"))]
        cand = buscar_candidatos(list(g.values())[0], movs, usar_cargo=False)
        assert len(cand) == 0

    def test_unico_asigna(self):
        g = agrupar_por_poliza([_fila(tp=Decimal("100"))])
        movs = [_mov(cargo=Decimal("100"))]
        r = cruzar_grupos(g, movs, usar_cargo=True)
        assert r[0].estatus == EstatusCruce.ENCONTRADO

    def test_multiples(self):
        g = agrupar_por_poliza([_fila(tp=Decimal("100"))])
        movs = [_mov(cargo=Decimal("100")), _mov(cargo=Decimal("100"))]
        r = cruzar_grupos(g, movs, usar_cargo=True)
        assert r[0].estatus == EstatusCruce.MULTIPLES_CANDIDATOS

    def test_sin_candidato(self):
        g = agrupar_por_poliza([_fila(tp=Decimal("99999"))])
        movs = [_mov(cargo=Decimal("100"))]
        r = cruzar_grupos(g, movs, usar_cargo=True)
        assert r[0].estatus == EstatusCruce.NO_ENCONTRADO

    def test_tdc_excluido(self):
        g = agrupar_por_poliza([_fila(tp=Decimal("100"))])
        movs = [_mov(cargo=Decimal("100"), es_tdc=True)]
        cand = buscar_candidatos(list(g.values())[0], movs, usar_cargo=True)
        assert len(cand) == 0


class TestRestriccion:
    def test_un_grupo_un_mov(self):
        g = agrupar_por_poliza([_fila(tp=Decimal("100"))])
        movs = [_mov(cargo=Decimal("100")), _mov(cargo=Decimal("100"))]
        r = cruzar_grupos(g, movs, usar_cargo=True)
        assert r[0].estatus == EstatusCruce.MULTIPLES_CANDIDATOS
        assert r[0].movimiento_asignado is None

    def test_un_mov_un_grupo(self):
        g1 = agrupar_por_poliza([_fila(poliza="P001", tp=Decimal("100"))])
        g2 = agrupar_por_poliza([_fila(poliza="P002", tp=Decimal("100"))])
        g = {**g1, **g2}
        movs = [_mov(cargo=Decimal("100"))]
        r = cruzar_grupos(g, movs, usar_cargo=True)
        assert sum(1 for x in r if x.estatus == EstatusCruce.ENCONTRADO) == 1


class TestConsecutivo:
    def test_reinicia(self):
        g = agrupar_por_poliza([
            _fila(poliza="P001", tp=Decimal("100")),
            _fila(poliza="P002", tp=Decimal("200")),
        ])
        movs = [_mov(cargo=Decimal("100")), _mov(cargo=Decimal("200"))]
        r = cruzar_grupos(g, movs, usar_cargo=True)
        cm = asignar_cruces(r, [])
        assert cm["INTRA|P001"] == "INTRA-EGR-BNMX-001"
        assert cm["INTRA|P002"] == "INTRA-EGR-BNMX-002"


class TestMismoCruce:
    def test_en_ambos_lados(self):
        g = agrupar_por_poliza([_fila(tp=Decimal("500")), _fila(tp=Decimal("500"))])
        movs = [_mov(cargo=Decimal("1000"))]
        r = cruzar_grupos(g, movs, usar_cargo=True)
        cm = asignar_cruces(r, [])
        cruce = cm.get("INTRA|P001")
        assert cruce is not None
        assert movs[0].cruce_cargo == cruce
        assert movs[0].poliza_relacionada == "P001"


class TestNormalizaciones:
    def test_empresa_transscruces(self):
        assert normalizar_empresa("TRANSCRUCES") == "TRANS"

    def test_banco_banamex(self):
        assert normalizar_banco("BANAMEX") == "BNMX"

    def test_banco_bajio(self):
        assert normalizar_banco("BAJIO") == "BAJIO"

    def test_banco_banregio(self):
        assert normalizar_banco("BANREGIO") == "BREG"


class TestNoXML:
    def test_app_no_importa_xml(self):
        import cruce_layouts_bancos.app as mod
        source = open(mod.__file__).read()
        assert "xml" not in source.lower()
        assert "CFDI" not in source
