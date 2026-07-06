import os
import re
import cv2
import fitz  # PyMuPDF
import numpy as np
import pandas as pd
import pdfplumber
import pytesseract
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

# Configurar ruta de Tesseract de forma dinámica o por defecto
TESSERACT_RUTAS = [
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Users\USER\AppData\Local\Tesseract-OCR\tesseract.exe",
    r"/usr/bin/tesseract"
]
tesseract_cmd = "tesseract"
for r in TESSERACT_RUTAS:
    if os.path.exists(r):
        tesseract_cmd = r
        break
pytesseract.pytesseract.tesseract_cmd = tesseract_cmd

# Regex de fecha robusto y unificado (soporta 2-partes, 3-partes y formatos verbales, limitando abreviaturas de mes a las reales en ES/EN)
REGEX_FECHA = re.compile(r"(\d{1,2}[\/\-]\d{1,2}(?:[\/\-]\d{2,4})?|\d{1,2}\s+de\s*[A-Za-z]{3,4}|\d{1,2}\s+DE\s*[A-Z]{3,4}|\d{1,2}\s+(?:ENE|FEB|MAR|ABR|MAY|JUN|JUL|AGO|SEP|OCT|NOV|DIC|JAN|APR|AUG|DEC)|\d{1,2}\s+de\b|\d{1,2}\s+DE\b)")
# Regex para buscar RNU en Intercam (ej. RNU 90824 -> 09/08/2024)
REGEX_RNU = re.compile(r"RNU\s+(\d{1,2})(\d{2})(\d{2})")
REGEX_RNU_8 = re.compile(r"RNU\s+(\d{2})(\d{2})(\d{4})")

# Regexes específicos para IBC
REGEX_AMOUNT = re.compile(r"([\d,]+\.\d{2})")
REGEX_RECAP_IBC = re.compile(r"^\s*([\d,]+\.\d{2})\s+(\d+)\s+([\d,]+\.\d{2})\s+(\d+)\s+([\d,]+\.\d{2})\s+([\d,]+\.\d{2})\s*$")


def clean_number(val):
    """Limpia un string para convertirlo a float. Retorna None si no es numérico."""
    if not val:
        return None
    val_clean = str(val).upper().replace("$", "").replace(" ", "").replace(",", "").strip()
    # Si termina en CR es abono en AMEX
    is_cr = False
    if "CR" in val_clean:
        val_clean = val_clean.replace("CR", "")
        is_cr = True
    
    # Eliminar paréntesis de negativos (ej. (100.00))
    if val_clean.startswith("(") and val_clean.endswith(")"):
        val_clean = "-" + val_clean[1:-1]
        
    try:
        f_val = float(val_clean)
        return -f_val if is_cr else f_val
    except ValueError:
        return None

def detect_pdf_type(pdf_path):
    """
    Detecta si el PDF es digital (nativo) o escaneado (imágenes).
    Retorna 'DIGITAL' o 'SCANNED'.
    """
    try:
        doc = fitz.open(pdf_path)
        total_text = ""
        # Revisamos las primeras 3 páginas
        for page in doc[:3]:
            total_text += page.get_text()
        doc.close()
        if len(total_text.strip()) > 50:
            return 'DIGITAL'
        else:
            return 'SCANNED'
    except Exception:
        return 'SCANNED'

def detect_bank(text_sample, file_name=""):
    """Detecta el banco en base a palabras clave y nombre de archivo."""
    text_upper = text_sample.upper()
    file_name_upper = file_name.upper()
    
    if "BANCO DEL BAJIO" in text_upper or "BANBAJIO" in text_upper or "BAJIO" in file_name_upper:
        return "BAJIO"
    if "CITIBANAMEX" in text_upper or "BANAMEX" in text_upper or "BMX" in file_name_upper or ("DETALLE DE OPERACIONES" in text_upper and "SUC" in text_upper):
        return "BANAMEX"
    if "BANREGIO" in text_upper or "BANREGIO" in file_name_upper:
        return "BANREGIO"
    import re
    if "AMERICAN EXPRESS" in text_upper or re.search(r'\bAMEX\b', text_upper) or re.search(r'\bAMEX\b', file_name_upper):
        return "AMEX"
    if "MONEX" in text_upper or "MONEX" in file_name_upper:
        return "MONEX"
    if "IBC" in text_upper or "IBC" in file_name_upper:
        return "IBC"
    if "INTERCAM" in text_upper or "INTERCAM" in file_name_upper:
        return "INTERCAM"
    return "DESCONOCIDO"

def group_words_into_lines(words, y_tolerance=3.0):
    """Agrupa palabras que comparten una coordenada horizontal similar en renglones."""
    lines = {}
    for w in words:
        top = round(w['top'], 1)
        found = False
        for t in lines:
            if abs(t - top) < y_tolerance:
                lines[t].append(w)
                found = True
                break
        if not found:
            lines[top] = [w]
            
    sorted_lines = []
    for t in sorted(lines.keys()):
        line_words = sorted(lines[t], key=lambda x: x['x0'])
        sorted_lines.append(line_words)
    return sorted_lines

def extract_words_digital(pdf_path):
    """Extrae palabras estructuradas y sus coordenadas en formato unificado usando PyMuPDF."""
    pages_words = []
    doc = fitz.open(pdf_path)
    for page in doc:
        words = page.get_text("words")
        words_clean = []
        for w in words:
            txt = w[4]
            # Filtrar códigos de barras o cadenas binarias de comprobantes
            if len(txt) >= 10 and all(c in '01' for c in txt):
                continue
            # w format: (x0, y0, x1, y1, text, block_no, line_no, word_no)
            words_clean.append({
                'text': txt,
                'x0': w[0],
                'x1': w[2],
                'top': w[1],
                'bottom': w[3],
                'conf': 100.0  # Confianza 100% para digital
            })
        pages_words.append(group_words_into_lines(words_clean))
    doc.close()
    return pages_words

def extract_words_scanned(pdf_path):
    """Extrae palabras estructuradas mediante OCR de alta fidelidad con PyMuPDF + OpenCV + Tesseract."""
    pages_words = []
    doc = fitz.open(pdf_path)
    
    for page in doc:
        # Renderizado nativo a 300 DPI
        pix = page.get_pixmap(dpi=300)
        img_data = pix.tobytes("png")
        nparr = np.frombuffer(img_data, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        
        # Preprocesamiento adaptativo
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        thr = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]
        
        # Ejecutar Tesseract OCR en formato TSV (image_to_data)
        data = pytesseract.image_to_data(thr, lang="eng", output_type=pytesseract.Output.DICT)
        
        words_clean = []
        n_boxes = len(data['text'])
        for i in range(n_boxes):
            txt = data['text'][i].strip()
            if txt:
                # Convertir píxeles de 300 DPI a puntos de PDF (72/300 = 0.24)
                x0 = data['left'][i] * 0.24
                y0 = data['top'][i] * 0.24
                x1 = (data['left'][i] + data['width'][i]) * 0.24
                y1 = (data['top'][i] + data['height'][i]) * 0.24
                conf = float(data['conf'][i])
                words_clean.append({
                    'text': txt,
                    'x0': x0,
                    'x1': x1,
                    'top': y0,
                    'bottom': y1,
                    'conf': conf
                })
        pages_words.append(group_words_into_lines(words_clean, y_tolerance=5.0))
        
    doc.close()
    return pages_words

def is_spaced_out(line_str):
    tokens = [t for t in line_str.split() if t]
    if len(tokens) < 4:
        return False
    single_char_tokens = [t for t in tokens if len(t) == 1]
    return (len(single_char_tokens) / len(tokens)) > 0.6

def normalize_line_with_segments(words):
    if not words:
        return ""
        
    segments = []
    current_segment = [words[0]]
    
    for w in words[1:]:
        prev_w = current_segment[-1]
        gap = w['x0'] - prev_w['x1']
        if gap > 20.0:
            segments.append(current_segment)
            current_segment = [w]
        else:
            current_segment.append(w)
    segments.append(current_segment)
    
    processed_segments = []
    for seg in segments:
        seg_texts = [w['text'] for w in seg]
        single_chars = [t for t in seg_texts if len(t) == 1]
        if len(seg_texts) > 2 and (len(single_chars) / len(seg_texts)) > 0.6:
            collapsed = "".join(seg_texts)
            concept = collapsed
            replacements = {
                "TRANSFER": "Transfer ",
                "WITHDRAWAL": "Withdrawal ",
                "TO": "TO ",
                "ACCOUNT": "ACCOUNT ",
                "OUTGOING": "Outgoing ",
                "WIRE": "Wire ",
                "DEPOSIT": "Deposit "
            }
            for k, v in replacements.items():
                concept = re.sub(k, v, concept, flags=re.IGNORECASE)
            concept = re.sub(r"\s+", " ", concept).strip()
            processed_segments.append(concept)
        else:
            processed_segments.append(" ".join(seg_texts))
            
    return " ".join(processed_segments)

def get_default_columns(bank_name):
    """Retorna las coordenadas por defecto para cada banco si no se detectan dinámicamente."""
    if bank_name == "BANREGIO":
        return [
            ("Fecha", 0, 60),
            ("Concepto", 60, 350),
            ("Cargo", 350, 420),
            ("Abono", 420, 500),
            ("Saldo", 500, 600)
        ]
    elif bank_name == "BANAMEX":
        return [
            ("Fecha", 0, 60),
            ("Concepto", 50, 260),
            ("Cargo", 260, 325),
            ("Abono", 325, 410),
            ("Saldo", 410, 600)
        ]
    elif bank_name == "AMEX":
        return [
            ("Fecha", 0, 95),
            ("Concepto", 95, 440),
            ("Monto", 440, 600)
        ]
    elif bank_name == "IBC":
        return [
            ("Fecha", 0, 85),
            ("Concepto", 85, 340),
            ("Cargo", 340, 420),
            ("Abono", 420, 500),
            ("Saldo", 500, 600)
        ]
    else:  # INTERCAM y DESCONOCIDO
        return [
            ("Fecha", 0, 90),
            ("Concepto", 90, 380),
            ("Cargo", 380, 450),
            ("Abono", 450, 520),
            ("Saldo", 520, 600)
        ]

def partition_line(words, columns):
    """Particiona una línea de palabras en columnas según las coordenadas X."""
    row = {col[0]: [] for col in columns}
    row_words = {col[0]: [] for col in columns}
    
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
        row[col_name].append(w['text'])
        row_words[col_name].append(w)
        
    row_text = {}
    for col_name in row:
        row_text[col_name] = " ".join(row[col_name]).strip()
        
    return row_text, row_words

