import os
import tempfile
import re
import pandas as pd
from parsers.legacy_pdf_engine import process_single_pdf

class BancoPDFParser:
    COLUMNAS_ESPERADAS = [
        'Archivo Origen', 'Banco', 'Cuenta', 'Moneda', 'Fecha',
        'Concepto', 'Cargo', 'Abono', 'Saldo', 'Referencia_Bancaria_Limpia'
    ]
    
    BANCOS_RIESGOSOS = ['BAJIO', 'INTERCAM', 'BANAMEX', 'IBC', 'BANREGIO']

    def parsear_pdf(self, file_bytes, original_filename: str):
        # Guardar en archivo temporal
        fd, tmp_path = tempfile.mkstemp(suffix=".pdf")
        with os.fdopen(fd, 'wb') as f:
            f.write(file_bytes)
            
        try:
            # Invocar al motor legado
            resultado = process_single_pdf(tmp_path)
        except Exception as e:
            os.remove(tmp_path)
            return pd.DataFrame(columns=self.COLUMNAS_ESPERADAS), {
                "valido": False,
                "advertencias": [f"Error interno del motor PDF: {str(e)}"]
            }
            
        # Limpiar
        os.remove(tmp_path)
        
        recap = resultado.get("recap", {})
        movs = resultado.get("transacciones", [])
        real_movs = [m for m in movs if m.get("es_movimiento_real", True)]
        
        df_movs = pd.DataFrame(real_movs)
        df_export = pd.DataFrame(columns=self.COLUMNAS_ESPERADAS)
        
        banco_detectado = recap.get("banco", "DESCONOCIDO")
        
        if not df_movs.empty:
            df_export['Archivo Origen'] = [original_filename] * len(real_movs)
            df_export['Banco'] = [banco_detectado] * len(real_movs)
            df_export['Cuenta'] = [recap.get("cuenta", "")] * len(real_movs)
            df_export['Moneda'] = [recap.get("moneda", "MXN")] * len(real_movs)
            
            
            df_export['Fecha'] = df_movs.get('fecha', pd.Series([None]*len(real_movs)))
            df_export['Concepto'] = df_movs.get('concepto', pd.Series(['']*len(real_movs)))
            
            # Buscar referencia limpia dentro del concepto sin alterarlo
            referencias_limpias = []
            for concepto in df_export['Concepto']:
                texto = str(concepto).upper()
                ref = ""
                # Intentar buscar palabra clave
                match_kw = re.search(r'\b(?:REF|REFERENCIA|CVE|RASTREO|AUT)\s*:?\s*([A-Z0-9]{6,20})\b', texto)
                if match_kw:
                    ref = match_kw.group(1)
                else:
                    # Intentar buscar secuencia numérica larga típica de referencia
                    match_num = re.search(r'\b(\d{7,20})\b', texto)
                    if match_num:
                        ref = match_num.group(1)
                referencias_limpias.append(ref)
                
            df_export['Referencia_Bancaria_Limpia'] = referencias_limpias
            
            df_export['Cargo'] = df_movs.get('cargo', pd.Series([0]*len(real_movs)))
            df_export['Abono'] = df_movs.get('abono', pd.Series([0]*len(real_movs)))
            df_export['Saldo'] = df_movs.get('saldo', pd.Series([0]*len(real_movs)))
            
        # Ejecutar validaciones
        validacion = self._validar_extraccion(df_export, banco_detectado)
        
        return df_export, validacion
        
    def _validar_extraccion(self, df: pd.DataFrame, banco: str) -> dict:
        advertencias = []
        valido = True
        
        if df.empty:
            return {"valido": False, "advertencias": ["No se extrajeron movimientos del PDF (0 filas)."]}
            
        # Validar banco riesgoso
        banco_upper = str(banco).upper()
        if any(b in banco_upper for b in self.BANCOS_RIESGOSOS):
            advertencias.append(f"Banco {banco} requiere revisión manual (posibles fallas de precisión o referencias vacías).")
            valido = False
            
        # Validar cargos/abonos todos en 0
        df['Cargo'] = pd.to_numeric(df['Cargo'], errors='coerce').fillna(0)
        df['Abono'] = pd.to_numeric(df['Abono'], errors='coerce').fillna(0)
        
        total_cargos = df['Cargo'].sum()
        total_abonos = df['Abono'].sum()
        
        if total_cargos == 0 and total_abonos == 0:
            advertencias.append("Todos los montos (Cargos y Abonos) están en cero.")
            valido = False
            
        # Validar montos inflados (Heurística: > 100 millones puede ser lectura sucia de BAJIO)
        if total_cargos > 100_000_000 or total_abonos > 100_000_000:
            advertencias.append("Montos detectados extremadamente altos (posible ruido de OCR o cuenta extraída como saldo).")
            valido = False
            
        # Validar referencias
        referencias_vacias = df['Referencia_Bancaria_Limpia'].isna() | (df['Referencia_Bancaria_Limpia'].astype(str).str.strip() == '')
        porcentaje_vacias = referencias_vacias.sum() / len(df)
        if porcentaje_vacias > 0.8:
            advertencias.append(f"El {porcentaje_vacias*100:.0f}% de los movimientos no tiene referencia bancaria detectada.")
            valido = False
            
        # Moneda
        if df['Moneda'].iloc[0] == "NO_IDENTIFICADA" or not df['Moneda'].iloc[0]:
            advertencias.append("Moneda no detectada. Se asumirá MXN.")
            
        return {
            "valido": valido,
            "advertencias": advertencias,
            "total_cargos": total_cargos,
            "total_abonos": total_abonos,
            "total_movimientos": len(df)
        }
