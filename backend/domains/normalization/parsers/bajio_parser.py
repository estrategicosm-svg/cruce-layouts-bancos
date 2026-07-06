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

class BajioParser(BaseBankParser):
    
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
                
                if "CUENTA CONECTA BANBAJIO" in line_upper and not meta["cuenta"]:
                    m = re.search(r"CUENTA CONECTA BANBAJIO\s*(\d+)", line_upper)
                    if m: meta["cuenta"] = m.group(1)
                    
                if "SALDO ANTERIOR" in line_upper and "DEPOSITOS" in line_upper:
                    pass # This is the header
                    
                # Look for the balances line: $ 4,678.79 $ 530,933.66 $ 529,533.35 $ 6,079.10
                m_bals = re.search(r"\$\s*([\d,]+\.\d{2})\s*\$\s*([\d,]+\.\d{2})\s*\$\s*([\d,]+\.\d{2})\s*\$\s*([\d,]+\.\d{2})", line_upper)
                if m_bals and "SALDO" not in line_upper and meta["saldo_inicial"] is None:
                    meta["saldo_inicial"] = Decimal(str(clean_number(m_bals.group(1))))
                    meta["saldo_final"] = Decimal(str(clean_number(m_bals.group(4))))
                    
                if "PERIODO:" in line_upper and not meta["periodo_inicio"]:
                    m = re.search(r"PERIODO:\s*(\d{1,2})\s*DE\s*([A-Z]+)\s*AL\s*(\d{1,2})\s*DE\s*([A-Z]+)\s*DE\s*(\d{4})", line_upper)
                    if m:
                        try:
                            meses = {"ENE": 1, "FEB": 2, "MAR": 3, "ABR": 4, "MAY": 5, "JUN": 6, 
                                     "JUL": 7, "AGO": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DIC": 12}
                            
                            d_ini = int(m.group(1))
                            mes_ini = meses.get(m.group(2)[:3], 1)
                            d_fin = int(m.group(3))
                            mes_fin = meses.get(m.group(4)[:3], 1)
                            anio = int(m.group(5))
                            
                            meta["periodo_inicio"] = date(anio, mes_ini, d_ini)
                            meta["periodo_fin"] = date(anio, mes_fin, d_fin)
                            meta["fecha_corte"] = meta["periodo_fin"]
                        except Exception:
                            pass
                            
        return meta

    def _convert_date(self, day_month: str, year: int) -> date:
        meses = {"ENE": 1, "FEB": 2, "MAR": 3, "ABR": 4, "MAY": 5, "JUN": 6, 
                 "JUL": 7, "AGO": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DIC": 12}
        try:
            parts = day_month.upper().split()
            day = int(parts[0])
            month = meses.get(parts[1][:3], 1)
            return date(year, month, day)
        except Exception:
            return date(year, 1, 1)

    def parse(self, filepath: str, document_uuid: str) -> CanonicalStatement:
        try:
            pages_words = extract_words_digital(filepath)
        except Exception as e:
            raise ParseError(f"No se pudo extraer texto del PDF Bajio: {str(e)}")

        meta = self._extract_metadata(pages_words)
        
        if not meta["cuenta"]:
            raise ParseError("No se pudo detectar la cuenta en Bajio.")
        if not meta["periodo_inicio"]:
            raise ParseError("No se pudo detectar el periodo en Bajio.")
        if meta["saldo_inicial"] is None:
            raise ParseError("No se pudo detectar el saldo inicial en Bajio.")
            
        year = meta["periodo_inicio"].year

        columns = [
            ("Fecha", 0, 60),
            ("Docto", 60, 130),
            ("Concepto", 130, 380),
            ("Abono", 380, 450),
            ("Cargo", 450, 520),
            ("Saldo", 520, 600)
        ]

        transactions = []
        in_transactions_section = False
        current_tx = None
        tx_index = 0

        for page in pages_words:
            for line in page:
                line_str = " ".join(w['text'] for w in line)
                line_upper = line_str.upper()
                
                # Ignorar encabezados altos
                if line[0]['top'] < 100:
                    continue

                if "FECHA" in line_upper and "DESCRIPCION DE LA OPERACION" in line_upper:
                    in_transactions_section = True
                    continue
                    
                if "ESTE DOCUMENTO ES UNA REPRESENTACION" in line_upper or "RESUMEN DE COMISIONES" in line_upper:
                    if current_tx:
                        transactions.append(current_tx)
                        current_tx = None
                    in_transactions_section = False
                    continue

                if not in_transactions_section:
                    continue
                    
                if "SALDO INICIAL" in line_upper:
                    continue
                    
                if not line_str.strip():
                    continue

                row = self._partition_line(line, columns)
                fecha_str = row.get("Fecha", "").strip()
                
                # En Bajio: "1 FEB"
                m_fecha = re.match(r"^(\d{1,2}\s+[A-Z]{3})\b", fecha_str.upper())
                
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
                        moneda="MXN",
                        concepto_original=row.get("Concepto", "").strip(),
                        referencia_bancaria_original=row.get("Docto", "").strip() if row.get("Docto", "").strip() else None
                    )
                        
                elif current_tx:
                    concepto_extra = row.get("Concepto", "").strip()
                    docto_extra = row.get("Docto", "").strip()
                    
                    if concepto_extra:
                        current_tx.concepto_original += " " + concepto_extra
                    if docto_extra:
                        # Para Bajío, a veces Docto es la referencia u operacion
                        if current_tx.referencia_bancaria_original:
                            current_tx.referencia_bancaria_original += " " + docto_extra
                        else:
                            current_tx.referencia_bancaria_original = docto_extra
                            
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
            banco="BAJIO",
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