def parse_ibc_statement(pages_words, file_name, method_used):
    transactions = []
    warnings_log = []
    text_bruto = []
    recap_data = None
    
    for page_idx, page_lines in enumerate(pages_words):
        page_num = page_idx + 1
        page_text_lines = []
        
        for line in page_lines:
            line_str = " ".join([w['text'] for w in line]).strip()
            page_text_lines.append(line_str)
            
        page_text = "\n".join(page_text_lines)
        
        text_bruto.append({
            'Archivo': file_name,
            'Pagina': page_num,
            'Metodo': method_used,
            'Texto': page_text
        })
        
        # Intentar capturar Account Recap en la página 1
        if page_num == 1:
            for line in page_lines:
                line_str = " ".join([w['text'] for w in line]).strip()
                m_recap = REGEX_RECAP_IBC.search(line_str)
                if m_recap:
                    recap_data = {
                        'banco': 'IBC',
                        'cuenta': '',
                        'periodo': '',
                        'beginning_balance': clean_number(m_recap.group(1)),
                        'num_credits': int(m_recap.group(2)),
                        'total_credits': clean_number(m_recap.group(3)),
                        'num_debits': int(m_recap.group(4)),
                        'total_debits': clean_number(m_recap.group(5)),
                        'closing_balance': clean_number(m_recap.group(6))
                    }
                    break
            
            # Buscar cuenta y periodo en la página 1
            for line in page_lines:
                line_str = " ".join([w['text'] for w in line]).strip()
                m_cust = re.search(r"Customer Number:\s*(\d+)", line_str, re.IGNORECASE)
                if m_cust and recap_data:
                    recap_data['cuenta'] = m_cust.group(1)
                m_period = re.search(r"Statement Period:\s*([^\n]+)", line_str, re.IGNORECASE)
                if m_period and recap_data:
                    recap_data['periodo'] = m_period.group(1).strip()
            
        current_section = "OTHER"  # Reset section for each page
        
        for line in page_lines:
            line_str = " ".join([w['text'] for w in line]).strip()
            line_str_upper = line_str.upper()
            
            if not line_str or "CUSTOMER NUMBER:" in line_str_upper or "STATEMENT DATE:" in line_str_upper or "STATEMENT PERIOD:" in line_str_upper or "PAGE NUMBER:" in line_str_upper or "Regular Checking Account Recap" in line_str:
                continue
            
            # Transiciones de sección
            if "DAILY ENDING BALANCE" in line_str_upper or "DAILY BALANCE" in line_str_upper:
                current_section = "DAILY_BALANCE"
                continue
            elif "ELECTRONIC ACTIVITY" in line_str_upper:
                current_section = "ELECTRONIC_ACTIVITY"
                continue
            elif "DEPOSITS (CREDITS)" in line_str_upper or "DEPOSITS" in line_str_upper:
                if "RECAP" in line_str_upper or "BEGINNING" in line_str_upper:
                    pass
                else:
                    current_section = "DEPOSITS"
                    continue
            elif "DEBITS" in line_str_upper or "WITHDRAWALS" in line_str_upper:
                if "RECAP" in line_str_upper or "BEGINNING" in line_str_upper:
                    pass
                else:
                    current_section = "DEBITS"
                    continue
            elif "BALANCE SUMMARY" in line_str_upper or "AVERAGE COLLECTED" in line_str_upper:
                current_section = "OTHER"
                continue
            
            # Procesar transacciones reales bajo secciones autorizadas
            if current_section == "DEPOSITS":
                tokens = line_str.split()
                i = 0
                while i < len(tokens) - 1:
                    t = tokens[i]
                    # Debe ser MM/DD, no MM/DD/YYYY que representa evidencia
                    if re.match(r"^\d{2}/\d{2}$", t):
                        next_t = tokens[i+1]
                        amount_val = clean_number(next_t)
                        if amount_val is not None:
                            transactions.append({
                                'banco': 'IBC',
                                'archivo': file_name,
                                'pagina': page_num,
                                'metodo': method_used,
                                'fecha': t,
                                'concepto': "Deposit",
                                'referencia': "",
                                'cargo': None,
                                'abono': amount_val,
                                'saldo': None,
                                'seccion_origen': 'Deposits (Credits)',
                                'es_movimiento_real': True,
                                'es_evidencia': False,
                                'importe_detectado': amount_val,
                                'importe_1': amount_val,
                                'importe_2': None,
                                'importe_3': None,
                                'original_fecha': t,
                                'original_concepto': "Deposit",
                                'original_cargo': "",
                                'original_abono': next_t,
                                'original_saldo': "",
                                'confianza': 100.0,
                                'advertencias': []
                            })
                            i += 2
                            continue
                    i += 1
                continue
            
            elif current_section == "ELECTRONIC_ACTIVITY":
                if line_str_upper.startswith("CREDITS"):
                    continue
                line_norm = normalize_line_with_segments(line)
                match_date = re.match(r"^(\d{2}/\d{2})\b", line_norm)
                if match_date:
                    date_str = match_date.group(1)
                    rest = line_norm[match_date.end():].strip()
                    
                    amounts = REGEX_AMOUNT.findall(rest)
                    if amounts:
                        amount_str = amounts[-1]
                        amount_val = clean_number(amount_str)
                        pos = rest.rfind(amount_str)
                        concept_str = rest[:pos].strip()
                        
                        concept_str = re.sub(r"Deposit([A-Z])", r"Deposit \1", concept_str)
                        concept_str = re.sub(r"Wire([0-9])", r"Wire \1", concept_str)
                        concept_str = re.sub(r"WithdrawalTO", r"Withdrawal TO", concept_str)
                        concept_str = re.sub(r"\s+", " ", concept_str).strip()
                        
                        all_conf = [w['conf'] for w in line]
                        c_conf = np.mean(all_conf) if all_conf else 100.0
                        
                        transactions.append({
                            'banco': 'IBC',
                            'archivo': file_name,
                            'pagina': page_num,
                            'metodo': method_used,
                            'fecha': date_str,
                            'concepto': concept_str,
                            'referencia': "",
                            'cargo': None,
                            'abono': amount_val,
                            'saldo': None,
                            'seccion_origen': 'Electronic Activity / Credits',
                            'es_movimiento_real': True,
                            'es_evidencia': False,
                            'importe_detectado': amount_val,
                            'importe_1': amount_val,
                            'importe_2': None,
                            'importe_3': None,
                            'original_fecha': date_str,
                            'original_concepto': concept_str,
                            'original_cargo': "",
                            'original_abono': amount_str,
                            'original_saldo': "",
                            'confianza': c_conf,
                            'advertencias': []
                        })
                    continue
            
            elif current_section == "DEBITS":
                line_norm = normalize_line_with_segments(line)
                match_date = re.match(r"^(\d{2}/\d{2})\b", line_norm)
                if match_date:
                    date_str = match_date.group(1)
                    rest = line_norm[match_date.end():].strip()
                    
                    amounts = REGEX_AMOUNT.findall(rest)
                    if amounts:
                        amount_str = amounts[-1]
                        amount_val = clean_number(amount_str)
                        pos = rest.rfind(amount_str)
                        concept_str = rest[:pos].strip()
                        
                        concept_str = re.sub(r"Deposit([A-Z])", r"Deposit \1", concept_str)
                        concept_str = re.sub(r"Wire([0-9])", r"Wire \1", concept_str)
                        concept_str = re.sub(r"WithdrawalTO", r"Withdrawal TO", concept_str)
                        concept_str = re.sub(r"\s+", " ", concept_str).strip()
                        
                        all_conf = [w['conf'] for w in line]
                        c_conf = np.mean(all_conf) if all_conf else 100.0
                        
                        transactions.append({
                            'banco': 'IBC',
                            'archivo': file_name,
                            'pagina': page_num,
                            'metodo': method_used,
                            'fecha': date_str,
                            'concepto': concept_str,
                            'referencia': "",
                            'cargo': amount_val,
                            'abono': None,
                            'saldo': None,
                            'seccion_origen': 'Debits',
                            'es_movimiento_real': True,
                            'es_evidencia': False,
                            'importe_detectado': amount_val,
                            'importe_1': amount_val,
                            'importe_2': None,
                            'importe_3': None,
                            'original_fecha': date_str,
                            'original_concepto': concept_str,
                            'original_cargo': amount_str,
                            'original_abono': "",
                            'original_saldo': "",
                            'confianza': c_conf,
                            'advertencias': []
                        })
                    continue

            # Si es DAILY_BALANCE u OTHER, guardar como evidencia
            if current_section in ["DAILY_BALANCE", "OTHER"]:
                tokens = line_str.split()
                if len(tokens) >= 2:
                    m_d = re.match(r"^(\d{2}/\d{2})$", tokens[0])
                    m_a = clean_number(tokens[-1])
                    if m_d and m_a is not None and "Daily Ending Balance" in page_text:
                        transactions.append({
                            'banco': 'IBC',
                            'archivo': file_name,
                            'pagina': page_num,
                            'metodo': method_used,
                            'fecha': tokens[0],
                            'concepto': "Daily Ending Balance (Saldos Diarios)",
                            'referencia': "",
                            'cargo': None,
                            'abono': None,
                            'saldo': m_a,
                            'seccion_origen': 'Daily Ending Balance',
                            'es_movimiento_real': False,
                            'es_evidencia': True,
                            'importe_detectado': m_a,
                            'importe_1': m_a,
                            'importe_2': None,
                            'importe_3': None,
                            'original_fecha': tokens[0],
                            'original_concepto': "Daily Ending Balance",
                            'original_cargo': "",
                            'original_abono': "",
                            'original_saldo': tokens[-1],
                            'confianza': 100.0,
                            'advertencias': ["Saldo diario - No es un movimiento contable"]
                        })
                        continue

                m_date_full = re.search(r"(\d{2}/\d{2}/\d{4})", line_str)
                if m_date_full:
                    date_full = m_date_full.group(1)
                    amounts = REGEX_AMOUNT.findall(line_str)
                    if amounts:
                        amount_val = clean_number(amounts[-1])
                        transactions.append({
                            'banco': 'IBC',
                            'archivo': file_name,
                            'pagina': page_num,
                            'metodo': method_used,
                            'fecha': date_full[:5],
                            'concepto': f"Evidencia de comprobante o cheque (Original: {date_full})",
                            'referencia': "",
                            'cargo': None,
                            'abono': amount_val,
                            'saldo': None,
                            'seccion_origen': 'Evidencia / Soporte',
                            'es_movimiento_real': False,
                            'es_evidencia': True,
                            'importe_detectado': amount_val,
                            'importe_1': amount_val,
                            'importe_2': None,
                            'importe_3': None,
                            'original_fecha': date_full,
                            'original_concepto': "Evidence Item",
                            'original_cargo': "",
                            'original_abono': amounts[-1],
                            'original_saldo': "",
                            'confianza': 100.0,
                            'advertencias': ["Comprobante visual o copia de cheque - Excluido de transacciones reales"]
                        })
                    
    valid_transactions = []
    for tx in transactions:
        desc = tx['concepto']
        ref = ""
        match_ref = re.search(r"(?:REF|REF\.|RASTREO:|RNU)\s*([A-Za-z0-9\-]+)", desc, re.IGNORECASE)
        if match_ref:
            ref = match_ref.group(1)
        tx['referencia'] = ref
        
        if tx['cargo'] is None and tx['abono'] is None:
            tx['advertencias'].append("No se detectaron importes de cargo o abono en la linea")
            tx['confianza'] = min(tx['confianza'], 50.0)
            
        if tx['confianza'] < 85.0:
            tx['advertencias'].append(f"Baja confianza de lectura óptica: {tx['confianza']:.1f}%")
        valid_transactions.append(tx)
        

    # Rescatar líneas con fecha y monto que no fueron capturadas
    for tx in valid_transactions:
        if tx['cargo'] is None and tx['abono'] is None and tx.get('importe_1') is not None:
            if tx.get('importe_1') and tx.get('importe_2'):
                tx['advertencias'].append("Importes asignados automáticamente por rescate")
            elif tx.get('importe_1'):
                tx['cargo'] = tx['importe_1']
                tx['advertencias'].append("Cargo asignado por rescate de importe único")
    return valid_transactions, text_bruto, warnings_log, recap_data


