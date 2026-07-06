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

class AmexParser(BaseBankParser):
    
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
                
                if "N" in line_upper and "MERO DE CUENTA" in line_upper and not meta["cuenta"]:
                    m = re.search(r"37\d{2}-\d{6}-\d{5}", line_upper)
                    if m: meta["cuenta"] = m.group(0)
                    
                if "DEL" in line_upper and "AL" in line_upper and "DE" in line_upper and not meta["periodo_inicio"]:
                    # Período de Facturación Del 7 de Enero al 6 de Febrero de 2024
                    m = re.search(r"DEL\s*(\d{1,2})\s*DE\s*([A-Z]+)\s*AL\s*(\d{1,2})\s*DE\s*([A-Z]+)\s*DE\s*(\d{4})", line_upper)
                    if m:
                        try:
                            meses = {"ENERO": 1, "FEBRERO": 2, "MARZO": 3, "ABRIL": 4, "MAYO": 5, "JUNIO": 6, 
                                     "JULIO": 7, "AGOSTO": 8, "SEPTIEMBRE": 9, "OCTUBRE": 10, "NOVIEMBRE": 11, "DICIEMBRE": 12}
                            
                            d_ini = int(m.group(1))
                            mes_ini = meses.get(m.group(2), 1)
                            d_fin = int(m.group(3))
                            mes_fin = meses.get(m.group(4), 1)
                            anio = int(m.group(5))
                            
                            # Ajuste de año para el inicio si cruza de año
                            anio_ini = anio
                            if mes_ini > mes_fin:
                                anio_ini -= 1
                                
                            meta["periodo_inicio"] = date(anio_ini, mes_ini, d_ini)
                            meta["periodo_fin"] = date(anio, mes_fin, d_fin)
                            meta["fecha_corte"] = meta["periodo_fin"]
                        except Exception:
                            pass
                            
                # Extraer saldos. AMEX muestra: 78,269.04 - 78,269.04 + 23,753.23 = 23,753.23
                if "=" in line_str and "-" in line_str and "+" in line_str and meta["saldo_inicial"] is None:
                    # Buscamos los 4 montos
                    montos = re.findall(r"([\d,]+\.\d{2})", line_str)
                    if len(montos) >= 4:
                        # Para una tarjeta de crédito, el saldo es una deuda, lo representamos como negativo
                        # para que cuadre la matemática base: Inicial + Pagos(Abonos) - Compras(Cargos) = Final
                        meta["saldo_inicial"] = -Decimal(str(clean_number(montos[0])))
                        meta["saldo_final"] = -Decimal(str(clean_number(montos[3])))
                            
        return meta

    def _convert_date(self, day_month: str, year: int, month: int) -> date:
        meses = {"ENERO": 1, "FEBRERO": 2, "MARZO": 3, "ABRIL": 4, "MAYO": 5, "JUNIO": 6, 
                 "JULIO": 7, "AGOSTO": 8, "SEPTIEMBRE": 9, "OCTUBRE": 10, "NOVIEMBRE": 11, "DICIEMBRE": 12}
        try:
            parts = day_month.upper().split(" DE ")
            day = int(parts[0])
            tx_month = meses.get(parts[1], 1)
            tx_year = year
            
            # Si el statement es de Enero pero la tx es de Diciembre
            if tx_month == 12 and month == 1:
                tx_year -= 1
                
            return date(tx_year, tx_month, day)
        except Exception:
            return date(year, 1, 1)

    def parse(self, filepath: str, document_uuid: str) -> CanonicalStatement:
        try:
            pages_words = extract_words_digital(filepath)
        except Exception as e:
            raise ParseError(f"No se pudo extraer texto del PDF AMEX: {str(e)}")

        meta = self._extract_metadata(pages_words)
        
        if not meta["cuenta"]:
            raise ParseError("No se pudo detectar la cuenta en AMEX.")
        if not meta["periodo_inicio"]:
            raise ParseError("No se pudo detectar el periodo en AMEX.")
        if meta["saldo_inicial"] is None:
            raise ParseError("No se pudo detectar el saldo inicial en AMEX.")
            
        year = meta["periodo_inicio"].year
        month = meta["periodo_inicio"].month

        transactions = []
        in_transactions_section = False
        current_tx = None
        tx_index = 0

        for page in pages_words:
            for line in page:
                line_str = " ".join(w['text'] for w in line)
                line_upper = line_str.upper()

                if "FECHA Y DETALLE DE LAS OPERACIONES" in line_upper:
                    in_transactions_section = True
                    continue
                    
                if "ESTE NO ES UN DOCUMENTO CON VALIDEZ FISCAL" in line_upper or "RESUMEN DE CUENTA" in line_upper:
                    if current_tx:
                        transactions.append(current_tx)
                        current_tx = None
                    in_transactions_section = False
                    continue

                if not in_transactions_section:
                    continue
                    
                if not line_str.strip():
                    continue
                    
                if "NUEVOS CARGOS Y ABONOS DE" in line_upper or "TOTAL DE LAS TRANSACCIONES" in line_upper:
                    continue
                if "N" in line_upper and "MERO DE CUENTA" in line_upper:
                    continue

                # Detectar fecha (ej: "26 de Enero")
                m_fecha = re.match(r"^(\d{1,2}\s+[D|d][E|e]\s+[A-Za-z]+)\b", line_str)
                
                if m_fecha:
                    if current_tx:
                        transactions.append(current_tx)
                        
                    # Extraer monto al final
                    m_monto = re.findall(r"([\d,]+\.\d{2})$", line_str.strip())
                    monto_val = None
                    concepto = line_str[m_fecha.end():].strip()
                    
                    if m_monto:
                        monto_val = clean_number(m_monto[0])
                        pos = concepto.rfind(m_monto[0])
                        concepto = concepto[:pos].strip()
                    
                    tx_index += 1
                    tx_uuid = f"{document_uuid}-TX-{tx_index}"
                    
                    monto_abs = Decimal(str(monto_val)) if monto_val else Decimal("0.00")
                    
                    # Por defecto en AMEX es un Cargo (Compra). Los Pagos tienen "CR" en la sig linea,
                    # o se pueden inferir al procesar la siguiente linea.
                    
                    current_tx = CanonicalTransaction(
                        uuid=tx_uuid,
                        statement_uuid=document_uuid,
                        fecha_operacion=self._convert_date(m_fecha.group(1), year, month),
                        monto_absoluto=monto_abs,
                        naturaleza="CARGO",
                        moneda="MXN",
                        concepto_original=concepto
                    )
                elif current_tx:
                    if line_upper.strip() == "CR":
                        current_tx.naturaleza = "ABONO"
                    else:
                        current_tx.concepto_original += " " + line_str.strip()

        if current_tx:
            transactions.append(current_tx)

        # Filtrar informativas y de moneda extranjera si el monto está en MXN en la tx principal
        # En AMEX, si hay una compra en USD, la siguiente linea dice "Dólar U.S.A. 29.75"
        # pero ya capturamos la línea principal con el monto en MXN.
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
            banco="AMEX",
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
