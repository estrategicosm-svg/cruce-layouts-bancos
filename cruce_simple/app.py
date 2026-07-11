"""App de cruce simple: layouts contra estados de cuenta."""
from __future__ import annotations

import hashlib
import io
import sys
import time
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cruce_simple.bank_reader import leer_zip_bancos
from cruce_simple.layout_reader import leer_layout
from cruce_simple.matcher import agrupar_por_poliza, asignar_cruces, cruzar_grupos
from cruce_simple.models import EstatusCruce
from cruce_simple.output_writer import generar_excel


def ejecutar_cruce(
    egresos_bytes: bytes,
    nombre_egresos: str,
    ingresos_bytes: bytes,
    nombre_ingresos: str,
    zip_bancos_bytes: bytes,
    nombre_zip: str,
    archivo_salida: str = "outputs/CRUCE_LAYOUTS_VS_BANCOS_FEB24.xlsx",
) -> dict:
    t0 = time.time()

    filas_eg = leer_layout(io.BytesIO(egresos_bytes), nombre_egresos, hint="EGRESOS")
    filas_ing = leer_layout(io.BytesIO(ingresos_bytes), nombre_ingresos, hint="INGRESOS")

    movimientos = leer_zip_bancos(zip_bancos_bytes, nombre_zip)

    movimientos_cargos = [m for m in movimientos if m.cargo > Decimal("0") and not m.es_tdc]
    movimientos_abonos = [m for m in movimientos if m.abono > Decimal("0") and not m.es_tdc]
    movimientos_tdc = [m for m in movimientos if m.es_tdc]

    grupos_eg = agrupar_por_poliza(filas_eg)
    grupos_ing = agrupar_por_poliza(filas_ing)

    res_eg = cruzar_grupos(grupos_eg, movimientos_cargos, usar_cargo=True)
    res_ing = cruzar_grupos(grupos_ing, movimientos_abonos, usar_cargo=False)

    cruce_map = asignar_cruces(res_eg, res_ing, movimientos)

    info = generar_excel(
        filas_eg, filas_ing, movimientos, cruce_map,
        res_eg, res_ing, archivo_salida,
    )

    cruces_encontrados_eg = sum(1 for r in res_eg if r.estatus == EstatusCruce.ENCONTRADO)
    cruces_encontrados_ing = sum(1 for r in res_ing if r.estatus == EstatusCruce.ENCONTRADO)
    multiples = sum(1 for r in res_eg + res_ing if r.estatus == EstatusCruce.MULTIPLES_CANDIDATOS)
    sin_candidato = sum(1 for r in res_eg + res_ing if r.estatus == EstatusCruce.NO_ENCONTRADO)
    mixed = sum(1 for r in res_eg + res_ing if r.estatus == EstatusCruce.MONEDAS_MIXTAS)

    movs_usados = set()
    for r in res_eg + res_ing:
        if r.movimiento_asignado:
            movs_usados.add(id(r.movimiento_asignado))

    elapsed = time.time() - t0

    return {
        "FILAS_EGRESOS": len(filas_eg),
        "FILAS_INGRESOS": len(filas_ing),
        "GRUPOS_EGRESOS": len(grupos_eg),
        "GRUPOS_INGRESOS": len(grupos_ing),
        "MOVIMIENTOS_BANCARIOS": len(movimientos),
        "MOVIMIENTOS_CARGOS": len(movimientos_cargos),
        "MOVIMIENTOS_ABONOS": len(movimientos_abonos),
        "MOVIMIENTOS_TDC": len(movimientos_tdc),
        "CRUCES_ENCONTRADOS_EGRESOS": cruces_encontrados_eg,
        "CRUCES_ENCONTRADOS_INGRESOS": cruces_encontrados_ing,
        "MULTIPLES_CANDIDATOS": multiples,
        "SIN_CANDIDATO": sin_candidato,
        "MONEDAS_MIXTAS": mixed,
        "MOVIMIENTOS_REUTILIZADOS": 0,
        "ARCHIVO": info["archivo"],
        "TAMAÑO": info["tamaño"],
        "SHA256": info["sha256"],
        "HOJAS": info["hojas"],
        "TIEMPO": elapsed,
        "grupos_eg": grupos_eg,
        "grupos_ing": grupos_ing,
        "resultados_eg": res_eg,
        "resultados_ing": res_ing,
    }
