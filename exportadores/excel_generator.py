from __future__ import annotations

import io
from pathlib import Path

import pandas as pd
from openpyxl import Workbook
from openpyxl.utils.dataframe import dataframe_to_rows

from exportadores.formateador import aplicar_formato_basico


class ExcelGenerator:
    def generar_excel_bytes(self, datos: dict[str, pd.DataFrame]) -> bytes:
        wb = self._crear_workbook(datos)
        salida = io.BytesIO()
        wb.save(salida)
        return salida.getvalue()

    def generar_excel(self, datos: dict[str, pd.DataFrame], nombre_archivo: str) -> str:
        wb = self._crear_workbook(datos)
        Path(nombre_archivo).parent.mkdir(parents=True, exist_ok=True)
        wb.save(nombre_archivo)
        return nombre_archivo

    def _crear_workbook(self, datos: dict[str, pd.DataFrame]) -> Workbook:
        wb = Workbook()
        wb.remove(wb.active)
        orden = [
            "RESUMEN",
            "CEDULA_SAT",
            "DETALLE_XML",
            "ESTADOS_CUENTA",
            "DIFERENCIAS",
            "SIN_XML",
            "SIN_BANCO",
            "VALIDACION",
        ]
        for nombre in orden:
            df = datos.get(nombre, pd.DataFrame())
            ws = wb.create_sheet(nombre)
            if df.empty:
                ws.append(["Mensaje"])
                ws.append([f"No hay datos disponibles para {nombre}"])
            else:
                for row in dataframe_to_rows(df, index=False, header=True):
                    ws.append(row)
            aplicar_formato_basico(ws)
            ws.page_setup.orientation = "landscape"
            ws.page_setup.fitToPage = True
        return wb
