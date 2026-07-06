import fitz  # PyMuPDF

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
            # Filtrar códigos de barras o cadenas binarias de comprobantes largas
            if len(txt) >= 20 and all(c in '01' for c in txt):
                continue
            words_clean.append({
                'text': txt,
                'x0': w[0],
                'x1': w[2],
                'top': w[1],
                'bottom': w[3],
                'conf': 100.0
            })
        pages_words.append(group_words_into_lines(words_clean))
    doc.close()
    return pages_words

def clean_number(val):
    """Limpia un string para convertirlo a float/Decimal. Retorna None si no es numérico."""
    if not val:
        return None
    val_clean = str(val).upper().replace("$", "").replace(" ", "").replace(",", "").strip()
    is_cr = False
    if "CR" in val_clean:
        val_clean = val_clean.replace("CR", "")
        is_cr = True
    
    if val_clean.endswith(")"):
        val_clean = val_clean.replace("(", "").replace(")", "")
        if not is_cr:
            val_clean = "-" + val_clean
            
    try:
        f_val = float(val_clean)
        return -f_val if is_cr else f_val
    except ValueError:
        return None