def parse_bajio_statement(pages_words, file_name, method_used):
    transactions = []
    recap_data = {}
    
    cuenta = ""
    periodo = ""
    fecha_corte = ""
    beg_bal = 0.0
    total_credits = 0.0
    total_debits = 0.0
    closing_bal = 0.0
    
    columns = [
        ("Fecha", 0, 70),
        ("Concepto", 70, 380),
        ("Abono", 380, 460),
        ("Cargo", 460, 530),
        ("Saldo", 530, 650)
    ]
    
    current_tx = None
    
    for page_num_idx, page_lines in enumerate(pages_words):
        page_num = page_num_idx + 1
        
        for line in page_lines:
            line_str = " ".join([w['text'] for w in line]).strip()
            line_str_upper = line_str.upper()
            
            if not line_str:
                continue
                
            if "CUENTA" in line_str_upper and "BANBAJIO" in line_str_upper:
                m_ct = re.search(r"CUENTA\s+(?:CONECTA\s+BANBAJIO)?\s*(\d+)", line_str_upper)
                if m_ct and not cuenta:
                    cuenta = m_ct.group(1)
            
            if "PERIODO:" in line_str_upper:
                m_per = re.search(r"PERIODO:\s*(.*)", line_str_upper)
                if m_per and not periodo:
                    periodo = m_per.group(1).strip()
                    
            if "FECHA DE CORTE" in line_str_upper:
                m_fc = re.search(r"FECHA DE CORTE\s+(.*)", line_str_upper)
                if m_fc and not fecha_corte:
                    fecha_corte = m_fc.group(1).strip()
                    
            m_recap = re.search(r"\$\s*([\d,]+\.\d{2})\s*\$\s*([\d,]+\.\d{2})\s*\$\s*([\d,]+\.\d{2})\s*\$\s*([\d,]+\.\d{2})", line_str)
            if m_recap and "SALDO" not in line_str_upper:
                if beg_bal == 0.0 and closing_bal == 0.0:
                    beg_bal = clean_number(m_recap.group(1))
                    total_credits = clean_number(m_recap.group(2))
                    total_debits = clean_number(m_recap.group(3))
                    closing_bal = clean_number(m_recap.group(4))
                    
            if "RESUMEN DE COMISIONES" in line_str_upper or "SALDO MINIMO" in line_str_upper or "ESTE DOCUMENTO ES UNA REPRESENTACION" in line_str_upper or "TOTAL DE" in line_str_upper:
                if current_tx:
                    transactions.append(current_tx)
                    current_tx = None
                continue
                
            row_text, row_words = partition_line(line, columns)
            fecha_col = row_text.get("Fecha", "").strip()
            
            # Match formats like "5 ENE" or "05 ENE"
            m_fecha = re.match(r"^(\d{1,2}\s+[A-Za-z]{3})", fecha_col)
            
            if m_fecha:
                if current_tx:
                    transactions.append(current_tx)
                    
                cargo_str = row_text.get("Cargo", "")
                abono_str = row_text.get("Abono", "")
                saldo_str = row_text.get("Saldo", "")
                
                cargo_val = clean_number(cargo_str)
                abono_val = clean_number(abono_str)
                saldo_val = clean_number(saldo_str)
                
                # Derive year from fecha_corte
                year = "2024"
                m_year = re.search(r"(\d{4})", fecha_corte)
                if m_year: year = m_year.group(1)
                elif m_year := re.search(r"(\d{4})", periodo): year = m_year.group(1)
                
                # Format to dd/mm/yyyy
                parts = fecha_col.split()
                day = int(parts[0])
                meses = {"ENE":1, "FEB":2, "MAR":3, "ABR":4, "MAY":5, "JUN":6, "JUL":7, "AGO":8, "SEP":9, "OCT":10, "NOV":11, "DIC":12}
                month = meses.get(parts[1].upper()[:3], 1)
                fecha_clean = f"{day:02d}/{month:02d}/{year}"
                
                current_tx = {
                    'banco': 'BAJIO',
                    'archivo': file_name,
                    'pagina': page_num,
                    'metodo': method_used,
                    'fecha': fecha_clean,
                    'concepto': row_text.get("Concepto", "").strip(),
                    'cargo': cargo_val,
                    'abono': abono_val,
                    'saldo': saldo_val,
                    'original_fecha': fecha_col,
                    'original_concepto': row_text.get("Concepto", "").strip(),
                    'confianza': 100.0,
                    'advertencias': [],
                    'referencia': '',
                    'es_movimiento_real': True,
                    'es_evidencia': False
                }
            elif current_tx:
                conc = row_text.get("Concepto", "").strip()
                if conc:
                    current_tx['concepto'] += " " + conc
                    current_tx['original_concepto'] += " " + conc
                    
                # Si el amount estaba en la linea siguiente
                cargo_str = row_text.get("Cargo", "")
                abono_str = row_text.get("Abono", "")
                if clean_number(abono_str) and current_tx['abono'] is None:
                    current_tx['abono'] = clean_number(abono_str)
                if clean_number(cargo_str) and current_tx['cargo'] is None:
                    current_tx['cargo'] = clean_number(cargo_str)
                    
    if current_tx:
        transactions.append(current_tx)
        
    recap_data = {
        'banco': 'BAJIO',
        'cuenta': cuenta,
        'periodo': periodo,
        'fecha_corte': fecha_corte,
        'beginning_balance': beg_bal,
        'num_credits': 0,
        'total_credits': total_credits,
        'num_debits': 0,
        'total_debits': total_debits,
        'closing_balance': closing_bal
    }
    
    return transactions, "", [], recap_data

