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

class IBCParser(BaseBankParser):
    
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
                
                if "CUSTOMER NUMBER:" in line_upper and not meta["cuenta"]:
                    m = re.search(r"CUSTOMER NUMBER:\s*(\d+)", line_upper)
                    if m: meta["cuenta"] = m.group(1)
                    
                if "STATEMENT PERIOD:" in line_upper and not meta["periodo_inicio"]:
                    m = re.search(r"(\d{2}/\d{2}/\d{4})\s*-\s*(\d{2}/\d{2}/\d{4})", line_upper)
                    if m:
                        try:
                            meta["periodo_inicio"] = datetime.strptime(m.group(1), "%m/%d/%Y").date()
                            meta["periodo_fin"] = datetime.strptime(m.group(2), "%m/%d/%Y").date()
                            meta["fecha_corte"] = meta["periodo_fin"]
                        except Exception:
                            pass
                            
                # Recap balances
                # Beginning Balance / Credits / Debits / Closing Balance
                # 25,151.02 7 108,791.14 5 132,005.00 1,937.16
                m_recap = re.search(r"^\s*([\d,]+\.\d{2})\s+(\d+)\s+([\d,]+\.\d{2})\s+(\d+)\s+([\d,]+\.\d{2})\s+([\d,]+\.\d{2})\s*$", line_str)
                if m_recap and meta["saldo_inicial"] is None:
                    meta["saldo_inicial"] = Decimal(str(clean_number(m_recap.group(1))))
                    meta["saldo_final"] = Decimal(str(clean_number(m_recap.group(6))))
                            
        return meta

    def _convert_date(self, day_month: str, year: int) -> date:
        try:
            parts = day_month.split("/")
            return date(year, int(parts[0]), int(parts[1]))
        except Exception:
            return date(year, 1, 1)

    def parse(self, filepath: str, document_uuid: str) -> CanonicalStatement:
        try:
            pages_words = extract_words_digital(filepath)
        except Exception as e:
            raise ParseError(f"No se pudo extraer texto del PDF IBC: {str(e)}")

        meta = self._extract_metadata(pages_words)
        
        if not meta["cuenta"]:
            raise ParseError("No se pudo detectar la cuenta en IBC.")
        if not meta["periodo_inicio"]:
            raise ParseError("No se pudo detectar el periodo en IBC.")
        if meta["saldo_inicial"] is None:
            raise ParseError("No se pudo detectar el saldo inicial en IBC.")
            
        year = meta["periodo_inicio"].year

        transactions = []
        current_section = "OTHER"
        tx_index = 0

        for page in pages_words:
            # Reset section on each page, but usually sections span or are explicitly named
            current_section = "OTHER"
            for line in page:
                line_str = " ".join(w['text'] for w in line).strip()
                line_upper = line_str.upper()

                if not line_str or "CUSTOMER NUMBER:" in line_upper or "STATEMENT DATE:" in line_upper or "STATEMENT PERIOD:" in line_upper or "PAGE NUMBER:" in line_upper:
                    continue
                    
                if "DAILY ENDING BALANCE" in line_upper or "DAILY BALANCE" in line_upper:
                    current_section = "DAILY_BALANCE"
                    continue
                elif "ELECTRONIC ACTIVITY" in line_upper:
                    current_section = "ELECTRONIC_ACTIVITY"
                    continue
                elif "DEPOSITS (CREDITS)" in line_upper or "DEPOSITS" in line_upper:
                    if "RECAP" in line_upper or "BEGINNING" in line_upper or "NUMBER OF" in line_upper:
                        pass
                    else:
                        current_section = "DEPOSITS"
                        continue
                elif "DEBITS" in line_upper or "WITHDRAWALS" in line_upper:
                    if "RECAP" in line_upper or "BEGINNING" in line_upper or "NUMBER OF" in line_upper:
                        pass
                    else:
                        current_section = "DEBITS"
                        continue
                elif "BALANCE SUMMARY" in line_upper or "AVERAGE COLLECTED" in line_upper:
                    current_section = "OTHER"
                    continue
                    
                if current_section == "DEPOSITS":
                    # Formato: 02/02 8,200.00 02/02 5,100.00
                    tokens = line_str.split()
                    i = 0
                    while i < len(tokens) - 1:
                        if re.match(r"^\d{2}/\d{2}$", tokens[i]):
                            m_date = tokens[i]
                            val = clean_number(tokens[i+1])
                            if val:
                                tx_index += 1
                                transactions.append(CanonicalTransaction(
                                    uuid=f"{document_uuid}-TX-{tx_index}",
                                    statement_uuid=document_uuid,
                                    fecha_operacion=self._convert_date(m_date, year),
                                    monto_absoluto=Decimal(str(val)),
                                    naturaleza="ABONO",
                                    moneda="USD", # Usually IBC is USD
                                    concepto_original="Deposit"
                                ))
                                i += 2
                                continue
                        i += 1
                        
                elif current_section in ["ELECTRONIC_ACTIVITY", "DEBITS"]:
                    if line_upper.startswith("CREDITS") or "DATE DESCRIPTION AMOUNT" in line_upper:
                        continue
                        
                    # Buscar fecha MM/DD al inicio
                    m_date = re.match(r"^(\d{2}/\d{2})\b", line_str)
                    if m_date:
                        date_str = m_date.group(1)
                        rest = line_str[m_date.end():].strip()
                        
                        # Buscar monto al final
                        amounts = re.findall(r"([\d,]+\.\d{2})", rest)
                        if amounts:
                            amount_str = amounts[-1]
                            amount_val = clean_number(amount_str)
                            
                            # Concepto es el resto
                            pos = rest.rfind(amount_str)
                            concept_str = rest[:pos].strip()
                            
                            if amount_val:
                                tx_index += 1
                                naturaleza = "ABONO" if current_section == "ELECTRONIC_ACTIVITY" else "CARGO"
                                
                                tx = CanonicalTransaction(
                                    uuid=f"{document_uuid}-TX-{tx_index}",
                                    statement_uuid=document_uuid,
                                    fecha_operacion=self._convert_date(date_str, year),
                                    monto_absoluto=Decimal(str(amount_val)),
                                    naturaleza=naturaleza,
                                    moneda="USD",
                                    concepto_original=concept_str
                                )
                                transactions.append(tx)

        valid_transactions = []
        for tx in transactions:
            if tx.monto_absoluto > Decimal("0.00"):
                refs = extract_all_references(tx.concepto_original, getattr(tx, 'referencia_bancaria_original', None))
                tx.referencia_bancaria_limpia = refs["referencia_bancaria_limpia"]
                tx.clave_rastreo = refs["clave_rastreo"]
                tx.numero_operacion = refs["numero_operacion"]
                tx.autorizacion = refs["autorizacion"]
                valid_transactions.append(tx)

        # Usar USD como default para IBC, o tomar de un metadata config (pero por ahora hardcoded USD como moneda principal en frontera)
        # Check if the text implies MXN?
        moneda_detectada = "USD"
        
        statement = CanonicalStatement(
            document_uuid=document_uuid,
            banco="IBC",
            cuenta=meta["cuenta"],
            periodo_inicio=meta["periodo_inicio"],
            periodo_fin=meta["periodo_fin"],
            moneda=moneda_detectada,
            saldo_inicial=meta["saldo_inicial"],
            saldo_final=meta["saldo_final"],
            transacciones=valid_transactions
        )

        self.validate_math_integrity(statement)
        return statement
