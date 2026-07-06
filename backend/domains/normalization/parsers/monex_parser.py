import re
from typing import List, Dict
from decimal import Decimal
from datetime import datetime, date

import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..')))

from domains.shared.canonical_models import CanonicalStatement, CanonicalTransaction
from domains.normalization.parsers.base_parser import BaseBankParser, ParseError
from domains.normalization.parsers.utils import extract_words_digital, clean_number
from domains.normalization.cleaners import extract_all_references

class MonexParser(BaseBankParser):
    
    def _partition_line(self, words: List[Dict], columns: List[tuple]) -> Dict[str, str]:
        row_text = {col[0]: [] for col in columns}
        split_points = []
        for i in range(len(columns) - 1):
            split_x = (columns[i][2] + columns[i+1][1]) / 2.0
            split_points.append(split_x)
            
        for w in words:
            center_x = (w['x0'] + w['x1']) / 2.0
            col_idx = len(columns) - 1
            for i, split_x in enumerate(split_points):
                if center_x < split_x:
                    col_idx = i
                    break
            col_name = columns[col_idx][0]
            row_text[col_name].append(w['text'])
            
        return {col: " ".join(words).strip() for col, words in row_text.items()}

    def _convert_date(self, day_month: str, year: int) -> date:
        meses = {"JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6, 
                 "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12,
                 "ENE": 1, "ABR": 4, "AGO": 8, "DIC": 12}
        try:
            parts = day_month.upper().split("/")
            day = int(parts[0])
            month = meses.get(parts[1][:3], 1)
            return date(year, month, day)
        except Exception:
            return date(year, 1, 1)

    def parse(self, filepath: str, document_uuid: str) -> CanonicalStatement:
        try:
            pages_words = extract_words_digital(filepath)
        except Exception as e:
            raise ParseError(f"No se pudo extraer texto del PDF Monex: {str(e)}")

        meta = {
            "cuenta": "",
            "saldo_inicial": None,
            "saldo_final": None,
            "periodo_inicio": None,
            "periodo_fin": None,
            "moneda": "MXN"
        }
        
        # Primero extraer metadata general (Periodo, Cuenta)
        for page in pages_words:
            for line in page:
                line_str = " ".join(w['text'] for w in line)
                line_upper = line_str.upper()
                
                if "CTA. CLABE:" in line_upper and not meta["cuenta"]:
                    m = re.search(r"CTA\. CLABE:\s*(\d+)", line_upper)
                    if m: meta["cuenta"] = m.group(1)
                    
                if "PERIODO:" in line_upper and not meta["periodo_inicio"]:
                    # PERIODO: Del 1 Febrero 2024 al 29 febrero 2024
                    m = re.search(r"DEL\s*(\d+)\s*([A-Z]+)\s*(\d{4})\s*AL\s*(\d+)\s*([A-Z]+)\s*(\d{4})", line_upper)
                    if m:
                        try:
                            meses = {"ENERO": 1, "FEBRERO": 2, "MARZO": 3, "ABRIL": 4, "MAYO": 5, "JUNIO": 6, 
                                     "JULIO": 7, "AGOSTO": 8, "SEPTIEMBRE": 9, "OCTUBRE": 10, "NOVIEMBRE": 11, "DICIEMBRE": 12}
                            
                            d_ini = int(m.group(1))
                            mes_ini = meses.get(m.group(2), 1)
                            anio_ini = int(m.group(3))
                            
                            d_fin = int(m.group(4))
                            mes_fin = meses.get(m.group(5), 1)
                            anio_fin = int(m.group(6))
                            
                            meta["periodo_inicio"] = date(anio_ini, mes_ini, d_ini)
                            meta["periodo_fin"] = date(anio_fin, mes_fin, d_fin)
                        except Exception:
                            pass

        if not meta["cuenta"]:
            raise ParseError("No se pudo detectar la cuenta en Monex.")
        if not meta["periodo_inicio"]:
            raise ParseError("No se pudo detectar el periodo en Monex.")

        year = meta["periodo_inicio"].year

        columns = [
            ("Fecha", 0, 80),
            ("Descripcion", 80, 220),
            ("Referencia", 220, 320),
            ("Abono", 320, 400),
            ("Cargo", 400, 480),
            ("SaldoG1", 480, 550),
            ("SaldoG2", 550, 620),
            ("SaldoDisp", 620, 720),
            ("Saldo", 720, 850)
        ]

        transactions = []
        in_transactions_section = False
        current_tx = None
        tx_index = 0
        
        # Para Monex buscaremos el bloque "Movimientos" que tiene los saldos específicos de esa moneda
        for page in pages_words:
            for line in page:
                line_str = " ".join(w['text'] for w in line)
                line_upper = line_str.upper()
                
                # Detectar moneda en curso
                if "D" in line_upper and "LAR AMERICANO AL" in line_upper:
                    meta["moneda"] = "USD"
                    
                if "SALDO INICIAL:" in line_upper and not in_transactions_section:
                    # Ej: Saldo inicial: 4,445.00
                    m = re.search(r"SALDO INICIAL:\s*\$?\s*([\d,]+\.\d{2})", line_upper)
                    if m: meta["saldo_inicial"] = Decimal(str(clean_number(m.group(1))))
                    
                if "SALDO VISTA:" in line_upper and not in_transactions_section:
                    m = re.search(r"SALDO VISTA:\s*\$?\s*([\d,]+\.\d{2})", line_upper)
                    if m: meta["saldo_final"] = Decimal(str(clean_number(m.group(1))))

                if "FECHA" in line_upper and "DESCRIPCI" in line_upper and "REFERENCIA" in line_upper:
                    in_transactions_section = True
                    continue
                    
                if "HOJA" in line_upper or "ESTADO DE CUENTA" in line_upper:
                    continue

                if not in_transactions_section:
                    continue
                    
                if "SALDO INICIAL:" in line_upper:
                    continue
                    
                if not line_str.strip():
                    continue

                row = self._partition_line(line, columns)
                fecha_str = row.get("Fecha", "").strip()
                
                # "01/Feb"
                m_fecha = re.match(r"^(\d{2}/[A-Za-z]{3})\b", fecha_str)
                
                if m_fecha:
                    if current_tx:
                        transactions.append(current_tx)
                        
                    cargo_val = clean_number(row.get("Cargo", ""))
                    abono_val = clean_number(row.get("Abono", ""))
                    
                    tx_index += 1
                    tx_uuid = f"{document_uuid}-TX-{tx_index}"
                    
                    monto_abs = Decimal("0.00")
                    naturaleza = "CARGO"
                    if cargo_val:
                        monto_abs = Decimal(str(cargo_val))
                    elif abono_val:
                        monto_abs = Decimal(str(abono_val))
                        naturaleza = "ABONO"
                        
                    current_tx = CanonicalTransaction(
                        uuid=tx_uuid,
                        statement_uuid=document_uuid,
                        fecha_operacion=self._convert_date(m_fecha.group(1), year),
                        monto_absoluto=monto_abs,
                        naturaleza=naturaleza,
                        moneda=meta["moneda"],
                        concepto_original=row.get("Descripcion", "").strip(),
                        referencia_bancaria_original=row.get("Referencia", "").strip() if row.get("Referencia", "").strip() else None
                    )
                        
                elif current_tx:
                    concepto_extra = row.get("Descripcion", "").strip()
                    ref_extra = row.get("Referencia", "").strip()
                    
                    if concepto_extra:
                        current_tx.concepto_original += " " + concepto_extra
                    if ref_extra:
                        if current_tx.referencia_bancaria_original:
                            current_tx.referencia_bancaria_original += " " + ref_extra
                        else:
                            current_tx.referencia_bancaria_original = ref_extra
                        
                    if current_tx.monto_absoluto == Decimal("0.00"):
                        cargo_val = clean_number(row.get("Cargo", ""))
                        abono_val = clean_number(row.get("Abono", ""))
                        if cargo_val:
                            current_tx.monto_absoluto = Decimal(str(cargo_val))
                            current_tx.naturaleza = "CARGO"
                        elif abono_val:
                            current_tx.monto_absoluto = Decimal(str(abono_val))
                            current_tx.naturaleza = "ABONO"

        if current_tx:
            transactions.append(current_tx)

        valid_transactions = []
        for tx in transactions:
            if tx.monto_absoluto > Decimal("0.00"):
                refs = extract_all_references(tx.concepto_original, getattr(tx, 'referencia_bancaria_original', None))
                tx.referencia_bancaria_limpia = refs["referencia_bancaria_limpia"]
                tx.clave_rastreo = refs["clave_rastreo"]
                tx.numero_operacion = refs["numero_operacion"]
                tx.autorizacion = refs["autorizacion"]
                valid_transactions.append(tx)

        statement = CanonicalStatement(
            document_uuid=document_uuid,
            banco="MONEX",
            cuenta=meta["cuenta"],
            periodo_inicio=meta["periodo_inicio"],
            periodo_fin=meta["periodo_fin"],
            moneda=meta["moneda"],
            saldo_inicial=meta["saldo_inicial"],
            saldo_final=meta["saldo_final"],
            transacciones=valid_transactions
        )

        self.validate_math_integrity(statement)
        return statement
