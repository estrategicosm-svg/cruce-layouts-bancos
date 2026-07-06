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

class BanregioParser(BaseBankParser):
    
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

    def _extract_metadata(self, pages_words: List[List[List[Dict]]]) -> Dict:
        meta = {
            "cuenta": "",
            "saldo_inicial": None,
            "saldo_final": None,
            "fecha_corte": None,
            "periodo_inicio": None,
            "periodo_fin": None
        }
        
        for page in pages_words:
            for line in page:
                line_str = " ".join(w['text'] for w in line)
                line_upper = line_str.upper()
                
                if "CLIENTE :" in line_upper and not meta["cuenta"]:
                    m = re.search(r"CLIENTE\s*:\s*([\w\-]+)", line_upper)
                    if m: meta["cuenta"] = m.group(1)
                    
                if "SALDO INICIAL" in line_upper and meta["saldo_inicial"] is None:
                    m = re.search(r"SALDO INICIAL\s*\$?\s*([\d,]+\.\d{2})", line_upper)
                    if m: meta["saldo_inicial"] = Decimal(str(clean_number(m.group(1))))
                    
                if "DEL" in line_upper and "AL" in line_upper and "DE" in line_upper and not meta["periodo_inicio"]:
                    # e.g., del 01 al 29 de FEBRERO 2024
                    m = re.search(r"DEL\s*(\d{1,2})\s*AL\s*(\d{1,2})\s*DE\s*([A-Z]+)\s*(\d{4})", line_upper)
                    if m:
                        try:
                            meses = {"ENE": 1, "FEB": 2, "MAR": 3, "ABR": 4, "MAY": 5, "JUN": 6, 
                                     "JUL": 7, "AGO": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DIC": 12}
                            
                            d_ini = int(m.group(1))
                            d_fin = int(m.group(2))
                            mes = meses.get(m.group(3)[:3], 1)
                            anio = int(m.group(4))
                            
                            meta["periodo_inicio"] = date(anio, mes, d_ini)
                            meta["periodo_fin"] = date(anio, mes, d_fin)
                            meta["fecha_corte"] = meta["periodo_fin"]
                        except Exception:
                            pass
                            
        return meta

    def _convert_date(self, day_str: str, year: int, month: int) -> date:
        try:
            return date(year, month, int(day_str))
        except Exception:
            return date(year, month, 1)

    def parse(self, filepath: str, document_uuid: str) -> CanonicalStatement:
        try:
            pages_words = extract_words_digital(filepath)
        except Exception as e:
            raise ParseError(f"No se pudo extraer texto del PDF Banregio: {str(e)}")

        meta = self._extract_metadata(pages_words)
        
        if not meta["cuenta"]:
            raise ParseError("No se pudo detectar la cuenta en Banregio.")
        if not meta["periodo_inicio"]:
            raise ParseError("No se pudo detectar el periodo en Banregio.")
        if meta["saldo_inicial"] is None:
            raise ParseError("No se pudo detectar el saldo inicial en Banregio.")
            
        year = meta["periodo_inicio"].year
        month = meta["periodo_inicio"].month

        columns = [
            ("Dia", 0, 60),
            ("Concepto", 60, 350),
            ("Cargo", 350, 425),
            ("Abono", 425, 500),
            ("Saldo", 500, 600)
        ]

        transactions = []
        in_transactions_section = False
        current_tx = None
        tx_index = 0

        for page in pages_words:
            for line in page:
                line_str = " ".join(w['text'] for w in line)
                line_upper = line_str.upper()

                if "DIA" in line_upper and "CONCEPTO" in line_upper and "CARGOS" in line_upper:
                    in_transactions_section = True
                    continue
                    
                if "MENSAJES IMPORTANTES" in line_upper or "EL SALDO INCLUYE LOS INTERESES" in line_upper or "PAGE" in line_upper or "NOTA IMPORTANTE" in line_upper:
                    if current_tx:
                        transactions.append(current_tx)
                        current_tx = None
                    in_transactions_section = False
                    continue

                if not in_transactions_section:
                    continue
                    
                if not line_str.strip():
                    continue

                row = self._partition_line(line, columns)
                dia_str = row.get("Dia", "").strip()
                
                # En Banregio la columna DIA empieza con un número de 2 dígitos (ej "09")
                m_dia = re.match(r"^(\d{2})\b", dia_str)
                
                if m_dia:
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
                        fecha_operacion=self._convert_date(m_dia.group(1), year, month),
                        monto_absoluto=monto_abs,
                        naturaleza=naturaleza,
                        moneda="MXN",
                        concepto_original=row.get("Concepto", "").strip()
                    )
                        
                elif current_tx:
                    concepto_extra = row.get("Concepto", "").strip()
                    if concepto_extra:
                        current_tx.concepto_original += " " + concepto_extra
                            
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
        
        # En Banregio no siempre dice explícitamente "Saldo Final" al final,
        # así que calculamos el saldo_final y verificamos si cuadra.
        cargos = sum(tx.monto_absoluto for tx in valid_transactions if tx.naturaleza == "CARGO")
        abonos = sum(tx.monto_absoluto for tx in valid_transactions if tx.naturaleza == "ABONO")
        
        # Asignar saldo_final calculado
        meta["saldo_final"] = meta["saldo_inicial"] + abonos - cargos

        statement = CanonicalStatement(
            document_uuid=document_uuid,
            banco="BANREGIO",
            cuenta=meta["cuenta"],
            periodo_inicio=meta["periodo_inicio"],
            periodo_fin=meta["periodo_fin"],
            moneda="MXN",
            saldo_inicial=meta["saldo_inicial"],
            saldo_final=meta["saldo_final"],
            transacciones=valid_transactions
        )

        self.validate_math_integrity(statement)
        return statement
