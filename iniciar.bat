@"
@echo off
echo Carpeta antes de cd: %cd%
cd /d "C:\Users\USER\OneDrive - Sinergy IE SC\Documentos\11_CEDULA_IVA\sat_conciliador_iva"
echo Carpeta despues de cd: %cd%
echo Iniciando Conciliador SAT IVA...
streamlit run app.py
pause
"@ | Out-File -Encoding utf8 "C:\Users\USER\Desktop\test_iniciar.bat"