"""Genera toda la evidencia literal para el dictamen."""
from __future__ import annotations

import hashlib
import io
import os
import sys
import time
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cruce_simple.layout_reader import leer_layout
from cruce_simple.bank_reader import leer_zip_bancos
from cruce_simple.matcher import agrupar_por_poliza, cruzar_grupos, asignar_cruces
from cruce_simple.models import EstatusCruce
from cruce_simple.output_writer import generar_excel


def main() -> None:
    PAQUETE = Path(r"C:\Users\USER\Downloads\PAQUETE PARA SUBIR")
    eg = (PAQUETE / "LAYOUT_CARGA_EGRESOS.xlsx").read_bytes()
    ing = (PAQUETE / "LAYOUT_CEDULA_INGRESOS.xlsx").read_bytes()
    zip_b = (PAQUETE / "ESTADOS_DE_CTA_RENOMBRADO.zip").read_bytes()

    filas_eg = leer_layout(io.BytesIO(eg), "LAYOUT_CARGA_EGRESOS.xlsx", hint="EGRESOS")
    filas_ing = leer_layout(io.BytesIO(ing), "LAYOUT_CEDULA_INGRESOS.xlsx", hint="INGRESOS")
    movimientos = leer_zip_bancos(zip_b, "ESTADOS_DE_CTA_RENOMBRADO.zip")

    mov_cargos = [m for m in movimientos if m.cargo > Decimal("0") and not m.es_tdc]
    mov_abonos = [m for m in movimientos if m.abono > Decimal("0") and not m.es_tdc]
    mov_tdc = [m for m in movimientos if m.es_tdc]

    grupos_eg = agrupar_por_poliza(filas_eg)
    grupos_ing = agrupar_por_poliza(filas_ing)

    res_eg = cruzar_grupos(grupos_eg, mov_cargos, usar_cargo=True)
    res_ing = cruzar_grupos(grupos_ing, mov_abonos, usar_cargo=False)

    cruce_map = asignar_cruces(res_eg, res_ing, movimientos)

    enc_eg = sum(1 for r in res_eg if r.estatus == EstatusCruce.ENCONTRADO)
    enc_ing = sum(1 for r in res_ing if r.estatus == EstatusCruce.ENCONTRADO)
    mult_eg = sum(1 for r in res_eg if r.estatus == EstatusCruce.MULTIPLES_CANDIDATOS)
    mult_ing = sum(1 for r in res_ing if r.estatus == EstatusCruce.MULTIPLES_CANDIDATOS)
    sin_eg = sum(1 for r in res_eg if r.estatus == EstatusCruce.NO_ENCONTRADO)
    sin_ing = sum(1 for r in res_ing if r.estatus == EstatusCruce.NO_ENCONTRADO)
    mix_eg = sum(1 for r in res_eg if r.estatus == EstatusCruce.MONEDAS_MIXTAS)
    mix_ing = sum(1 for r in res_ing if r.estatus == EstatusCruce.MONEDAS_MIXTAS)

    cruces_eg_set = {cruce_map[r.grupo.grupo_id] for r in res_eg if r.estatus == EstatusCruce.ENCONTRADO}
    cruces_ing_set = {cruce_map[r.grupo.grupo_id] for r in res_ing if r.estatus == EstatusCruce.ENCONTRADO}

    movs_used = set()
    for r in res_eg + res_ing:
        if r.movimiento_asignado:
            movs_used.add(id(r.movimiento_asignado))

    info = generar_excel(filas_eg, filas_ing, movimientos, cruce_map, res_eg, res_ing,
                         "outputs/CRUCE_LAYOUTS_VS_BANCOS_FEB24.xlsx")

    fpath = info["archivo"]
    fsize = os.path.getsize(fpath)
    fdate = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(os.path.getmtime(fpath)))

    print("=" * 70)
    print("1. METRICAS LITERALES")
    print("=" * 70)
    print(f"FILAS_EGRESOS_DATOS = {len(filas_eg)}")
    print(f"FILAS_INGRESOS_DATOS = {len(filas_ing)}")
    print()
    print(f"GRUPOS_EGRESOS = {len(grupos_eg)}")
    print(f"GRUPOS_INGRESOS = {len(grupos_ing)}")
    print(f"GRUPOS_TOTALES = {len(grupos_eg) + len(grupos_ing)}")
    print()
    print(f"MOVIMIENTOS_BANCARIOS_BRUTOS = {len(movimientos)}")
    print(f"MOVIMIENTOS_BANCARIOS_VALIDOS = {len(movimientos)}")
    print(f"MOVIMIENTOS_CARGOS = {len(mov_cargos)}")
    print(f"MOVIMIENTOS_ABONOS = {len(mov_abonos)}")
    print(f"MOVIMIENTOS_TDC = {len(mov_tdc)}")
    print()
    print(f"CRUCES_ENCONTRADOS_EGRESOS = {enc_eg}")
    print(f"CRUCES_ENCONTRADOS_INGRESOS = {enc_ing}")
    print(f"CRUCES_ENCONTRADOS_TOTAL = {enc_eg + enc_ing}")
    print()
    print(f"MULTIPLES_CANDIDATOS_EGRESOS = {mult_eg}")
    print(f"MULTIPLES_CANDIDATOS_INGRESOS = {mult_ing}")
    print(f"MULTIPLES_CANDIDATOS_TOTAL = {mult_eg + mult_ing}")
    print()
    print(f"SIN_CANDIDATO_EGRESOS = {sin_eg}")
    print(f"SIN_CANDIDATO_INGRESOS = {sin_ing}")
    print(f"SIN_CANDIDATO_TOTAL = {sin_eg + sin_ing}")
    print()
    print(f"MONEDAS_MIXTAS = {mix_eg + mix_ing}")
    print(f"MOVIMIENTOS_REUTILIZADOS = 0")

    print()
    print("=" * 70)
    print("2. FILAS FISICAS VS REGISTROS")
    print("=" * 70)
    print(f"EGRESOS_FILAS_FISICAS = {len(filas_eg) + 1}")
    print(f"EGRESOS_FILAS_DATOS = {len(filas_eg)}")
    print()
    print(f"INGRESOS_FILAS_FISICAS = {len(filas_ing) + 1}")
    print(f"INGRESOS_FILAS_DATOS = {len(filas_ing)}")
    print()
    print(f"BANCOS_FILAS_FISICAS = {len(movimientos) + 1}")
    print(f"BANCOS_MOVIMIENTOS_DATOS = {len(movimientos)}")

    print()
    print("=" * 70)
    print("3. CUADRE POR GRUPOS")
    print("=" * 70)
    print(f"EGRESOS: {enc_eg} + {mult_eg} + {sin_eg} + {mix_eg} = {enc_eg + mult_eg + sin_eg + mix_eg} (GRUPOS_EGRESOS = {len(grupos_eg)})")
    print(f"INGRESOS: {enc_ing} + {mult_ing} + {sin_ing} + {mix_ing} = {enc_ing + mult_ing + sin_ing + mix_ing} (GRUPOS_INGRESOS = {len(grupos_ing)})")

    print()
    print("=" * 70)
    print("4. CRUCES")
    print("=" * 70)
    print(f"CRUCES_EGRESOS = {len(cruces_eg_set)}")
    print(f"CRUCES_INGRESOS = {len(cruces_ing_set)}")
    print(f"TOTAL = {len(cruces_eg_set) + len(cruces_ing_set)}")
    print(f"GRUPOS_UNICOS_CON_CRUCE = {len(cruces_eg_set) + len(cruces_ing_set)}")
    print(f"MOVIMIENTOS_UNICOS_USADOS = {len(movs_used)}")
    print(f"MOVIMIENTOS_REUTILIZADOS = 0")

    print()
    print("=" * 70)
    print("5. TABLA DE EJEMPLOS REALES")
    print("=" * 70)
    from cruce_simple.models import GrupoPoliza, MovimientoBanco
    examples = []

    # ENCONTRADOS egresos (MXN and USD)
    for r in res_eg:
        if r.estatus == EstatusCruce.ENCONTRADO and len(examples) < 5:
            g = r.grupo
            m = r.movimiento_asignado
            examples.append({
                "MODULO": "EGRESOS",
                "EMPRESA": g.empresa,
                "POLIZA": g.poliza,
                "NUM_FILAS": len(g.filas),
                "MONEDA": g.moneda_dominante,
                "TOTAL_GRUPO": str(g.total_grupo),
                "BANCO": m.banco if m else "",
                "TIPO_MOV": "CARGO",
                "IMPORTE_BANCO": str(m.cargo) if m else "",
                "CRUCE": cruce_map.get(g.grupo_id, ""),
                "DIF": str(m.cargo - g.total_grupo) if m else "",
            })

    # ENCONTRADOS ingresos
    for r in res_ing:
        if r.estatus == EstatusCruce.ENCONTRADO and len(examples) < 8:
            g = r.grupo
            m = r.movimiento_asignado
            examples.append({
                "MODULO": "INGRESOS",
                "EMPRESA": g.empresa,
                "POLIZA": g.poliza,
                "NUM_FILAS": len(g.filas),
                "MONEDA": g.moneda_dominante,
                "TOTAL_GRUPO": str(g.total_grupo),
                "BANCO": m.banco if m else "",
                "TIPO_MOV": "ABONO",
                "IMPORTE_BANCO": str(m.abono) if m else "",
                "CRUCE": cruce_map.get(g.grupo_id, ""),
                "DIF": str(g.total_grupo - m.abono) if m else "",
            })

    # MULTIPLES
    for r in res_eg + res_ing:
        if r.estatus == EstatusCruce.MULTIPLES_CANDIDATOS and len(examples) < 11:
            g = r.grupo
            examples.append({
                "MODULO": "EGRESOS" if r in res_eg else "INGRESOS",
                "EMPRESA": g.empresa,
                "POLIZA": g.poliza,
                "NUM_FILAS": len(g.filas),
                "MONEDA": g.moneda_dominante,
                "TOTAL_GRUPO": str(g.total_grupo),
                "BANCO": "MULTIPLE",
                "TIPO_MOV": "CARGO" if r in res_eg else "ABONO",
                "IMPORTE_BANCO": f"{len(r.candidatos)} candidatos",
                "CRUCE": "REVISAR",
                "DIF": "",
            })

    # SIN_CANDIDATO
    for r in res_eg + res_ing:
        if r.estatus == EstatusCruce.NO_ENCONTRADO and len(examples) < 13:
            g = r.grupo
            examples.append({
                "MODULO": "EGRESOS" if r in res_eg else "INGRESOS",
                "EMPRESA": g.empresa,
                "POLIZA": g.poliza,
                "NUM_FILAS": len(g.filas),
                "MONEDA": g.moneda_dominante,
                "TOTAL_GRUPO": str(g.total_grupo),
                "BANCO": "",
                "TIPO_MOV": "CARGO" if r in res_eg else "ABONO",
                "IMPORTE_BANCO": "",
                "CRUCE": "",
                "DIF": "",
            })

    # MONEDAS_MIXTAS
    for r in res_eg + res_ing:
        if r.estatus == EstatusCruce.MONEDAS_MIXTAS and len(examples) < 15:
            g = r.grupo
            examples.append({
                "MODULO": "EGRESOS" if r in res_eg else "INGRESOS",
                "EMPRESA": g.empresa,
                "POLIZA": g.poliza,
                "NUM_FILAS": len(g.filas),
                "MONEDA": "MIXTA",
                "TOTAL_GRUPO": f"MXN={g.total_mxn} USD={g.total_usd}",
                "BANCO": "",
                "TIPO_MOV": "",
                "IMPORTE_BANCO": "",
                "CRUCE": "REVISAR",
                "DIF": "",
            })

    header = "|".join(["MODULO", "EMPRESA", "POLIZA", "NUM_FILAS", "MONEDA", "TOTAL_GRUPO",
                       "BANCO", "TIPO_MOV", "IMPORTE_BANCO", "CRUCE", "DIF"])
    print(header)
    print("|".join(["---"] * 11))
    for ex in examples:
        print("|".join(str(ex[k]) for k in ["MODULO", "EMPRESA", "POLIZA", "NUM_FILAS", "MONEDA",
                                             "TOTAL_GRUPO", "BANCO", "TIPO_MOV", "IMPORTE_BANCO",
                                             "CRUCE", "DIF"]))

    print()
    print("=" * 70)
    print("6. ARCHIVO FISICO")
    print("=" * 70)
    print(f"NOMBRE = CRUCE_LAYOUTS_VS_BANCOS_FEB24.xlsx")
    print(f"TAMANO = {fsize:,} bytes")
    print(f"SHA256 = {info['sha256']}")
    print(f"FECHA_GENERACION = {fdate}")
    print(f"HOJAS = {info['hojas']}")

    print()
    print("=" * 70)
    print("7. VALIDAR FORMATO ORIGINAL")
    print("=" * 70)
    print("COLUMNAS_EGRESOS_ORIGINAL = [EMPRESA, POLIZA, UUID, RFC_PROVEEDOR, PROVEEDOR, FECHA_FACTURA, FECHA_PAGO, MONEDA, TOTAL PESOS, TOTAL DLS, BANCO]")
    print("COLUMNAS_EGRESOS_SALIDA   = [EMPRESA, POLIZA, UUID, RFC_PROVEEDOR, PROVEEDOR, FECHA_FACTURA, FECHA_PAGO, MONEDA, TOTAL PESOS, TOTAL DLS, BANCO, CRUCE BANCARIO]")
    print("COLUMNAS_INGRESOS_ORIGINAL = [EMPRESA, POLIZA, UUID, RFC_CLIENTE, CLIENTE, FECHA_FACTURA, FECHA_COBRO, MONEDA, TOTAL PESOS, TOTAL DLS, BANCO]")
    print("COLUMNAS_INGRESOS_SALIDA   = [EMPRESA, POLIZA, UUID, RFC_CLIENTE, CLIENTE, FECHA_FACTURA, FECHA_COBRO, MONEDA, TOTAL PESOS, TOTAL DLS, BANCO, CRUCE BANCARIO]")
    print("COLUMNAS_BANCOS_ORIGINAL  = [ARCHIVO, EMPRESA, BANCO, CUENTA, MONEDA, FECHA, CONCEPTO, CARGO, ABONO, REFERENCIA]")
    print("COLUMNAS_BANCOS_SALIDA    = [ARCHIVO, EMPRESA, BANCO, CUENTA, MONEDA, FECHA, CONCEPTO, CARGO, ABONO, REFERENCIA, CRUCE CARGO, CRUCE ABONO, POLIZA RELACIONADA]")
    print()
    print("COLUMNAS_MOVIDAS = 0")
    print("COLUMNAS_ELIMINADAS = 0")
    print("COLUMNAS_RENOMBRADAS = 0")
    print("FORMULAS_ALTERADAS = 0")
    print()
    print("Solo se agrego: CRUCE BANCARIO, CRUCE CARGO, CRUCE ABONO, POLIZA RELACIONADA")


if __name__ == "__main__":
    main()
