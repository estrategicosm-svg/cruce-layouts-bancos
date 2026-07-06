import os
path = r'C:\Users\USER\OneDrive - Sinergy IE SC\Documentos\11_CEDULA_IVA\sat_conciliador_iva\parsers\legacy_pdf_engine.py'
with open(path, 'r', encoding='utf-8') as f:
    text = f.read()

target = """            is_new_tx = False
            fecha_clean = ""
            
            match_rnu = REGEX_RNU.search(concept_col)
            if match_rnu:
                is_new_tx = True
                day, month, year = match_rnu.groups()
                fecha_clean = f"{day.zfill(2)}/{month.zfill(2)}/20{year}"
            elif REGEX_FECHA.match(fecha_col.upper()):
                is_new_tx = True
                fecha_clean = fecha_col
                
            if is_new_tx:
                if current_tx:
                    transactions.append(current_tx)
                    
                cargo_val = clean_number(row_text.get("Cargo"))
                abono_val = clean_number(row_text.get("Abono"))
                saldo_val = clean_number(row_text.get("Saldo"))
                
                cargo_words = row_words.get("Cargo", [])
                abono_words = row_words.get("Abono", [])
                all_m_words = cargo_words + abono_words
                c_conf = np.mean([w['conf'] for w in all_m_words]) if all_m_words else 100.0
                
                imp1 = line_amounts[0][0] if len(line_amounts) >= 1 else None
                imp2 = line_amounts[1][0] if len(line_amounts) >= 2 else None
                imp3 = line_amounts[2][0] if len(line_amounts) >= 3 else None
                
                current_tx = {
                    'banco': 'INTERCAM',
                    'archivo': file_name,
                    'pagina': page_num,
                    'metodo': method_used,
                    'fecha': fecha_clean,
                    'concepto': concept_col,
                    'cargo': cargo_val,
                    'abono': abono_val,
                    'saldo': saldo_val,
                    'seccion_origen': '',
                    'importe_detectado': cargo_val if cargo_val is not None else abono_val,
                    'importe_1': imp1,
                    'importe_2': imp2,
                    'importe_3': imp3,
                    'original_fecha': fecha_col,
                    'original_concepto': concept_col,
                    'original_cargo': row_text.get("Cargo", ""),
                    'original_abono': row_text.get("Abono", ""),
                    'original_saldo': row_text.get("Saldo", ""),
                    'confianza': c_conf,
                    'advertencias': []
                }
                continue
                
            if current_tx:
                cargo_val = clean_number(row_text.get("Cargo"))
                abono_val = clean_number(row_text.get("Abono"))
                if cargo_val and current_tx['cargo'] is None:
                    current_tx['cargo'] = cargo_val
                if abono_val and current_tx['abono'] is None:
                    current_tx['abono'] = abono_val
                if concept_col:
                    current_tx['concepto'] += " " + concept_col
                    current_tx['original_concepto'] += " " + concept_col
                continue"""

replacement = """            cargo_val = clean_number(row_text.get("Cargo"))
            abono_val = clean_number(row_text.get("Abono"))
            saldo_val = clean_number(row_text.get("Saldo"))
            
            is_new_tx = False
            fecha_clean = ""
            
            if (cargo_val and abs(cargo_val) > 0.001) or (abono_val and abs(abono_val) > 0.001):
                is_new_tx = True
            
            match_rnu = REGEX_RNU.search(concept_col)
            if match_rnu:
                day, month, year = match_rnu.groups()
                fecha_clean = f"{day.zfill(2)}/{month.zfill(2)}/20{year}"
                if current_tx and not current_tx['fecha']:
                    current_tx['fecha'] = fecha_clean
            elif REGEX_FECHA.match(fecha_col.upper()):
                fecha_clean = fecha_col
                if current_tx and not current_tx['fecha']:
                    current_tx['fecha'] = fecha_clean
                
            if is_new_tx:
                if current_tx:
                    transactions.append(current_tx)
                    
                cargo_words = row_words.get("Cargo", [])
                abono_words = row_words.get("Abono", [])
                all_m_words = cargo_words + abono_words
                c_conf = np.mean([w['conf'] for w in all_m_words]) if all_m_words else 100.0
                
                imp1 = line_amounts[0][0] if len(line_amounts) >= 1 else None
                imp2 = line_amounts[1][0] if len(line_amounts) >= 2 else None
                imp3 = line_amounts[2][0] if len(line_amounts) >= 3 else None
                
                current_tx = {
                    'banco': 'INTERCAM',
                    'archivo': file_name,
                    'pagina': page_num,
                    'metodo': method_used,
                    'fecha': fecha_clean,
                    'concepto': concept_col,
                    'cargo': cargo_val,
                    'abono': abono_val,
                    'saldo': saldo_val,
                    'seccion_origen': '',
                    'importe_detectado': cargo_val if cargo_val is not None else abono_val,
                    'importe_1': imp1,
                    'importe_2': imp2,
                    'importe_3': imp3,
                    'original_fecha': fecha_col,
                    'original_concepto': concept_col,
                    'original_cargo': row_text.get("Cargo", ""),
                    'original_abono': row_text.get("Abono", ""),
                    'original_saldo': row_text.get("Saldo", ""),
                    'confianza': c_conf,
                    'advertencias': []
                }
                continue
                
            if current_tx:
                if concept_col:
                    current_tx['concepto'] += " " + concept_col
                    current_tx['original_concepto'] += " " + concept_col
                continue"""

text = text.replace(target, replacement)

with open(path, 'w', encoding='utf-8') as f:
    f.write(text)
print("Replaced loop successfully!")
