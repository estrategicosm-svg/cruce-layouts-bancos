from __future__ import annotations

import hashlib
import os
import tempfile
import zipfile
from decimal import Decimal
from pathlib import Path

import pandas as pd
import streamlit as st

from conciliacion.conciliador import Conciliador
from conciliacion.conciliador_ingresos import ConciliadorIngresos
from exportadores.excel_generator import ExcelGenerator
from exportadores.reportes import registros_a_dataframe, registros_ingresos_a_dataframe, resumen_a_dataframe
from parsers.banco_parser import BancoParser
from parsers.cedula_ingresos_parser import CedulaIngresosParser
from parsers.layout_detector import detectar_layout
from parsers.cedula_parser import CedulaParser
from parsers.xml_parser import XMLParser

ASSETS_DIR = Path(__file__).parent / "assets" / "plantillas"

LAYOUT_HASHES = {
    "LAYOUT_CEDULA_INGRESOS.xlsx": "832C2628B8F2EDF969425A06877399AEE08BA3F7380BC40B0ACDBA9126A553F0",
    "LAYOUT_CARGA_EGRESOS.xlsx": "7CFAC1C9FBB55326751723E475513C24A8D909E7252BB1CD72B0CAFFAB50BA5B",
}

_SYSTEM_DIRS = {"__MACOSX", ".DS_Store", "Thumbs.db", "__pycache__"}


def _verificar_layout(nombre: str) -> bool:
    filepath = ASSETS_DIR / nombre
    if not filepath.exists():
        return False
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest().upper() == LAYOUT_HASHES[nombre]


def _es_ruta_segura(nombre: str) -> bool:
    parts = Path(nombre).parts
    return not any(p.startswith(".") or p.startswith("__") or p in _SYSTEM_DIRS for p in parts)


def _procesar_zip_bancario(archivo_zip_bytes: bytes) -> tuple[list, list[str], pd.DataFrame | None]:
    """Extract and process bank statement ZIP. Returns (movimientos, errores, control_df)."""
    movimientos = []
    errores = []
    control_rows = []
    banco_parser = BancoParser()

    with tempfile.TemporaryDirectory() as tmpdir:
        zip_path = os.path.join(tmpdir, "estados.zip")
        with open(zip_path, "wb") as f:
            f.write(archivo_zip_bytes)

        try:
            with zipfile.ZipFile(zip_path) as zf:
                unsafe = [n for n in zf.namelist() if not _es_ruta_segura(n)]
                if unsafe:
                    errores.append(f"Archivos con rutas inseguras ignorados: {unsafe}")

                compatible = [
                    n for n in zf.namelist()
                    if _es_ruta_segura(n)
                    and not n.startswith("__")
                    and not n.endswith("/")
                    and any(n.lower().endswith(ext) for ext in (".pdf", ".xlsx", ".xls"))
                ]

                if not compatible:
                    errores.append("No se encontraron archivos compatibles (PDF, XLSX, XLS) en el ZIP.")
                    return movimientos, errores, None

                for name in compatible:
                    data = zf.read(name)
                    fname = Path(name).name
                    ext = Path(name).suffix.lower()
                    empresa = Path(name).parts[0] if len(Path(name).parts) > 1 else ""
                    error_archivo = ""
                    movs_count = 0
                    parser_tipo = ""
                    moneda_detectada = ""

                    try:
                        if ext == ".pdf":
                            from parsers.pdf_parser import BancoPDFParser
                            parser_tipo = "BancoPDFParser"
                            fd, tmp = tempfile.mkstemp(suffix=".pdf")
                            with os.fdopen(fd, "wb") as tmpf:
                                tmpf.write(data)
                            try:
                                df, validacion = BancoPDFParser().parsear_pdf(tmp, fname)
                                if df is not None and not df.empty:
                                    movs = banco_parser.parsear_dataframe(df)
                                    movimientos.extend(movs)
                                    movs_count = len(movs)
                                    if not df.empty:
                                        moneda_detectada = str(df.iloc[0].get("Moneda", ""))
                                else:
                                    errores.append(f"{fname}: sin movimientos extraidos.")
                            finally:
                                os.remove(tmp)
                        else:
                            parser_tipo = "BancoParser"
                            from io import BytesIO
                            df = pd.read_excel(BytesIO(data))
                            movs = banco_parser.parsear_dataframe(df)
                            movimientos.extend(movs)
                            movs_count = len(movs)
                            if not df.empty:
                                mon_col = next((c for c in df.columns if "moneda" in c.lower()), None)
                                if mon_col:
                                    moneda_detectada = str(df.iloc[0].get(mon_col, ""))
                    except Exception as exc:
                        error_archivo = str(exc)
                        errores.append(f"{fname}: {exc}")

                    control_rows.append({
                        "ARCHIVO": fname,
                        "EMPRESA": empresa,
                        "TIPO_DOCUMENTO": ext.upper().lstrip("."),
                        "PARSER": parser_tipo,
                        "MOVIMIENTOS_EXTRAIDOS": movs_count,
                        "MONEDA_DETECTADA": moneda_detectada or "NO_DETERMINADA",
                        "ERROR": error_archivo,
                        "ESTATUS": "OK" if not error_archivo else "ERROR",
                    })
        except Exception as exc:
            errores.append(f"Error procesando ZIP bancario: {exc}")

    control_df = pd.DataFrame(control_rows) if control_rows else None
    return movimientos, errores, control_df


