"""Agrupa filas por EMPRESA+POLIZA y cruza contra movimientos bancarios."""
from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from cruce_simple.models import (
    EstatusCruce,
    FilaLayout,
    GrupoPoliza,
    MovimientoBanco,
    ResultadoCruce,
)


def agrupar_por_poliza(filas: list[FilaLayout]) -> dict[str, GrupoPoliza]:
    grupos: dict[str, GrupoPoliza] = {}
    for f in filas:
        key = f"{f.empresa}|{f.poliza}"
        if key not in grupos:
            grupos[key] = GrupoPoliza(empresa=f.empresa, poliza=f.poliza)
        grupos[key].filas.append(f)
    for g in grupos.values():
        g.calcular_totales()
    return grupos


def buscar_candidatos(
    grupo: GrupoPoliza,
    movimientos: list[MovimientoBanco],
    usar_cargo: bool,
) -> list[MovimientoBanco]:
    candidatos: list[MovimientoBanco] = []
    for m in movimientos:
        if m.es_tdc:
            continue
        if m.empresa != grupo.empresa:
            continue
        if m.moneda.upper() != grupo.moneda_dominante.upper():
            continue
        if usar_cargo and m.cargo <= 0:
            continue
        if not usar_cargo and m.abono <= 0:
            continue
        monto_m = m.cargo if usar_cargo else m.abono
        dif = abs(monto_m - grupo.total_grupo)
        if dif <= Decimal("1.00"):
            candidatos.append(m)
    return candidatos


def cruzar_grupos(
    grupos: dict[str, GrupoPoliza],
    movimientos: list[MovimientoBanco],
    usar_cargo: bool,
) -> list[ResultadoCruce]:
    resultados: list[ResultadoCruce] = []
    movimientos_usados: set[int] = set()

    for key in sorted(grupos.keys()):
        grupo = grupos[key]

        if grupo.tiene_mixed:
            resultados.append(ResultadoCruce(
                grupo=grupo,
                estatus=EstatusCruce.MONEDAS_MIXTAS,
                causa="POLIZA_CON_MONEDAS_MIXTAS",
            ))
            continue

        candidatos = buscar_candidatos(grupo, movimientos, usar_cargo)

        candidatos_disponibles = [
            m for m in candidatos
            if id(m) not in movimientos_usados
        ]

        if len(candidatos_disponibles) == 0:
            resultados.append(ResultadoCruce(
                grupo=grupo,
                estatus=EstatusCruce.NO_ENCONTRADO,
            ))
        elif len(candidatos_disponibles) == 1:
            m = candidatos_disponibles[0]
            movimientos_usados.add(id(m))
            monto_m = m.cargo if usar_cargo else m.abono
            dif = monto_m - grupo.total_grupo
            monto_str = f"{monto_m:.2f}"
            resultados.append(ResultadoCruce(
                grupo=grupo,
                estatus=EstatusCruce.ENCONTRADO,
                movimiento_asignado=m,
                candidatos=candidatos_disponibles,
                cruce_bancario="",
                diferencia=dif,
            ))
            m.poliza_relacionada = grupo.poliza
        else:
            resultados.append(ResultadoCruce(
                grupo=grupo,
                estatus=EstatusCruce.MULTIPLES_CANDIDATOS,
                candidatos=candidatos_disponibles,
            ))

    return resultados


def asignar_cruces(
    resultados_egresos: list[ResultadoCruce],
    resultados_ingresos: list[ResultadoCruce],
    movimientos: list[MovimientoBanco],
) -> dict[str, str]:
    consecutivos: dict[str, int] = defaultdict(int)
    cruce_map: dict[str, str] = {}

    for r in resultados_egresos:
        if r.estatus != EstatusCruce.ENCONTRADO:
            continue
        g = r.grupo
        m = r.movimiento_asignado
        key = f"{g.empresa}|EGR|{m.banco}"
        consecutivos[key] += 1
        cruce = f"{g.empresa}-EGR-{m.banco}-{consecutivos[key]:03d}"
        cruce_map[g.grupo_id] = cruce
        m.cruce_cargo = cruce

    for r in resultados_ingresos:
        if r.estatus != EstatusCruce.ENCONTRADO:
            continue
        g = r.grupo
        m = r.movimiento_asignado
        key = f"{g.empresa}|ING|{m.banco}"
        consecutivos[key] += 1
        cruce = f"{g.empresa}-ING-{m.banco}-{consecutivos[key]:03d}"
        cruce_map[g.grupo_id] = cruce
        m.cruce_abono = cruce

    return cruce_map
