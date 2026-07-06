# Conciliador SAT IVA

Aplicacion local en Python y Streamlit para apoyar la conciliacion contable, fiscal y bancaria en cedulas de devolucion de IVA.

## Uso rapido

```powershell
cd sat_conciliador_iva
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
streamlit run app.py
```

## Archivos esperados

- Cedula SAT: Excel con columnas equivalentes a `config/columnas_cedula.yaml`.
- Estado de cuenta: Excel con fecha, concepto, cargo, abono y alguna referencia bancaria.
- XML CFDI: ZIP con archivos `.xml`.

La aplicacion intenta reconocer columnas comunes aunque no coincidan exactamente con el nombre configurado.