class SATConciliatorApp:
    def __init__(self) -> None:
        self._init_state()

    def _init_state(self) -> None:
        defaults = {
            "cedula": None,
            "cedula_ingresos": None,
            "ingresos_folio_counter": 300,
            "ingresos_hash": None,
            "cfdis_emitidos": None,
            "cfdis_recibidos": None,
            "movimientos": None,
            "resultado": None,
            "reporte_excel": None,
            "errores": [],
            "bank_control_df": None,
        }
        for key, value in defaults.items():
            st.session_state.setdefault(key, value)

    def run(self) -> None:
        self._sidebar()
        self._main()

    def _sidebar(self) -> None:
        with st.sidebar:
            st.header("Configuracion")
            tolerancia = st.number_input(
                "Tolerancia de diferencia (MXN)",
                min_value=0.0, max_value=1000.0, value=1.0, step=0.5,
            )
            dias_tolerancia = st.slider("Dias de tolerancia para fechas", 0, 30, 5)

            st.divider()
            st.subheader("Descargables oficiales")
            for nombre in ["LAYOUT_CEDULA_INGRESOS.xlsx", "LAYOUT_CARGA_EGRESOS.xlsx"]:
                label = "Descargar layout de Ingresos" if "INGRESOS" in nombre else "Descargar layout de Egresos"
                filepath = ASSETS_DIR / nombre
                if _verificar_layout(nombre):
                    with open(filepath, "rb") as f:
                        data = f.read()
                    st.download_button(
                        label=label, data=data, file_name=nombre,
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        use_container_width=True, key=f"dl_{nombre}",
                    )
                else:
                    st.error(f"Archivo {nombre} no verificado (SHA-256 no coincide). Descarga bloqueada.")

            st.divider()
            st.subheader("Archivos de entrada")

            cedula_file = st.file_uploader("1. Cedula de Egresos", type=["xlsx", "xls"])
            ingresos_file = st.file_uploader("2. Cedula de Ingresos (opcional)", type=["xlsx", "xls"])
            banco_file = st.file_uploader(
                "3. Estados de cuenta (ZIP, PDF, XLSX, XLS)",
                type=["zip", "pdf", "xlsx", "xls"],
            )
            xml_emitidos_file = st.file_uploader("4. XML CFDI Emitidos (ZIP)", type=["zip"], key="xml_emitidos")
            xml_recibidos_file = st.file_uploader("5. XML CFDI Recibidos (ZIP)", type=["zip"], key="xml_recibidos")

            st.divider()
            st.subheader("Estado de carga")
            status = []
            status.append(f"Cedula Egresos: {'cargada' if cedula_file else 'no cargada'}")
            status.append(f"Cedula Ingresos: {'cargada' if ingresos_file else 'no cargada'}")
            status.append(f"Estados de Cuenta: {'cargados' if banco_file else 'no cargados'}")
            status.append(f"XML Emitidos: {'cargados' if xml_emitidos_file else 'no cargados'}")
            status.append(f"XML Recibidos: {'cargados' if xml_recibidos_file else 'no cargados'}")
            for s in status:
                icon = "+" if "carga" in s.split(":")[1].strip() else "-"
                st.caption(f"[{icon}] {s}")

            st.divider()
            if st.button("Procesar archivos", type="primary", use_container_width=True):
                if not banco_file:
                    st.error("Carga al menos un estado de cuenta (ZIP, PDF o Excel).")
                elif not xml_emitidos_file and not xml_recibidos_file:
                    st.error("Carga al menos un ZIP de XML (emitidos o recibidos).")
                else:
                    self._procesar(
                        cedula_file, ingresos_file, banco_file,
                        xml_emitidos_file, xml_recibidos_file,
                        Decimal(str(tolerancia)), dias_tolerancia,
                    )

            st.divider()
            if st.session_state.reporte_excel:
                st.download_button(
                    "Descargar Excel", data=st.session_state.reporte_excel,
                    file_name="conciliacion_sat_iva.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True,
                )

    def _main(self) -> None:
        st.markdown('<div class="main-title">Conciliador SAT IVA</div>', unsafe_allow_html=True)
        st.markdown('<div class="subtle">Conciliacion contable, fiscal y bancaria para cedulas de devolucion.</div>', unsafe_allow_html=True)

        resultado = st.session_state.resultado
        col1, col2, col3, col4, col5 = st.columns(5)
        col1.metric("Egresos", len(st.session_state.cedula or []))
        col2.metric("Ingresos", len(st.session_state.cedula_ingresos or []))
        cfdis_total = len(st.session_state.cfdis_emitidos or []) + len(st.session_state.cfdis_recibidos or [])
        col3.metric("XML CFDI", cfdis_total)
        col4.metric("Banco", len(st.session_state.movimientos or []))
        col5.metric("Conciliados", resultado.conciliados if resultado else 0)

        if resultado:
            self._mostrar_resultado(resultado)
        else:
            self._mostrar_inicio()

    def _mostrar_inicio(self) -> None:
        st.divider()
        cols = st.columns(3)
        with cols[0]:
            st.subheader("Paso 1")
            st.write("Carga la cedula SAT en Excel con UUID, importe, fecha de pago y referencia bancaria.")
        with cols[1]:
            st.subheader("Paso 2")
            st.write("Carga los XML CFDI emitidos y recibidos en ZIP separados.")
        with cols[2]:
            st.subheader("Paso 3")
            st.write("Carga el estado de cuenta (ZIP, PDF o Excel). Se conciliara por referencia y monto.")

    def _mostrar_resultado(self, resultado) -> None:
        st.divider()
        resumen_df = resumen_a_dataframe(resultado)
        registros_df = registros_a_dataframe(resultado)
        diferencias_df = registros_df[registros_df["Estatus"].astype(str).str.contains("DIFERENCIA|FUERA|MONEDA|DUPLICADO", na=False)]
        sin_xml_df = registros_df[registros_df["Estatus"] == "SIN XML"]
        sin_banco_df = registros_df[registros_df["Estatus"] == "SIN BANCO"]

        tabs_list = ["Resumen", "Registros", "Diferencias", "Sin XML", "Sin banco", "Validacion"]
        if st.session_state.cedula_ingresos:
            tabs_list.insert(1, "Ingresos")
        if st.session_state.bank_control_df is not None:
            tabs_list.append("Control ZIP")
        tabs = st.tabs(tabs_list)
        tab_idx = 0
        with tabs[tab_idx]:
            st.dataframe(resumen_df, use_container_width=True, hide_index=True)
        tab_idx += 1
        if st.session_state.cedula_ingresos:
            with tabs[tab_idx]:
                st.dataframe(self._ingresos_df(st.session_state.cedula_ingresos), use_container_width=True, hide_index=True)
            tab_idx += 1
        with tabs[tab_idx]:
            st.dataframe(registros_df, use_container_width=True, hide_index=True)
        tab_idx += 1
        with tabs[tab_idx]:
            st.dataframe(diferencias_df, use_container_width=True, hide_index=True)
        tab_idx += 1
        with tabs[tab_idx]:
            st.dataframe(sin_xml_df, use_container_width=True, hide_index=True)
        tab_idx += 1
        with tabs[tab_idx]:
            st.dataframe(sin_banco_df, use_container_width=True, hide_index=True)
        tab_idx += 1
        with tabs[tab_idx]:
            errores = st.session_state.errores
            if errores:
                st.dataframe(pd.DataFrame({"Errores": errores}), use_container_width=True, hide_index=True)
            else:
                st.success("No se registraron errores de procesamiento.")
        tab_idx += 1
        if st.session_state.bank_control_df is not None:
            with tabs[tab_idx]:
                st.dataframe(st.session_state.bank_control_df, use_container_width=True, hide_index=True)

    def _procesar(
        self, cedula_file, ingresos_file, banco_file,
        xml_emitidos_file, xml_recibidos_file,
        tolerancia: Decimal, dias_tolerancia: int,
    ) -> None:
        with st.spinner("Procesando conciliacion..."):
            errores_totales: list[str] = []

            # --- Validate and parse egresos ---
            cedula = []
            if cedula_file:
                cedula_parser = CedulaParser()
                cedula_parser.parsear_excel(cedula_file)
                cedula = cedula_parser.parsear_excel(cedula_file)
                errores_totales.extend(cedula_parser.errores)
                if cedula_parser.detection:
                    d = cedula_parser.detection
                    st.info(
                        f"Cedula Egresos: layout={d.layout_type.value}, "
                        f"hoja=DATOS, fila_encabezado={d.header_row + 1}, "
                        f"filas={len(cedula)}, columnas={d.columns_recognized}"
                    )

            # --- Validate and parse ingresos ---
            cedula_ingresos = st.session_state.cedula_ingresos
            if ingresos_file:
                ingresos_parser = CedulaIngresosParser()
                nuevo_hash = hash(ingresos_file.getvalue())
                if st.session_state.ingresos_hash != nuevo_hash:
                    cedula_ingresos = ingresos_parser.parsear_excel(ingresos_file)
                    st.session_state.cedula_ingresos = cedula_ingresos
                    st.session_state.ingresos_hash = nuevo_hash
                    st.session_state.ingresos_folio_counter = 300
                errores_totales.extend(ingresos_parser.errores)
                if ingresos_parser.detection:
                    d = ingresos_parser.detection
                    st.info(
                        f"Cedula Ingresos: layout={d.layout_type.value}, "
                        f"hoja=DATOS, fila_encabezado={d.header_row + 1}, "
                        f"filas={len(cedula_ingresos or [])}, columnas={d.columns_recognized}"
                    )

            # --- Parse banco (ZIP / PDF / XLSX) ---
            banco_parser = BancoParser()
            fname = banco_file.name.lower()
            if fname.endswith(".zip"):
                movimientos, bank_errors, control_df = _procesar_zip_bancario(banco_file.getvalue())
                errores_totales.extend(bank_errors)
                st.session_state.bank_control_df = control_df
                n_archivos = len(control_df) if control_df is not None else 0
                n_exitosos = len(control_df[control_df["ESTATUS"] == "OK"]) if control_df is not None else 0
                st.info(f"ZIP de estados de cuenta: {n_archivos} archivos, {n_exitosos} procesados, "
                        f"{len(movimientos)} movimientos extraidos.")
            elif fname.endswith(".pdf"):
                from parsers.pdf_parser import BancoPDFParser
                pdf_parser = BancoPDFParser()
                df, validacion = pdf_parser.parsear_pdf(banco_file.getvalue(), banco_file.name)
                movimientos = banco_parser.parsear_dataframe(df) if df is not None and not df.empty else []
                st.session_state.bank_control_df = None
            else:
                movimientos = banco_parser.parsear_excel(banco_file)
                st.session_state.bank_control_df = None
            errores_totales.extend(banco_parser.errores)

            xml_parser = XMLParser()

            # --- Parse XML emitidos ---
            cfdis_emitidos = []
            if xml_emitidos_file:
                resultado_emit = xml_parser.parsear_zip(xml_emitidos_file.getvalue(), origen_xml="EMITIDO")
                cfdis_emitidos = resultado_emit.exitosos
                st.info(f"XML emitidos: {resultado_emit.exitosos_count} exitoso(s), {resultado_emit.fallos_count} fallido(s).")
                if resultado_emit.fallos_count > 0:
                    for fallo in resultado_emit.fallos:
                        errores_totales.append(f"XML emitido - {fallo['archivo']}: {fallo['error']}")

            # --- Parse XML recibidos ---
            cfdis_recibidos = []
            if xml_recibidos_file:
                resultado_rec = xml_parser.parsear_zip(xml_recibidos_file.getvalue(), origen_xml="RECIBIDO")
                cfdis_recibidos = resultado_rec.exitosos
                st.info(f"XML recibidos: {resultado_rec.exitosos_count} exitoso(s), {resultado_rec.fallos_count} fallido(s).")
                if resultado_rec.fallos_count > 0:
                    for fallo in resultado_rec.fallos:
                        errores_totales.append(f"XML recibido - {fallo['archivo']}: {fallo['error']}")

            cfdis = cfdis_emitidos + cfdis_recibidos
            if not cfdis:
                st.warning("No se cargaron XML. La conciliacion fiscal no estara disponible.")
                cfdis = []

            st.session_state.cfdis_emitidos = cfdis_emitidos
            st.session_state.cfdis_recibidos = cfdis_recibidos

            # --- Conciliar egresos ---
            conciliador = Conciliador(tolerancia=tolerancia, dias_tolerancia=dias_tolerancia)
            resultado = conciliador.conciliar(cedula, cfdis, movimientos)
            errores_totales.extend(resultado.errores)

            # --- Conciliar ingresos ---
            resultado_ingresos = None
            if cedula_ingresos:
                conc_ing = ConciliadorIngresos(tolerancia=tolerancia, dias_tolerancia=dias_tolerancia)
                resultado_ingresos = conc_ing.conciliar(cedula_ingresos, cfdis, movimientos)
                folio = st.session_state.ingresos_folio_counter
                for reg in resultado_ingresos.registros:
                    if reg.cfdi is not None and reg.movimiento is not None and reg.folio_conciliacion is None:
                        reg.folio_conciliacion = folio
                        folio += 1
                st.session_state.ingresos_folio_counter = folio
                st.session_state.cedula_ingresos = resultado_ingresos.registros
                errores_totales.extend(conc_ing.errores)

            # --- Armar Excel ---
            registros_df = registros_a_dataframe(resultado)
            datos_excel: dict[str, pd.DataFrame] = {
                "RESUMEN": resumen_a_dataframe(resultado),
                "CEDULA_SAT": registros_df,
                "DETALLE_XML": self._cfdis_df(cfdis),
                "ESTADOS_CUENTA": self._movimientos_df(movimientos, resultado, resultado_ingresos),
                "VALIDACION": pd.DataFrame({"Errores": errores_totales}),
            }
            if resultado_ingresos:
                datos_excel["CEDULA_INGRESOS"] = registros_ingresos_a_dataframe(resultado_ingresos)

            st.session_state.cedula = cedula
            st.session_state.movimientos = movimientos
            st.session_state.resultado = resultado
            st.session_state.errores = errores_totales
            st.session_state.reporte_excel = ExcelGenerator().generar_excel_bytes(datos_excel)
            st.success("Conciliacion terminada.")

    def _cfdis_df(self, cfdis) -> pd.DataFrame:
        return pd.DataFrame(
            [
                {
                    "UUID": cfdi.uuid,
                    "RFC emisor": cfdi.rfc_emisor,
                    "RFC receptor": cfdi.rfc_receptor,
                    "Fecha": cfdi.fecha,
                    "Subtotal": float(cfdi.subtotal),
                    "IVA": float(cfdi.iva),
                    "Total": float(cfdi.total),
                    "Moneda": cfdi.moneda,
                    "Origen": cfdi.origen_xml,
                    "Archivo": cfdi.archivo,
                }
                for cfdi in cfdis
            ]
        )

    def _ingresos_df(self, registros) -> pd.DataFrame:
        return pd.DataFrame(
            [
                {
                    "Folio": r.folio_conciliacion,
                    "RFC": r.rfc,
                    "Cliente": r.cliente,
                    "UUID": r.uuid,
                    "Factura": r.factura,
                    "Fecha": r.fecha,
                    "Total": float(r.total),
                    "Moneda": r.moneda,
                    "Estatus": r.estatus,
                }
                for r in registros
            ]
        )

    def _movimientos_df(self, movimientos, resultado=None, resultado_ingresos=None) -> pd.DataFrame:
        folio_map: dict[int, int] = {}
        if resultado:
            for reg in resultado.registros:
                if reg.folio_conciliacion and reg.movimiento:
                    folio_map[id(reg.movimiento)] = reg.folio_conciliacion
        if resultado_ingresos:
            for reg in resultado_ingresos.registros:
                if reg.folio_conciliacion and reg.movimiento:
                    folio_map[id(reg.movimiento)] = reg.folio_conciliacion
        return pd.DataFrame(
            [
                {
                    "Folio": folio_map.get(id(mov)),
                    "Banco": mov.banco,
                    "Cuenta": mov.cuenta,
                    "Fecha": mov.fecha,
                    "Concepto": mov.concepto,
                    "Cargo": float(mov.cargo),
                    "Abono": float(mov.abono),
                    "Monto": float(mov.monto),
                    "Referencia": mov.referencia,
                    "Moneda": mov.moneda,
                }
                for mov in movimientos
            ]
        )


if __name__ == "__main__":
    SATConciliatorApp().run()