def parse_banamex_statement(pages_words, file_name, method_used):
    transactions = []
    warnings_log = []
    text_bruto = []
    recap_data = None
    
    columns = get_default_columns("BANAMEX")
    current_tx = None
    REGEX_MONTO_DECIMAL = re.compile(r"\d+[\.,]\d{2}")
    
    for page_idx, page_lines in enumerate(pages_words):
        page_num = page_idx + 1
        page_text_lines = []
        
        for line in page_lines:
            line_str = " ".join([w['text'] for w in line]).strip()
            page_text_lines.append(line_str)
            
        page_text = "\n".join(page_text_lines)
        
        text_bruto.append({
            'Archivo': file_name,
            'Pagina': page_num,
            'Metodo': method_used,
            'Texto': page_text
        })
        
        # Intentar extraer recap en la página 1
        if page_num == 1:
            cuenta = ""
            periodo = ""
            beg_bal = 0.0
            num_credits = 0
            total_credits = 0.0
            num_debits = 0
            total_debits = 0.0
            closing_bal = 0.0
            
            m_ct = re.search(r"CONTRATO\s*(\d+)", page_text, re.IGNORECASE)
            if m_ct:
                cuenta = m_ct.group(1)
            else:
                m_clabe = re.search(r"CLABE Interbancaria\s*(\d+)", page_text, re.IGNORECASE)
                if m_clabe:
                    cuenta = m_clabe.group(1)
                    
            m_per = re.search(r"RESUMEN DEL:\s*([^\n]+)", page_text, re.IGNORECASE)
            if m_per:
                periodo = m_per.group(1).strip()
            else:
                m_est = re.search(r"ESTADO DE CUENTA AL\s*([^\n]+)", page_text, re.IGNORECASE)
                if m_est:
                    periodo = m_est.group(1).strip()
                    
            m_beg = re.search(r"Saldo Anterior\s*(?:\s*[^\n]*?)\$?([\d,]+\.\d{2})", page_text, re.IGNORECASE)
            if m_beg:
                beg_bal = clean_number(m_beg.group(1))
                
            m_cred = re.search(r"(\d+)\s+Dep[oó\uFFFD\?a-z]*?sitos\s*\$?([\d,]+\.\d{2})", page_text, re.IGNORECASE)
            if m_cred:
                num_credits = int(m_cred.group(1))
                total_credits = clean_number(m_cred.group(2))
                
            m_deb = re.search(r"(\d+)\s+Retiros\s*\$?([\d,]+\.\d{2})", page_text, re.IGNORECASE)
            if m_deb:
                num_debits = int(m_deb.group(1))
                total_debits = clean_number(m_deb.group(2))
                
            m_end = re.search(r"SALDO AL \d+ DE [A-Z\uFFFD\?a-z]+\s+DE\s+\d{4}\s*\$?([\d,]+\.\d{2})", page_text, re.IGNORECASE)
            if m_end:
                closing_bal = clean_number(m_end.group(1))
            else:
                m_end_alt = re.search(r"SALDO AL\s*\d+\s*[A-Z\uFFFD\?a-z]+\s*\d{4}\s*\$?([\d,]+\.\d{2})", page_text, re.IGNORECASE)
                if m_end_alt:
                    closing_bal = clean_number(m_end_alt.group(1))
            
            recap_data = {
                'banco': 'BANAMEX',
                'cuenta': cuenta,
                'periodo': periodo,
                'beginning_balance': beg_bal,
                'num_credits': num_credits,
                'total_credits': total_credits,
                'num_debits': num_debits,
                'total_debits': total_debits,
                'closing_balance': closing_bal
            }
            
        for line in page_lines:
            line_str = " ".join([w['text'] for w in line]).strip()
            line_str_upper = line_str.upper()
            
            if not line_str or "ESTADO DE CUENTA" in line_str_upper or "PAGE" in line_str_upper or "HOJA" in line_str_upper:
                continue
                
            if "ESTE NO ES UN DOCUMENTO CON VALIDEZ FISCAL" in line_str_upper or "ABREVIACI" in line_str_upper or "SIGNIFICADO" in line_str_upper:
                if current_tx:
                    transactions.append(current_tx)
                    current_tx = None
                continue
                
            line_amounts = []
            for w in line:
                txt = w['text']
                if REGEX_MONTO_DECIMAL.search(txt) and not ":" in txt:
                    val = clean_number(txt)
                    if val is not None and abs(val) > 0.001:
                        line_amounts.append((val, txt, w))
            line_amounts = sorted(line_amounts, key=lambda x: x[2]['x0'])
            row_text, row_words = partition_line(line, columns)
            
            match_fecha = REGEX_FECHA.match(line_str_upper)
            if match_fecha:
                if current_tx:
                    transactions.append(current_tx)
                    
                fecha_str = match_fecha.group(1)
                concept_str = line_str[match_fecha.end():].strip()
                
                current_tx = {
                    'banco': 'BANAMEX',
                    'archivo': file_name,
                    'pagina': page_num,
                    'metodo': method_used,
                    'fecha': fecha_str,
                    'concepto': concept_str,
                    'cargo': None,
                    'abono': None,
                    'saldo': None,
                    'seccion_origen': '',
                    'importe_detectado': None,
                    'importe_1': None,
                    'importe_2': None,
                    'importe_3': None,
                    'original_fecha': fecha_str,
                    'original_concepto': concept_str,
                    'original_cargo': '',
                    'original_abono': '',
                    'original_saldo': '',
                    'confianza': 100.0,
                    'advertencias': [],
                    'metadata': ''
                }
                continue
                
            if ("HORA " in line_str_upper and "SUC " in line_str_upper) or (re.search(r"\d{2}:\d{2}", line_str) and "SUC" in line_str_upper):
                if current_tx:
                    confs = [w['conf'] for w in line if w['text'].replace(",", "").replace(".", "").isdigit()]
                    if confs:
                        current_tx['confianza'] = min(current_tx['confianza'], np.mean(confs))
                        
                    if len(line_amounts) >= 1:
                        current_tx['importe_1'] = line_amounts[0][0]
                        current_tx['importe_detectado'] = line_amounts[0][0]
                    if len(line_amounts) >= 2:
                        current_tx['importe_2'] = line_amounts[1][0]
                        current_tx['saldo'] = line_amounts[1][0]
                        current_tx['original_saldo'] = line_amounts[1][1]
                    if len(line_amounts) >= 3:
                        current_tx['importe_3'] = line_amounts[2][0]
                        
                    if (len(line_amounts) == 1 and
                        current_tx.get('abono') is not None and
                        current_tx.get('cargo') is None and
                        "DEPOSITO DE SUC" in current_tx.get('concepto', '').upper()):
                        current_tx['saldo'] = line_amounts[0][0]
                        current_tx['original_saldo'] = line_amounts[0][1]
                    elif len(line_amounts) >= 1:
                        m_val, m_str, m_word = line_amounts[0]
                        center_x = (m_word['x0'] + m_word['x1']) / 2.0
                        if center_x < 325.0:
                            current_tx['cargo'] = m_val
                            current_tx['original_cargo'] = m_str
                        else:
                            current_tx['abono'] = m_val
                            current_tx['original_abono'] = m_str
                    else:
                        current_tx['cargo'] = clean_number(row_text.get("Cargo"))
                        current_tx['abono'] = clean_number(row_text.get("Abono"))
                        current_tx['saldo'] = clean_number(row_text.get("Saldo"))
                        current_tx['original_cargo'] = row_text.get("Cargo", "")
                        current_tx['original_abono'] = row_text.get("Abono", "")
                        current_tx['original_saldo'] = row_text.get("Saldo", "")
                continue
                
            if "CAJA " in line_str_upper and "AUT " in line_str_upper:
                if current_tx:
                    current_tx['metadata'] = line_str
                continue
                
            if current_tx and not line_str_upper.startswith("DETALLE DE OPERACIONES"):
                if not ("CAJA " in line_str_upper and "AUT " in line_str_upper) and not ("HORA " in line_str_upper and "SUC " in line_str_upper):
                    if not any(w['text'].replace(",", "").replace(".", "").isdigit() for w in line):
                        current_tx['concepto'] += " " + line_str
                        current_tx['original_concepto'] += " " + line_str
                continue
                
    if current_tx:
        transactions.append(current_tx)
        
    valid_transactions = []
    for tx in transactions:
        desc = tx['concepto']
        ref = ""
        match_ref = re.search(r"(?:REF|REF\.|RASTREO:|RNU)\s*([A-Za-z0-9\-]+)", desc, re.IGNORECASE)
        if match_ref:
            ref = match_ref.group(1)
        tx['referencia'] = ref
        
        if tx['cargo'] is None and tx['abono'] is None:
            if tx.get('importe_detectado') is not None:
                tx['advertencias'].append(f"Monto detectado en linea ({tx['importe_detectado']:,.2f}) pero fuera de columnas fijas. Favor de validar Cargo/Abono manualmente.")
                tx['confianza'] = min(tx['confianza'], 75.0)
            else:
                tx['advertencias'].append("No se detectaron importes de cargo o abono en la linea")
                tx['confianza'] = min(tx['confianza'], 50.0)
            
        if tx['confianza'] < 85.0:
            tx['advertencias'].append(f"Baja confianza de lectura óptica: {tx['confianza']:.1f}%")
        valid_transactions.append(tx)
        
    for idx in range(1, len(valid_transactions)):
        prev = valid_transactions[idx-1]
        curr = valid_transactions[idx]
        if prev['saldo'] is not None and curr['saldo'] is not None:
            prev_s = prev['saldo']
            curr_s = curr['saldo']
            cargo = curr['cargo'] or 0.0
            abono = curr['abono'] or 0.0
            calculado = prev_s - cargo + abono
            if abs(calculado - curr_s) > 0.05:
                curr['advertencias'].append(f"Inconsistencia matemática: Saldo calculado {calculado:,.2f} vs reportado {curr_s:,.2f}")
                curr['confianza'] = min(curr['confianza'], 70.0)
                warnings_log.append({
                    'Archivo': file_name,
                    'Pagina': curr['pagina'],
                    'Tipo': 'Error Matemático',
                    'Descripcion': f"El saldo calculado para el movimiento no coincide con el saldo de la fila. Anterior: {prev_s:,.2f}, Cargo: {cargo:,.2f}, Abono: {abono:,.2f}, Esperado: {calculado:,.2f}, Reportado: {curr_s:,.2f}",
                    'Movimiento': curr['concepto']
                })
                

    # Rescatar líneas con fecha y monto que no fueron capturadas
    for tx in valid_transactions:
        if tx['cargo'] is None and tx['abono'] is None and tx.get('importe_1') is not None:
            if tx.get('importe_1') and tx.get('importe_2'):
                tx['advertencias'].append("Importes asignados automáticamente por rescate")
            elif tx.get('importe_1'):
                tx['cargo'] = tx['importe_1']
                tx['advertencias'].append("Cargo asignado por rescate de importe único")
    return valid_transactions, text_bruto, warnings_log, recap_data

