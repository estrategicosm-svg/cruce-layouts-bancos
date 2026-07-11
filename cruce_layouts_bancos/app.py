"""App de cruce simple: layouts contra estados de cuenta."""
from __future__ import annotations

import io
import sys
import time
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cruce_layouts_bancos.bank_reader import leer_zip_bancos
from cruce_layouts_bancos.layout_reader import leer_layout
from cruce_layouts_bancos.matcher import agrupar_por_poliza, asignar_cruces, cruzar_grupos
from cruce_layouts_bancos.models import EstatusCruce
from cruce_layouts_bancos.output_writer import generar_excel


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

    mov_cargos = [m for m in movimientos if m.cargo > Decimal("0") and not m.es_tdc]
    mov_abonos = [m for m in movimientos if m.abono > Decimal("0") and not m.es_tdc]
    mov_tdc = [m for m in movimientos if m.es_tdc]

    grupos_eg = agrupar_por_poliza(filas_eg)
    grupos_ing = agrupar_por_poliza(filas_ing)

    res_eg = cruzar_grupos(grupos_eg, mov_cargos, usar_cargo=True)
    res_ing = cruzar_grupos(grupos_ing, mov_abonos, usar_cargo=False)

    cruce_map = asignar_cruces(res_eg, res_ing)

    info = generar_excel(filas_eg, filas_ing, movimientos, cruce_map, archivo_salida)

    enc_eg = sum(1 for r in res_eg if r.estatus == EstatusCruce.ENCONTRADO)
    enc_ing = sum(1 for r in res_ing if r.estatus == EstatusCruce.ENCONTRADO)
    mult_eg = sum(1 for r in res_eg if r.estatus == EstatusCruce.MULTIPLES_CANDIDATOS)
    mult_ing = sum(1 for r in res_ing if r.estatus == EstatusCruce.MULTIPLES_CANDIDATOS)
    sin_eg = sum(1 for r in res_eg if r.estatus == EstatusCruce.NO_ENCONTRADO)
    sin_ing = sum(1 for r in res_ing if r.estatus == EstatusCruce.NO_ENCONTRADO)
    mix_eg = sum(1 for r in res_eg if r.estatus == EstatusCruce.MONEDAS_MIXTAS)
    mix_ing = sum(1 for r in res_ing if r.estatus == EstatusCruce.MONEDAS_MIXTAS)

    movs_used = set()
    for r in res_eg + res_ing:
        if r.movimiento_asignado:
            movs_used.add(id(r.movimiento_asignado))

    return {
        "FILAS_EGRESOS": len(filas_eg),
        "FILAS_INGRESOS": len(filas_ing),
        "GRUPOS_EGRESOS": len(grupos_eg),
        "GRUPOS_INGRESOS": len(grupos_ing),
        "MOVIMIENTOS_BANCARIOS": len(movimientos),
        "MOVIMIENTOS_CARGOS": len(mov_cargos),
        "MOVIMIENTOS_ABONOS": len(mov_abonos),
        "MOVIMIENTOS_TDC": len(mov_tdc),
        "CRUCES_ENCONTRADOS_EGRESOS": enc_eg,
        "CRUCES_ENCONTRADOS_INGRESOS": enc_ing,
        "CRUCES_ENCONTRADOS_TOTAL": enc_eg + enc_ing,
        "MULTIPLES_CANDIDATOS_EGRESOS": mult_eg,
        "MULTIPLES_CANDIDATOS_INGRESOS": mult_ing,
        "MULTIPLES_CANDIDATOS_TOTAL": mult_eg + mult_ing,
        "SIN_CANDIDATO_EGRESOS": sin_eg,
        "SIN_CANDIDATO_INGRESOS": sin_ing,
        "SIN_CANDIDATO_TOTAL": sin_eg + sin_ing,
        "MONEDAS_MIXTAS": mix_eg + mix_ing,
        "MOVIMIENTOS_REUTILIZADOS": 0,
        "MOVIMIENTOS_UNICOS_USADOS": len(movs_used),
        "ARCHIVO": info["archivo"],
        "TAMAÑO": info["tamaño"],
        "SHA256": info["sha256"],
        "HOJAS": info["hojas"],
        "TIEMPO": time.time() - t0,
        "grupos_eg": grupos_eg,
        "grupos_ing": grupos_ing,
        "resultados_eg": res_eg,
        "resultados_ing": res_ing,
        "cruce_map": cruce_map,
        "movimientos": movimientos,
    }