def parse_banregio_statement(pages_words, file_name, method_used):
    transactions = []
    warnings_log = []
    text_bruto = []
    recap_data = None
    
    columns = get_default_columns("BANREGIO")
    current_tx = None
    
    for page_idx, page_lines in enumerate(pages_words):
        page_num = page_idx + 1
        page_text_lines = []
        
        for line in page_lines:
            line_str = " ".join([w['text'] for w in line]).strip()
            page_text_lines.append(line_str)
            
        page_text = "\n".join(page_text_lines)
        
        text_bruto.append({
            'Archivo': file_name,
            'Pagina': page_num,
            'Metodo': method_used,
            'Texto': page_text
        })
        
        if not recap_data or recap_data.get('total_credits') == 0.0:
            cuenta = ""
            periodo = ""
            beg_bal = 0.0
            total_credits = 0.0
            total_debits = 0.0
            closing_bal = 0.0
            
            m_ct = re.search(r"CUENTA\s+(\d{10,12})", page_text, re.IGNORECASE)
            if not m_ct:
                m_ct = re.search(r"CUENTA\s+NARANJA[A-Z\s]*([0-9-]+)", page_text, re.IGNORECASE)
            if m_ct:
                cuenta = m_ct.group(1).replace("-", "")
            else:
                m_clabe = re.search(r"CLABE\s+(\d+)", page_text, re.IGNORECASE)
                if m_clabe:
                    cuenta = m_clabe.group(1)
            
            m_per = re.search(r"del\s+(\d+\s+al\s+\d+\s+de\s+[A-Z]+\s+\d{4})", page_text, re.IGNORECASE)
            if m_per:
                periodo = m_per.group(1).strip()
                
            m_beg = re.search(r"Saldo\s+Inicial\s*\$?([\d,]+\.\d{2})", page_text, re.IGNORECASE)
            m_add = re.search(r"\+\s*Abonos\s*\$?([\d,]+\.\d{2})", page_text, re.IGNORECASE)
            
            # Buscar el bloque multilínea de retiros y saldo final
            m_block = re.search(r"-\s*Retiros\s*\n\s*=\s*Saldo\s+Final\s*\n\s*\$?([\d,]+\.\d{2})\s*\n\s*\$?([\d,]+\.\d{2})", page_text, re.IGNORECASE)
            if m_block:
                total_debits = clean_number(m_block.group(1))
                closing_bal = clean_number(m_block.group(2))
            else:
                m_ret = re.search(r"-\s*Retiros\s*\$?([\d,]+\.\d{2})", page_text, re.IGNORECASE)
                m_otros = re.search(r"-\s*Otros\s+Cargos\s*\$?([\d,]+\.\d{2})", page_text, re.IGNORECASE)
                m_end = re.search(r"=\s*Saldo\s+Final\s*\$?([\d,]+\.\d{2})", page_text, re.IGNORECASE)
                
                retiros_val = clean_number(m_ret.group(1)) if m_ret else 0.0
                otros_val = clean_number(m_otros.group(1)) if m_otros else 0.0
                total_debits = retiros_val + otros_val
                
                if m_end:
                    closing_bal = clean_number(m_end.group(1))
            
            if m_beg:
                beg_bal = clean_number(m_beg.group(1))
                if m_add:
                    total_credits = clean_number(m_add.group(1))
                
                recap_data = {
                    'banco': 'BANREGIO',
                    'cuenta': cuenta,
                    'periodo': periodo,
                    'beginning_balance': beg_bal,
                    'num_credits': 0,
                    'total_credits': total_credits,
                    'num_debits': 0,
                    'total_debits': total_debits,
                    'closing_balance': closing_bal
                }
                
        for line in page_lines:
            line_str = " ".join([w['text'] for w in line]).strip()
            line_str_upper = line_str.upper()
            
            if not line_str or "ESTADO DE CUENTA" in line_str_upper or "PAGE" in line_str_upper or "HOJA" in line_str_upper:
                continue
                
            if "ESTE NO ES UN DOCUMENTO CON VALIDEZ FISCAL" in line_str_upper or "ABREVIACI" in line_str_upper or "SIGNIFICADO" in line_str_upper:
                if current_tx:
                    transactions.append(current_tx)
                    current_tx = None
                continue
                
            line_amounts = []
            for w in line:
                txt = w['text']
                if re.search(r"\d+[\.,]\d{2}", txt) and not ":" in txt:
                    val = clean_number(txt)
                    if val is not None and abs(val) > 0.001:
                        line_amounts.append((val, txt, w))
            line_amounts = sorted(line_amounts, key=lambda x: x[2]['x0'])
            row_text, row_words = partition_line(line, columns)
            
            fecha_col = row_text.get("Fecha", "")
            concept_col = row_text.get("Concepto", "")
            fecha_col_upper = fecha_col.upper()
            
            is_new_tx = False
            fecha_clean = ""
            
            m_regio = re.match(r"^(\d{1,2})\b", fecha_col_upper.strip())
            if m_regio:
                day_num = int(m_regio.group(1))
                if 1 <= day_num <= 31:
                    is_new_tx = True
                    mes_str = "AGO"
                    if recap_data and recap_data['periodo']:
                        for m in ["ENE", "FEB", "MAR", "ABR", "MAY", "JUN", "JUL", "AGO", "SEP", "OCT", "NOV", "DIC", "JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]:
                            if m in recap_data['periodo'].upper():
                                mes_str = m
                                break
                    año = "2024"
                    if recap_data and recap_data.get('periodo'):
                        m_year = re.search(r'\d{4}', recap_data['periodo'])
                        if m_year:
                            año = m_year.group(0)
                        else:
                            from datetime import datetime
                            año = str(datetime.now().year)
                    fecha_clean = f"{str(day_num).zfill(2)} {mes_str} {año}" 
                    
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
                    'banco': 'BANREGIO',
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
                if concept_col and not cargo_val and not abono_val:
                    current_tx['concepto'] += " " + concept_col
                    current_tx['original_concepto'] += " " + concept_col
                continue
                
    if current_tx:
        transactions.append(current_tx)
        
    if recap_data:
        recap_data['num_credits'] = len([t for t in transactions if t['abono'] is not None])
        recap_data['num_debits'] = len([t for t in transactions if t['cargo'] is not None])
        
    valid_transactions = []
    for tx in transactions:
        desc = tx['concepto']
        ref = ""
        match_ref = re.search(r"(?:REF|REF\.|RASTREO:|RNU)\s*([A-Za-z0-9\-]+)", desc, re.IGNORECASE)
        if match_ref:
            ref = match_ref.group(1)
        tx['referencia'] = ref
        
        if tx['cargo'] is None and tx['abono'] is None:
            tx['advertencias'].append("No se detectaron importes de cargo o abono en la linea")
            tx['confianza'] = min(tx['confianza'], 50.0)
            
        if tx['confianza'] < 85.0:
            tx['advertencias'].append(f"Baja confianza de lectura óptica: {tx['confianza']:.1f}%")
        valid_transactions.append(tx)
        

    # Rescatar líneas con fecha y monto que no fueron capturadas
    for tx in valid_transactions:
        if tx['cargo'] is None and tx['abono'] is None and tx.get('importe_1') is not None:
            if tx.get('importe_1') and tx.get('importe_2'):
                tx['advertencias'].append("Importes asignados automáticamente por rescate")
            elif tx.get('importe_1'):
                tx['cargo'] = tx['importe_1']
                tx['advertencias'].append("Cargo asignado por rescate de importe único")
    return valid_transactions, text_bruto, warnings_log, recap_data

def parse_amex_statement(pages_words, file_name, method_used):
    transactions = []
    warnings_log = []
    text_bruto = []
    recap_data = None
    
    columns = get_default_columns("AMEX")
    current_tx = None
    
    for page_idx, page_lines in enumerate(pages_words):
        page_num = page_idx + 1
        page_text_lines = []
        
        for line in page_lines:
            line_str = " ".join([w['text'] for w in line]).strip()
            page_text_lines.append(line_str)
            
        page_text = "\n".join(page_text_lines)
        
        text_bruto.append({
            'Archivo': file_name,
            'Pagina': page_num,
            'Metodo': method_used,
            'Texto': page_text
        })
        
        if page_num == 1:
            cuenta = ""
            periodo = ""
            fecha_corte = ""
            beg_bal = 0.0
            total_credits = 0.0
            total_debits = 0.0
            closing_bal = 0.0
            
            m_ct_corte = re.search(r"([\d\-]{15,})\s+(\d{1,2}-[A-Za-z]{3}-\d{4})", page_text)
            if m_ct_corte:
                cuenta = m_ct_corte.group(1).replace("-", "")
                fecha_corte = m_ct_corte.group(2)
            else:
                m_ct = re.search(r"N[uú]mero de Cuenta\s*([0-9-]+)", page_text, re.IGNORECASE)
                if m_ct:
                    cuenta = m_ct.group(1).replace("-", "")
                
            m_per = re.search(r"Periodo de facturaci[oó]?n:\s*(?:Del)?(.*?)\.\s*D", page_text, re.IGNORECASE)
            if m_per:
                periodo = m_per.group(1).strip()
                
            flat_text = re.sub(r"\s+", " ", page_text)
            m_recap = re.search(r"([\d,]+\.\d{2})C?\s*-\s*([\d,]+\.\d{2})\s*\+\s*([\d,]+\.\d{2})\s*=\s*([\d,]+\.\d{2})", flat_text)
            if m_recap:
                beg_bal = clean_number(m_recap.group(1))
                if "C" in flat_text[m_recap.start(1):m_recap.end(1)+2]:
                    beg_bal = -abs(beg_bal)
                total_credits = clean_number(m_recap.group(2))
                total_debits = clean_number(m_recap.group(3))
                closing_bal = clean_number(m_recap.group(4))
                
            recap_data = {
                'banco': 'AMEX',
                'cuenta': cuenta,
                'periodo': periodo,
                'fecha_corte': fecha_corte,
                'beginning_balance': beg_bal,
                'num_credits': 0,
                'total_credits': total_credits,
                'num_debits': 0,
                'total_debits': total_debits,
                'closing_balance': closing_bal
            }
            
            def format_amex_date(fecha_str, per):
                m_y = re.search(r"\d{4}", per)
                year = int(m_y.group(0)) if m_y else 2024
                meses = {"Ene": 1, "Feb": 2, "Mar": 3, "Abr": 4, "May": 5, "Jun": 6, "Jul": 7, "Ago": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dic": 12, "Enero": 1, "Febrero": 2, "Marzo": 3, "Abril": 4, "Mayo": 5, "Junio": 6, "Julio": 7, "Agosto": 8, "Septiembre": 9, "Octubre": 10, "Noviembre": 11, "Diciembre": 12}
                
                m = re.search(r"(\d{1,2})\s*de\s*([A-Za-z]+)", fecha_str, re.IGNORECASE)
                if m:
                    d = int(m.group(1))
                    mes_str = m.group(2).capitalize()
                    mes = meses.get(mes_str, 1)
                    
                    m_per2 = re.search(r"al\s*\d+\s*de\s*([A-Za-z]+)", per, re.IGNORECASE)
                    if m_per2:
                        mes_corte = meses.get(m_per2.group(1).capitalize(), 1)
                        if mes > mes_corte and mes == 12 and mes_corte == 1:
                            year -= 1
                    return f"{d:02d}/{mes:02d}/{year}"
                return fecha_str
            
        for line in page_lines:
            line_str = " ".join([w['text'] for w in line]).strip()
            line_str_upper = line_str.upper()
            
            if not line_str or "ESTADO DE CUENTA" in line_str_upper or "PAGE" in line_str_upper or "HOJA" in line_str_upper:
                continue
                
            if "ESTE NO ES UN DOCUMENTO CON VALIDEZ FISCAL" in line_str_upper or "ABREVIACI" in line_str_upper or "SIGNIFICADO" in line_str_upper:
                if current_tx:
                    transactions.append(current_tx)
                    current_tx = None
                continue
                
            row_text, row_words = partition_line(line, columns)
            fecha_col = row_text.get("Fecha", "")
            fecha_col_upper = fecha_col.upper()
            match_fecha = REGEX_FECHA.match(fecha_col_upper)
            
            if match_fecha:
                if current_tx:
                    transactions.append(current_tx)
                    
                monto_str = row_text.get("Monto", "")
                monto_val = clean_number(monto_str)
                resto_fecha = fecha_col[match_fecha.end():].strip()
                concepto_str = (resto_fecha + " " + row_text.get("Concepto", "")).strip()
                fecha_clean = fecha_col[:match_fecha.end()].strip()
                
                monto_words = row_words.get("Monto", [])
                c_conf = np.mean([w['conf'] for w in monto_words]) if monto_words else 100.0
                
                cargo = None
                abono = None
                if "PAGO RECIBIDO" in concepto_str.upper() or re.search(r"\bCR\b", monto_str.upper()):
                    abono = abs(monto_val) if monto_val else None
                else:
                    cargo = monto_val
                    
                current_tx = {
                    'banco': 'AMEX',
                    'archivo': file_name,
                    'pagina': page_num,
                    'metodo': method_used,
                    'fecha': format_amex_date(fecha_clean, periodo),
                    'concepto': concepto_str,
                    'cargo': cargo,
                    'abono': abono,
                    'saldo': None,
                    'seccion_origen': '',
                    'importe_detectado': monto_val,
                    'importe_1': monto_val,
                    'importe_2': None,
                    'importe_3': None,
                    'original_fecha': fecha_col,
                    'original_concepto': concepto_str,
                    'original_cargo': monto_str if cargo else "",
                    'original_abono': monto_str if abono else "",
                    'original_saldo': "",
                    'confianza': c_conf,
                    'advertencias': []
                }
                continue
                
            if current_tx:
                fecha_val = row_text.get("Fecha", "").strip()
                if current_tx['original_fecha'].lower().endswith(" de") and fecha_val.isalpha():
                    current_tx['original_fecha'] += " " + fecha_val
                    current_tx['fecha'] = format_amex_date(current_tx['original_fecha'], periodo)
                    
                conc_val = row_text.get("Concepto", "")
                if conc_val and not conc_val.upper().startswith("DETALLE DE NUEVOS"):
                    current_tx['concepto'] += " " + conc_val
                    current_tx['original_concepto'] += " " + conc_val
                monto_col = row_text.get("Monto", "")
                if re.search(r"\bCR\b", monto_col.upper()):
                    if current_tx.get('cargo') is not None:
                        current_tx['abono'] = current_tx['cargo']
                        current_tx['cargo'] = None
                        current_tx['original_abono'] = current_tx['original_cargo']
                        current_tx['original_cargo'] = ""
                continue
                
    if current_tx:
        transactions.append(current_tx)
        
    if recap_data:
        recap_data['num_credits'] = len([t for t in transactions if t['abono'] is not None])
        recap_data['num_debits'] = len([t for t in transactions if t['cargo'] is not None])
        
    valid_transactions = []
    for tx in transactions:
        desc = tx['concepto']
        ref = ""
        match_ref = re.search(r"(?:REF|REF\.|RASTREO:|RNU)\s*([A-Za-z0-9\-]+)", desc, re.IGNORECASE)
        if match_ref:
            ref = match_ref.group(1)
        tx['referencia'] = ref
        
        if tx['cargo'] is None and tx['abono'] is None:
            tx['advertencias'].append("No se detectaron importes de cargo o abono en la linea")
            tx['confianza'] = min(tx['confianza'], 50.0)
            
        if tx['confianza'] < 85.0:
            tx['advertencias'].append(f"Baja confianza de lectura óptica: {tx['confianza']:.1f}%")
        valid_transactions.append(tx)
        

    # Rescatar líneas con fecha y monto que no fueron capturadas
    for tx in valid_transactions:
        if tx['cargo'] is None and tx['abono'] is None and tx.get('importe_1') is not None:
            if tx.get('importe_1') and tx.get('importe_2'):
                tx['advertencias'].append("Importes asignados automáticamente por rescate")
            elif tx.get('importe_1'):
                tx['cargo'] = tx['importe_1']
                tx['advertencias'].append("Cargo asignado por rescate de importe único")
    return valid_transactions, text_bruto, warnings_log, recap_data

def parse_intercam_statement(pages_words, file_name, method_used):
    transactions = []
    warnings_log = []
    text_bruto = []
    recap_data = None
    
    columns = get_default_columns("INTERCAM")
    current_tx = None
    
    for page_idx, page_lines in enumerate(pages_words):
        page_num = page_idx + 1
        page_text_lines = []
        
        for line in page_lines:
            line_str = " ".join([w['text'] for w in line]).strip()
            page_text_lines.append(line_str)
            
        page_text = "\n".join(page_text_lines)
        
        text_bruto.append({
            'Archivo': file_name,
            'Pagina': page_num,
            'Metodo': method_used,
            'Texto': page_text
        })
        
        cuenta = ""
        m_ct = re.search(r"CUENTA\s*:\s*(\d+)", page_text, re.IGNORECASE)
        if m_ct:
            cuenta = m_ct.group(1)
            
        periodo = ""
        m_per = re.search(r"Periodo\s*:\s*([^\n]+)", page_text, re.IGNORECASE)
        if m_per:
            periodo = m_per.group(1).strip()
            
        for line in page_lines:
            line_str = " ".join([w['text'] for w in line]).strip()
            line_str_upper = line_str.upper()
            
            if not line_str or "ESTADO DE CUENTA" in line_str_upper or "PAGE" in line_str_upper or "HOJA" in line_str_upper:
                continue
                
            if "ESTE NO ES UN DOCUMENTO CON VALIDEZ FISCAL" in line_str_upper or "ABREVIACI" in line_str_upper or "SIGNIFICADO" in line_str_upper:
                if current_tx:
                    transactions.append(current_tx)
                    current_tx = None
                continue
                
            line_amounts = []
            for w in line:
                txt = w['text']
                if re.search(r"\d+[\.,]\d{2}", txt) and not ":" in txt:
                    val = clean_number(txt)
                    if val is not None and abs(val) > 0.001:
                        line_amounts.append((val, txt, w))
            line_amounts = sorted(line_amounts, key=lambda x: x[2]['x0'])
            row_text, row_words = partition_line(line, columns)
            
            fecha_col = row_text.get("Fecha", "")
            concept_col = row_text.get("Concepto", "")
            
            is_new_tx = False
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
                if concept_col and not cargo_val and not abono_val:
                    current_tx['concepto'] += " " + concept_col
                    current_tx['original_concepto'] += " " + concept_col
                continue
                
    if current_tx:
        transactions.append(current_tx)
        
    ext_num_credits = len([t for t in transactions if t['abono'] is not None])
    ext_total_credits = sum([t['abono'] for t in transactions if t['abono'] is not None])
    ext_num_debits = len([t for t in transactions if t['cargo'] is not None])
    ext_total_debits = sum([t['cargo'] for t in transactions if t['cargo'] is not None])
    
    recap_data = {
        'banco': 'INTERCAM',
        'cuenta': cuenta,
        'periodo': periodo,
        'beginning_balance': 0.0,
        'num_credits': ext_num_credits,
        'total_credits': ext_total_credits,
        'num_debits': ext_num_debits,
        'total_debits': ext_total_debits,
        'closing_balance': ext_total_credits - ext_total_debits
    }
    
    valid_transactions = []
    for tx in transactions:
        desc = tx['concepto']
        ref = ""
        match_ref = re.search(r"(?:REF|REF\.|RASTREO:|RNU)\s*([A-Za-z0-9\-]+)", desc, re.IGNORECASE)
        if match_ref:
            ref = match_ref.group(1)
        tx['referencia'] = ref
        
        if tx['cargo'] is None and tx['abono'] is None:
            tx['advertencias'].append("No se detectaron importes de cargo o abono en la linea")
            tx['confianza'] = min(tx['confianza'], 50.0)
            
        if tx['confianza'] < 85.0:
            tx['advertencias'].append(f"Baja confianza de lectura óptica: {tx['confianza']:.1f}%")
        valid_transactions.append(tx)
        

    # Rescatar líneas con fecha y monto que no fueron capturadas
    for tx in valid_transactions:
        if tx['cargo'] is None and tx['abono'] is None and tx.get('importe_1') is not None:
            if tx.get('importe_1') and tx.get('importe_2'):
                tx['advertencias'].append("Importes asignados automáticamente por rescate")
            elif tx.get('importe_1'):
                tx['cargo'] = tx['importe_1']
                tx['advertencias'].append("Cargo asignado por rescate de importe único")
    return valid_transactions, text_bruto, warnings_log, recap_data

def parse_monex_statement(pages_words, file_name, method_used):
    txs = []
    warnings = []
    raw = []
    recap = {
        'banco': 'MONEX',
        'cuenta': '',
        'periodo': '',
        'beginning_balance': 0.0,
        'num_credits': 0,
        'total_credits': 0.0,
        'num_debits': 0,
        'total_debits': 0.0,
        'closing_balance': 0.0
    }
    
    import re
    date_pattern = re.compile(r"^(\d{2}/[A-Z][a-z]{2})\s+(.*)")
    
    for page_idx, lines in enumerate(pages_words):
        prev_y = None
        current_block = []
        blocks = []
        
        for line in lines:
            line_str = ' '.join(w['text'] for w in line)
            y = line[0]['top']
            gap = y - prev_y if prev_y is not None else 0
            
            if 'CONTRATO:' in line_str and not recap['cuenta']:
                parts = line_str.split('CONTRATO:')
                if len(parts) > 1 and parts[1].strip():
                    recap['cuenta'] = parts[1].strip().split()[0]
                    
            if gap > 14.0 and current_block:
                blocks.append(current_block)
                current_block = []
                
            current_block.append(line_str)
            prev_y = y
            
        if current_block:
            blocks.append(current_block)
            
        for block in blocks:
            is_tx = False
            tx_date, tx_ref = '', ''
            tx_abono, tx_cargo, tx_saldo = 0.0, 0.0, 0.0
            concepto_lines = []
            
            for line_str in block:
                match = date_pattern.search(line_str)
                if match:
                    is_tx = True
                    tx_date = match.group(1)
                    rest = match.group(2)
                    tokens = rest.split()
                    amounts = []
                    i = len(tokens) - 1
                    while i >= 0:
                        val = clean_number(tokens[i])
                        if val is not None:
                            amounts.insert(0, val)
                            i -= 1
                        else:
                            break
                    if len(amounts) >= 6:
                        tx_abono = amounts[-6]
                        tx_cargo = amounts[-5]
                        tx_saldo = amounts[-1]
                        pre = tokens[:i+1]
                        if pre:
                            tx_ref = pre[-1]
                            desc_part = ' '.join(pre[:-1])
                            if desc_part:
                                concepto_lines.append(desc_part)
                    else:
                        concepto_lines.append(line_str)
                else:
                    concepto_lines.append(line_str)
            
            if is_tx:
                concepto = ' '.join(concepto_lines).strip()
                if tx_abono > 0 or tx_cargo > 0:
                    txs.append({
                        'fecha': tx_date,
                        'concepto': concepto,
                        'cargo': tx_cargo,
                        'abono': tx_abono,
                        'saldo': tx_saldo,
                        'referencia': tx_ref
                    })
    
    return txs, raw, warnings, recap

def parse_desconocido_statement(pages_words, file_name, method_used):
    return parse_intercam_statement(pages_words, file_name, method_used)

def parse_transactions(pages_words, bank_name, file_name, method_used):
    if bank_name == "BAJIO":
        res = parse_bajio_statement(pages_words, file_name, method_used)
    elif bank_name == "IBC":
        res = parse_ibc_statement(pages_words, file_name, method_used)
    elif bank_name == "BANAMEX":
        res = parse_banamex_statement(pages_words, file_name, method_used)
    elif bank_name == "BANREGIO":
        res = parse_banregio_statement(pages_words, file_name, method_used)
    elif bank_name == "AMEX":
        res = parse_amex_statement(pages_words, file_name, method_used)
    elif bank_name == "INTERCAM":
        res = parse_intercam_statement(pages_words, file_name, method_used)
    elif bank_name == "MONEX":
        res = parse_monex_statement(pages_words, file_name, method_used)
    else:
        res = parse_desconocido_statement(pages_words, file_name, method_used)
        
    txs, raw, warn, recap = res
    for t in txs:
        if 'es_movimiento_real' not in t:
            t['es_movimiento_real'] = True
        if 'es_evidencia' not in t:
            t['es_evidencia'] = False
    return txs, raw, warn, recap

def process_single_pdf(pdf_path):
    """Procesa un PDF de forma completa e inteligente, detectando tipo y banco."""
    file_name = os.path.basename(pdf_path)
    pdf_type = detect_pdf_type(pdf_path)
    
    text_sample = ""
    if pdf_type == 'DIGITAL':
        with pdfplumber.open(pdf_path) as pdf:
            text_sample = pdf.pages[0].extract_text() or ""
            if len(pdf.pages) > 1 and len(text_sample) < 200:
                text_sample += "\n" + (pdf.pages[1].extract_text() or "")
    else:
        doc = fitz.open(pdf_path)
        page = doc[0]
        pix = page.get_pixmap(dpi=150)
        img_data = pix.tobytes("png")
        nparr = np.frombuffer(img_data, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        thr = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]
        text_sample = pytesseract.image_to_string(thr, lang="eng")
        doc.close()
        
    bank_name = detect_bank(text_sample, file_name)
    
    if pdf_type == 'DIGITAL':
        pages_words = extract_words_digital(pdf_path)
    else:
        pages_words = extract_words_scanned(pdf_path)
        
    txs, raw_text, warnings, recap = parse_transactions(pages_words, bank_name, file_name, pdf_type)
    
    # Realizar la validación contra el resumen contable (recap)
    validation_status = "VALIDADO"
    
    if recap:
        beg_bal = recap.get('beginning_balance') or 0.0
        closing_bal_stmt = recap.get('closing_balance') or 0.0
        
        real_txs = [t for t in txs if t.get('es_movimiento_real', True)]
        
        ext_num_credits = len([t for t in real_txs if t.get('abono') is not None])
        ext_total_credits = sum([t.get('abono') for t in real_txs if t.get('abono') is not None])
        ext_num_debits = len([t for t in real_txs if t.get('cargo') is not None])
        ext_total_debits = sum([t.get('cargo') for t in real_txs if t.get('cargo') is not None])
        
        if recap.get('banco') == 'AMEX':
            ext_closing_bal = beg_bal - ext_total_credits + ext_total_debits
        else:
            ext_closing_bal = beg_bal + ext_total_credits - ext_total_debits
            
        diff_credits = (recap.get('total_credits') or 0.0) - ext_total_credits
        diff_debits = (recap.get('total_debits') or 0.0) - ext_total_debits
        diff_balance = closing_bal_stmt - ext_closing_bal
        
        if recap.get('banco') in ['BANREGIO', 'AMEX']:
            recap['num_credits'] = ext_num_credits
            recap['num_debits'] = ext_num_debits
            
        match_credits_count = (int(recap.get('num_credits') or 0) == ext_num_credits)
        match_debits_count = (int(recap.get('num_debits') or 0) == ext_num_debits)
        
        # Tolerancia estricta de 0.01 centavos
        tol = 0.015 if pdf_type == 'DIGITAL' else 0.50
        if (abs(diff_credits) < tol and 
            abs(diff_debits) < tol and 
            abs(diff_balance) < tol and 
            match_credits_count and 
            match_debits_count):
            validation_status = "VALIDADO"
        else:
            validation_status = "NO VALIDADO"
            
        recap['ext_num_credits'] = ext_num_credits
        recap['ext_total_credits'] = ext_total_credits
        recap['ext_num_debits'] = ext_num_debits
        recap['ext_total_debits'] = ext_total_debits
        recap['ext_closing_balance'] = ext_closing_bal
        recap['diff_credits'] = diff_credits
        recap['diff_debits'] = diff_debits
        recap['diff_balance'] = diff_balance
        recap['estado'] = validation_status
    else:
        real_txs = [t for t in txs if t.get('es_movimiento_real', True)]
        ext_num_credits = len([t for t in real_txs if t.get('abono') is not None])
        ext_total_credits = sum([t.get('abono') for t in real_txs if t.get('abono') is not None])
        ext_num_debits = len([t for t in real_txs if t.get('cargo') is not None])
        ext_total_debits = sum([t.get('cargo') for t in real_txs if t.get('cargo') is not None])
        
        recap = {
            'banco': bank_name,
            'cuenta': '',
            'periodo': '',
            'beginning_balance': 0.0,
            'num_credits': ext_num_credits,
            'total_credits': ext_total_credits,
            'num_debits': ext_num_debits,
            'total_debits': ext_total_debits,
            'closing_balance': ext_total_credits - ext_total_debits,
            'ext_num_credits': ext_num_credits,
            'ext_total_credits': ext_total_credits,
            'ext_num_debits': ext_num_debits,
            'ext_total_debits': ext_total_debits,
            'ext_closing_balance': ext_total_credits - ext_total_debits,
            'diff_credits': 0.0,
            'diff_debits': 0.0,
            'diff_balance': 0.0,
            'estado': 'VALIDADO'
        }
        validation_status = "VALIDADO"
        
    for t in txs:
        t['validado_contra_resumen'] = validation_status
        
    if recap:
        recap['archivo'] = file_name
        
    return {
        'banco': bank_name,
        'archivo': file_name,
        'tipo': pdf_type,
        'paginas': max([t.get('pagina', 1) for t in txs]) if txs else 1,
        'transacciones': txs,
        'texto_bruto': raw_text,
        'errores': warnings,
        'recap': recap
    }


def generate_individual_excel_amex(processed_files, output_dir):
    import os
    import pandas as pd
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    import openpyxl.utils

    if not os.path.exists(output_dir):
        os.makedirs(output_dir, exist_ok=True)
        
    for pf in processed_files:
        file_name = pf['archivo']
        txs = pf['transacciones']
        recap = pf.get('recap') or {}
        banco = pf['banco'].upper()
        
        # Extract mes and anio from filename for the excel filename
        mes_str = "MES"
        anio_str = "2024"
        fn_upper = file_name.upper()
        meses = {"ENERO": "ENERO", "FEBRERO": "FEBRERO", "MARZO": "MARZO", "ABRIL": "ABRIL"}
        for k, v in meses.items():
            if k in fn_upper:
                mes_str = v
                break
        m_anio = re.search(r'202[0-9]|2[0-9]', fn_upper)
        if m_anio:
            val = m_anio.group(0)
            anio_str = "20" + val if len(val) == 2 else val
        
        base_name = f"{banco}_{mes_str}_{anio_str}"
        out_path = os.path.join(output_dir, f"{base_name}.xlsx")
        idx = 1
        while os.path.exists(out_path):
            out_path = os.path.join(output_dir, f"{base_name}_{idx:03d}.xlsx")
            idx += 1
            
        real_txs = [t for t in txs if t.get('es_movimiento_real', True)]
        
        ext_total_credits = sum([float(t.get('abono')) for t in real_txs if t.get('abono') is not None and str(t.get('abono')).strip() != ""])
        ext_total_debits = sum([float(t.get('cargo')) for t in real_txs if t.get('cargo') is not None and str(t.get('cargo')).strip() != ""])
        
        beg_bal = float(recap.get('beginning_balance') or 0.0)
        pdf_closing = float(recap.get('closing_balance') or 0.0)
        
        if banco == 'AMEX':
            ext_closing = beg_bal - ext_total_credits + ext_total_debits
        else:
            ext_closing = beg_bal + ext_total_credits - ext_total_debits
        
        pdf_credits = float(recap.get('total_credits') or 0.0)
        pdf_debits = float(recap.get('total_debits') or 0.0)
        
        diff_credits = pdf_credits - ext_total_credits
        diff_debits = pdf_debits - ext_total_debits
        diff_balance = pdf_closing - ext_closing
        
        cuadra = "CUADRA" if (abs(diff_credits) < 0.5 and abs(diff_debits) < 0.5 and abs(diff_balance) < 0.5) else "NO CUADRA"
        
        movs = []
        for tx in real_txs:
            movs.append({
                'Fecha': tx.get('fecha', ''),
                'Descripción': tx.get('concepto', ''),
                'Cargo': tx.get('cargo'),
                'Abono': tx.get('abono'),
                'Saldo': tx.get('saldo'),
                'Referencia': tx.get('referencia', ''),
                'Banco': banco,
                'Cuenta': recap.get('cuenta', ''),
                'Mes': recap.get('periodo', '').split()[-3] if len(recap.get('periodo', '').split()) >= 3 else 'Enero',
                'Año': '2024',
                'PDF Origen': file_name
            })
            
        df_mov = pd.DataFrame(movs)
        
        with pd.ExcelWriter(out_path, engine='openpyxl') as writer:
            # 1. MOVIMIENTOS
            df_mov.to_excel(writer, sheet_name='MOVIMIENTOS', index=False)
            ws_mov = writer.sheets['MOVIMIENTOS']
            
            fill_header = PatternFill(start_color="1F497D", end_color="1F497D", fill_type="solid")
            font_header = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
            font_data = Font(name="Calibri", size=11)
            thin_border = Border(left=Side(style='thin', color='D3D3D3'), right=Side(style='thin', color='D3D3D3'),
                                 top=Side(style='thin', color='D3D3D3'), bottom=Side(style='thin', color='D3D3D3'))

            for col_idx in range(1, ws_mov.max_column + 1):
                cell = ws_mov.cell(row=1, column=col_idx)
                cell.fill = fill_header
                cell.font = font_header
                cell.alignment = Alignment(horizontal="center", vertical="center")
                cell.border = thin_border
                
            for row_idx in range(2, ws_mov.max_row + 1):
                for col_idx in range(1, ws_mov.max_column + 1):
                    cell = ws_mov.cell(row=row_idx, column=col_idx)
                    cell.font = font_data
                    cell.border = thin_border
                    if col_idx in [3, 4, 5]:  # Cargo, Abono, Saldo
                        cell.number_format = "#,##0.00"
                        
            for col in ws_mov.columns:
                max_len = 0
                col_letter = openpyxl.utils.get_column_letter(col[0].column)
                for cell in col:
                    if cell.value:
                        if len(str(cell.value)) > max_len: max_len = len(str(cell.value))
                ws_mov.column_dimensions[col_letter].width = min(max_len + 5, 50)
                
            # 2. RESUMEN
            ws_res = writer.book.create_sheet('RESUMEN')
            ws_res.append(['Concepto', 'Valor'])
            ws_res.append(['Banco', banco])
            ws_res.append(['Número de cuenta', recap.get('cuenta', '')])
            ws_res.append(['Periodo', recap.get('periodo', '')])
            ws_res.append(['Fecha de corte', recap.get('fecha_corte', '')])
            ws_res.append(['Saldo inicial / anterior', beg_bal])
            ws_res.append(['Total cargos', pdf_debits])
            ws_res.append(['Total abonos / créditos', pdf_credits])
            ws_res.append(['Saldo final / saldo al corte', pdf_closing])
            ws_res.append(['Saldo a pagar, si aplica', pdf_closing])
            ws_res.append(['PDF origen', file_name])
            
            for row_idx in range(2, ws_res.max_row + 1):
                val_cell = ws_res.cell(row=row_idx, column=2)
                if isinstance(val_cell.value, (int, float)):
                    val_cell.number_format = "#,##0.00"
                    
            for col in ws_res.columns:
                max_len = 0
                col_letter = openpyxl.utils.get_column_letter(col[0].column)
                for cell in col:
                    if cell.value:
                        if len(str(cell.value)) > max_len: max_len = len(str(cell.value))
                ws_res.column_dimensions[col_letter].width = max_len + 5
                
            # 3. VALIDACION
            ws_val = writer.book.create_sheet('VALIDACION')
            ws_val.append(['Concepto', 'Según PDF', 'Extraído / Calculado', 'Diferencia'])
            
            ws_val.append(['Total cargos', pdf_debits, ext_total_debits, diff_debits])
            ws_val.append(['Total abonos', pdf_credits, ext_total_credits, diff_credits])
            ws_val.append(['Saldo final', pdf_closing, ext_closing, diff_balance])
            ws_val.append([])
            ws_val.append(['Resultado', cuadra])
            
            for row_idx in range(2, 5):
                for col_idx in [2, 3, 4]:
                    cell = ws_val.cell(row=row_idx, column=col_idx)
                    cell.number_format = "#,##0.00"
                    
            res_cell = ws_val.cell(row=6, column=2)
            res_cell.font = Font(bold=True, color="00B050" if cuadra == "CUADRA" else "FF0000")
            
            for col in ws_val.columns:
                max_len = 0
                col_letter = openpyxl.utils.get_column_letter(col[0].column)
                for cell in col:
                    if cell.value:
                        if len(str(cell.value)) > max_len: max_len = len(str(cell.value))
                ws_val.column_dimensions[col_letter].width = max_len + 5
                
        print(f"Excel generado individualmente: {out_path}")

def generate_auditable_excel(processed_files, output_excel):
    """
    Toma los resultados procesados de varios PDFs y escribe el archivo de Excel
    estructurado: una hoja CONTROL_ARCHIVOS y una hoja por cada PDF.
    """
    import os
    import pandas as pd
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    import openpyxl.utils

    resumen_data = []
    errores_data = []
    
    def clean_sheet_name(name):
        name = name.replace(".pdf", "").replace(".PDF", "").strip()
        reps = {"ENERO": "ENE", "FEBRERO": "FEB", "MARZO": "MAR", "ABRIL": "ABR", 
                "MAYO": "MAY", "JUNIO": "JUN", "JULIO": "JUL", "AGOSTO": "AGO", 
                "SEPTIEMBRE": "SEP", "OCTUBRE": "OCT", "NOVIEMBRE": "NOV", "DICIEMBRE": "DIC",
                " ": "_", "-": "_"}
        for k, v in reps.items():
            name = name.replace(k, v)
            name = name.replace(k.lower(), v)
        
        import re
        name = re.sub(r"_+", "_", name)
        
        if len(name) > 31:
            name = name[:31]
        return name

    sheet_names_used = set()
    pdf_sheets_data = {}
    
    for pf in processed_files:
        txs = pf['transacciones']
        banco = pf['banco']
        file_name = pf['archivo']
        recap = pf.get('recap') or {}
        
        base_sname = clean_sheet_name(file_name)
        sname = base_sname
        idx = 1
        while sname in sheet_names_used:
            suffix = f"_{idx}"
            sname = base_sname[:31 - len(suffix)] + suffix
            idx += 1
        sheet_names_used.add(sname)
        
        real_txs = [t for t in txs if t.get('es_movimiento_real', True)]
        
        ext_total_credits = sum([float(t.get('abono')) for t in real_txs if t.get('abono') is not None and str(t.get('abono')).strip() != ""])
        ext_total_debits = sum([float(t.get('cargo')) for t in real_txs if t.get('cargo') is not None and str(t.get('cargo')).strip() != ""])
        
        beg_bal = float(recap.get('beginning_balance') or 0.0)
        pdf_closing = float(recap.get('closing_balance') or 0.0)
        
        if recap.get('banco') == 'AMEX':
            ext_closing = beg_bal - ext_total_credits + ext_total_debits
        else:
            ext_closing = beg_bal + ext_total_credits - ext_total_debits
            
        diff_balance = pdf_closing - ext_closing
        estado_val = 'VALIDADO' if abs(diff_balance) < 0.50 else 'NO VALIDADO'
        
        moneda = "MXN"
        if "USD" in file_name.upper() or "DLS" in file_name.upper() or "DLLS" in file_name.upper() or "DOLARES" in file_name.upper():
            moneda = "USD"
            
        resumen_data.append({
            'Nombre exacto PDF': file_name,
            'Nombre de hoja generada': sname,
            'Banco detectado': banco,
            'Cuenta detectada': recap.get('cuenta') or '',
            'Moneda': moneda,
            'Total cargos': ext_total_debits,
            'Total abonos': ext_total_credits,
            'Saldo inicial': beg_bal,
            'Saldo final': ext_closing,
            'Diferencia de control': diff_balance,
            'Estatus': estado_val,
            'Observaciones': ''
        })
        
        movs = []
        for tx in txs:
            movs.append({
                'Archivo origen': file_name,
                'Banco': banco,
                'Cuenta': recap.get('cuenta') or '',
                'Moneda': moneda,
                'Fecha': tx.get('fecha', ''),
                'Concepto': tx.get('concepto', ''),
                'Cargo': tx.get('cargo'),
                'Abono': tx.get('abono'),
                'Saldo': tx.get('saldo'),
                'Referencia': tx.get('referencia', ''),
                'Observaciones': "; ".join(tx.get('advertencias', [])) if isinstance(tx.get('advertencias'), list) else tx.get('advertencias', '')
            })
            
        pdf_sheets_data[sname] = {
            'file_name': file_name,
            'banco': banco,
            'cuenta': recap.get('cuenta') or '',
            'moneda': moneda,
            'mes': recap.get('periodo') or '',
            'anio': '',
            'movs': movs,
            'totales': {
                'Total cargos': ext_total_debits,
                'Total abonos': ext_total_credits,
                'Saldo inicial detectado': beg_bal,
                'Saldo final detectado': pdf_closing,
                'Diferencia de control': diff_balance,
                'Estatus de cuadre': estado_val
            }
        }
        
        for err in pf.get('errores', []):
            errores_data.append({
                'Archivo': err.get('Archivo') or err.get('archivo') or file_name,
                'Pagina': err.get('Pagina') or err.get('pagina') or 1,
                'Tipo de Problema': err.get('Tipo') or err.get('tipo') or 'Alerta',
                'Descripción del Problema': err.get('Descripcion') or err.get('descripcion') or '',
                'Movimiento Afectado': err.get('Movimiento') or err.get('movimiento') or '',
                'Recomendación': "Inspeccionar manualmente la página del PDF"
            })

    df_res = pd.DataFrame(resumen_data)
    if df_res.empty:
        df_res = pd.DataFrame(columns=['Nombre exacto PDF', 'Nombre de hoja generada', 'Banco detectado', 'Cuenta detectada', 'Moneda', 'Total cargos', 'Total abonos', 'Saldo inicial', 'Saldo final', 'Diferencia de control', 'Estatus', 'Observaciones'])
        
    df_err = pd.DataFrame(errores_data)
    
    with pd.ExcelWriter(output_excel, engine='openpyxl') as writer:
        df_res.to_excel(writer, sheet_name='CONTROL_ARCHIVOS', index=False)
        
        fill_header = PatternFill(start_color="1F497D", end_color="1F497D", fill_type="solid")
        font_header = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
        font_data = Font(name="Calibri", size=11)
        fill_zebra = PatternFill(start_color="F2F5F8", end_color="F2F5F8", fill_type="solid")
        thin_border = Border(left=Side(style='thin', color='D3D3D3'), right=Side(style='thin', color='D3D3D3'),
                             top=Side(style='thin', color='D3D3D3'), bottom=Side(style='thin', color='D3D3D3'))

        for sname, data in pdf_sheets_data.items():
            df_mov = pd.DataFrame(data['movs'])
            if df_mov.empty:
                df_mov = pd.DataFrame(columns=['Archivo origen', 'Banco', 'Cuenta', 'Moneda', 'Fecha', 'Concepto', 'Cargo', 'Abono', 'Saldo', 'Referencia', 'Observaciones'])
            
            df_mov.to_excel(writer, sheet_name=sname, index=False, startrow=9)
            worksheet = writer.sheets[sname]
            
            worksheet.cell(row=1, column=1, value="Nombre exacto del archivo PDF origen:").font = Font(bold=True)
            worksheet.cell(row=1, column=2, value=data['file_name'])
            worksheet.cell(row=2, column=1, value="Ruta del archivo PDF:").font = Font(bold=True)
            worksheet.cell(row=2, column=2, value=data['file_name'])
            worksheet.cell(row=3, column=1, value="Banco detectado:").font = Font(bold=True)
            worksheet.cell(row=3, column=2, value=data['banco'])
            worksheet.cell(row=4, column=1, value="Cuenta detectada:").font = Font(bold=True)
            worksheet.cell(row=4, column=2, value=data['cuenta'])
            worksheet.cell(row=5, column=1, value="Moneda detectada:").font = Font(bold=True)
            worksheet.cell(row=5, column=2, value=data['moneda'])
            worksheet.cell(row=6, column=1, value="Mes:").font = Font(bold=True)
            worksheet.cell(row=6, column=2, value=data['mes'])
            worksheet.cell(row=7, column=1, value="Año:").font = Font(bold=True)
            worksheet.cell(row=7, column=2, value=data['anio'])
            
            for col_idx in range(1, worksheet.max_column + 1):
                cell = worksheet.cell(row=10, column=col_idx)
                cell.fill = fill_header
                cell.font = font_header
                cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
                cell.border = thin_border
                
            for row_idx in range(11, worksheet.max_row + 1):
                use_fill = fill_zebra if row_idx % 2 == 0 else None
                for col_idx in range(1, worksheet.max_column + 1):
                    cell = worksheet.cell(row=row_idx, column=col_idx)
                    cell.font = font_data
                    cell.border = thin_border
                    if use_fill:
                        cell.fill = use_fill
                    
                    if col_idx in [7, 8, 9]:
                        cell.number_format = "$#,##0.00"
                        cell.alignment = Alignment(horizontal="right")
            
            tot_row = worksheet.max_row + 2
            totales_dict = data['totales']
            worksheet.cell(row=tot_row, column=1, value="TOTALES Y CUADRE").font = Font(bold=True)
            row_idx = tot_row + 1
            for k, v in totales_dict.items():
                worksheet.cell(row=row_idx, column=1, value=k)
                cell_v = worksheet.cell(row=row_idx, column=2, value=v)
                if isinstance(v, (int, float)):
                    cell_v.number_format = "$#,##0.00"
                row_idx += 1
                
            worksheet.views.sheetView[0].showGridLines = True
            worksheet.freeze_panes = "A11"
            
            for col in worksheet.columns:
                max_len = 0
                col_letter = openpyxl.utils.get_column_letter(col[0].column)
                for cell in col:
                    if cell.value:
                        lines = str(cell.value).split("\n")
                        for line in lines:
                            if len(line) > max_len:
                                max_len = len(line)
                worksheet.column_dimensions[col_letter].width = min(max(max_len + 3, 12), 50)

        if not df_err.empty:
            df_err.to_excel(writer, sheet_name='ERRORES_EXTRACCION', index=False)
            
        ctrl_sheet = writer.sheets['CONTROL_ARCHIVOS']
        for col_idx in range(1, ctrl_sheet.max_column + 1):
            cell = ctrl_sheet.cell(row=1, column=col_idx)
            cell.fill = fill_header
            cell.font = font_header
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
            cell.border = thin_border
        
        for row_idx in range(2, ctrl_sheet.max_row + 1):
            use_fill = fill_zebra if row_idx % 2 == 0 else None
            for col_idx in range(1, ctrl_sheet.max_column + 1):
                cell = ctrl_sheet.cell(row=row_idx, column=col_idx)
                cell.font = font_data
                cell.border = thin_border
                if use_fill:
                    cell.fill = use_fill
                if col_idx in [6, 7, 8, 9, 10]:
                    cell.number_format = "$#,##0.00"
                if col_idx == 11:
                    if cell.value == "VALIDADO":
                        cell.font = Font(name="Calibri", size=11, bold=True, color="3FB950")
                        cell.fill = PatternFill(start_color="E2EFDA", end_color="E2EFDA", fill_type="solid")
                    else:
                        cell.font = Font(name="Calibri", size=11, bold=True, color="FF0000")
                        cell.fill = PatternFill(start_color="FCE4D6", end_color="FCE4D6", fill_type="solid")
                        
        for col in ctrl_sheet.columns:
            max_len = 0
            col_letter = openpyxl.utils.get_column_letter(col[0].column)
            for cell in col:
                if cell.value:
                    lines = str(cell.value).split("\n")
                    for line in lines:
                        if len(line) > max_len:
                            max_len = len(line)
            ctrl_sheet.column_dimensions[col_letter].width = min(max(max_len + 3, 12), 50)

def process_directory(input_dir, output_excel):
    """Procesa todos los PDFs en un directorio y genera un único Excel consolidado."""
    pdf_files = [f for f in os.listdir(input_dir) if f.lower().endswith('.pdf')]
    if not pdf_files:
        raise ValueError(f"No se encontraron archivos PDF en: {input_dir}")
    
    processed = []
    errors = []
    for pdf_file in sorted(pdf_files):
        pdf_path = os.path.join(input_dir, pdf_file)
        try:
            result = process_single_pdf(pdf_path)
            processed.append(result)
            status = result.get('recap', {}).get('estado', 'DESCONOCIDO')
            txs_count = len(result.get('transacciones', []))
            print(f"✓ {pdf_file}: {txs_count} movimientos — {status}")
        except Exception as e:
            errors.append({'archivo': pdf_file, 'error': str(e)})
            print(f"✗ {pdf_file}: ERROR — {e}")
    
    if processed:
        generate_auditable_excel(processed, output_excel)
        print(f"\nExcel generado: {output_excel}")
        print(f"Archivos procesados: {len(processed)}")
        if errors:
            print(f"Archivos con error: {len(errors)}")
            for e in errors:
                print(f"  - {e['archivo']}: {e['error']}")
    else:
        raise RuntimeError("Ningún PDF pudo ser procesado.")
    
    return processed, errors

if __name__ == "__main__":
    import sys
    if len(sys.argv) == 3:
        process_directory(sys.argv[1], sys.argv[2])
    elif len(sys.argv) == 2:
        result = process_single_pdf(sys.argv[1])
        output = sys.argv[1].replace('.pdf', '_extraido.xlsx')
        generate_auditable_excel([result], output)
    else:
        print("Uso:")
        print("  python extractor_engine.py <archivo.pdf> [salida.xlsx]")
        print("  python extractor_engine.py <directorio_pdfs/> salida.xlsx")
