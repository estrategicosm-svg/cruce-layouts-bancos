from __future__ import annotations

import hashlib
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
from parsers.cedula_parser import CedulaParser
from parsers.xml_parser import XMLParser

ASSETS_DIR = Path(__file__).parent / "assets" / "plantillas"

LAYOUT_HASHES = {
    "LAYOUT_CEDULA_INGRESOS.xlsx": "832C2628B8F2EDF969425A06877399AEE08BA3F7380BC40B0ACDBA9126A553F0",
    "LAYOUT_CARGA_EGRESOS.xlsx": "7CFAC1C9FBB55326751723E475513C24A8D909E7252BB1CD72B0CAFFAB50BA5B",
}


def _verificar_layout(nombre: str) -> bool:
    """Verificar SHA-256 de un archivo de layout antes de servirlo."""
    filepath = ASSETS_DIR / nombre
    if not filepath.exists():
        return False
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest().upper() == LAYOUT_HASHES[nombre]


st.set_page_config(
    page_title="Conciliador SAT IVA",
    page_icon="SAT",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    .block-container { padding-top: 1.5rem; }
    .main-title { color: #17324d; font-size: 2rem; font-weight: 700; margin-bottom: .25rem; }
    .subtle { color: #56616b; margin-bottom: 1.2rem; }
    [data-testid="stMetricValue"] { font-size: 1.5rem; }
    </style>
    """,
    unsafe_allow_html=True,
)


class SATConciliatorApp:
    def __init__(self) -> None:
        self._init_state()

    def _init_state(self) -> None:
        defaults = {
            "cedula": None,
            "cedula_ingresos": None,
            "ingresos_folio_counter": 300,
            "ingresos_hash": None,
            "cfdis": None,
            "movimientos": None,
            "resultado": None,
            "reporte_excel": None,
            "errores": [],
            "pdf_df": None,
            "pdf_validacion": None,
            "pdf_filename": None,
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
                min_value=0.0,
                max_value=1000.0,
                value=1.0,
                step=0.5,
            )
            dias_tolerancia = st.slider("Dias de tolerancia para fechas", 0, 30, 5)

            st.divider()
            st.subheader("Archivos")

            st.markdown("**Descargables oficiales**")
            for nombre in ["LAYOUT_CEDULA_INGRESOS.xlsx", "LAYOUT_CARGA_EGRESOS.xlsx"]:
                label = "Descargar layout de Ingresos" if "INGRESOS" in nombre else "Descargar layout de Egresos"
                filepath = ASSETS_DIR / nombre
                if _verificar_layout(nombre):
                    with open(filepath, "rb") as f:
                        data = f.read()
                    st.download_button(
                        label=label,
                        data=data,
                        file_name=nombre,
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        use_container_width=True,
                        key=f"dl_{nombre}",
                    )
                else:
                    st.error(f"Archivo {nombre} no verificado (SHA-256 no coincide). Descarga bloqueada.")

            st.divider()

            cedula_file = st.file_uploader("Cedula de Egresos (IVA Acreditable)", type=["xlsx", "xls"])
            ingresos_file = st.file_uploader("Cedula de Ingresos (opcional)", type=["xlsx", "xls"])
            banco_file = st.file_uploader("Estado de cuenta Excel/PDF", type=["xlsx", "xls", "pdf"])
            moneda_banco = st.radio("Moneda del estado de cuenta", ["MXN", "USD"], horizontal=True)
            xml_zip = st.file_uploader("ZIP con CFDI XML", type=["zip"])

            confirmado_pdf = True
            if banco_file and banco_file.name.lower().endswith('.pdf'):
                st.warning("BETA: Extracción de PDF experimental.")
                if "pdf_df" not in st.session_state or st.session_state.get("pdf_filename") != banco_file.name:
                    from parsers.pdf_parser import BancoPDFParser
                    parser = BancoPDFParser()
                    with st.spinner("Extrayendo movimientos del PDF..."):
                        df, validacion = parser.parsear_pdf(banco_file.getvalue(), banco_file.name)
                        st.session_state.pdf_df = df
                        st.session_state.pdf_validacion = validacion
                        st.session_state.pdf_filename = banco_file.name
                        
                validacion = st.session_state.pdf_validacion
                if not validacion.get("valido"):
                    st.error("Advertencias detectadas en la extracción:")
                    for adv in validacion.get("advertencias", []):
                        st.write(f"- {adv}")
                    st.warning("Validar Excel antes de usarlo para conciliación.")
                    confirmado_pdf = st.checkbox("Continuar y Conciliar de todos modos")
                
                from io import BytesIO
                output = BytesIO()
                st.session_state.pdf_df.to_excel(output, index=False)
                st.download_button(
                    "Descargar Excel convertido del PDF",
                    data=output.getvalue(),
                    file_name=banco_file.name.replace(".pdf", ".xlsx").replace(".PDF", ".xlsx"),
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True,
                )

            if st.button("Procesar archivos", type="primary", use_container_width=True):
                if not cedula_file and not ingresos_file:
                    st.error("Sube al menos una cedula (egresos o ingresos).")
                elif not banco_file or not xml_zip:
                    st.error("Carga el estado de cuenta y el ZIP de XML.")
                elif banco_file.name.lower().endswith('.pdf') and not confirmado_pdf:
                    st.error("Revisa las advertencias y confirma manualmente para continuar.")
                else:
                    self._procesar(cedula_file, ingresos_file, banco_file, xml_zip, moneda_banco, Decimal(str(tolerancia)), dias_tolerancia)

            st.divider()
            if st.session_state.reporte_excel:
                st.download_button(
                    "Descargar Excel",
                    data=st.session_state.reporte_excel,
                    file_name="conciliacion_sat_iva.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True,
                )

    def _main(self) -> None:
        st.markdown('<div class="main-title">Conciliador SAT IVA</div>', unsafe_allow_html=True)
        st.markdown('<div class="subtle">Conciliacion contable, fiscal y bancaria para cedulas de devolucion.</div>', unsafe_allow_html=True)

        resultado = st.session_state.resultado
        cedula_ingresos = st.session_state.cedula_ingresos
        col1, col2, col3, col4, col5 = st.columns(5)
        col1.metric("Egresos", len(st.session_state.cedula or []))
        col2.metric("Ingresos", len(cedula_ingresos or []))
        col3.metric("XML CFDI", len(st.session_state.cfdis or []))
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
            st.write("Carga un ZIP con los XML CFDI. La app leera UUID, total, impuestos, moneda y timbre fiscal.")
        with cols[2]:
            st.subheader("Paso 3")
            st.write("Carga el estado de cuenta. Se conciliara por referencia y, si hace falta, por importe y fecha.")

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

    def _procesar(self, cedula_file, ingresos_file, banco_file, xml_zip, moneda_banco, tolerancia: Decimal, dias_tolerancia: int) -> None:
        with st.spinner("Procesando conciliacion..."):
            cedula_parser = CedulaParser()
            banco_parser = BancoParser()
            xml_parser = XMLParser()
            errores_totales: list[str] = []

            # --- Parse egresos ---
            cedula = cedula_parser.parsear_excel(cedula_file) if cedula_file else []
            errores_totales.extend(cedula_parser.errores)

            # --- Parse ingresos ---
            cedula_ingresos = st.session_state.cedula_ingresos
            if ingresos_file:
                ingresos_parser = CedulaIngresosParser()
                nuevo_hash = hash(ingresos_file.getvalue())
                if st.session_state.ingresos_hash != nuevo_hash:
                    cedula_ingresos = ingresos_parser.parsear_excel(ingresos_file)
                    st.session_state.cedula_ingresos = cedula_ingresos
                    st.session_state.ingresos_hash = nuevo_hash
                    st.session_state.ingresos_folio_counter = 300
                    st.info(f"Nueva cedula de Ingresos cargada: {len(cedula_ingresos)} registro(s)")
                else:
                    st.info(f"Cedula de Ingresos ya cargada: {len(cedula_ingresos)} registro(s)")
                errores_totales.extend(ingresos_parser.errores)

            # --- Parse banco ---
            if banco_file.name.lower().endswith('.pdf'):
                movimientos = banco_parser.parsear_dataframe(st.session_state.pdf_df)
            else:
                movimientos = banco_parser.parsear_excel(banco_file)
            errores_totales.extend(banco_parser.errores)

            # --- Parse ZIP ---
            resultado_zip = xml_parser.parsear_zip(xml_zip.getvalue())
            cfdis = resultado_zip.exitosos
            errores_totales.extend(xml_parser.errores)

            st.info(f"ZIP procesado: {resultado_zip.total} archivo(s) XML encontrado(s), "
                    f"{resultado_zip.exitosos_count} exitoso(s), "
                    f"{resultado_zip.fallos_count} fallido(s).")
            if resultado_zip.fallos_count > 0:
                with st.expander("Archivos que no se pudieron procesar"):
                    for fallo in resultado_zip.fallos:
                        st.write(f"- **{fallo['archivo']}**: {fallo['error']}")
            if resultado_zip.exitosos_count == 0 and resultado_zip.total > 0:
                st.error("Ningún XML pudo procesarse. Revisa los errores e inténtalo de nuevo.")
                return
            if resultado_zip.total == 0:
                st.warning("No se encontraron archivos .xml dentro del ZIP.")

            # --- Conciliar egresos ---
            conciliador = Conciliador(tolerancia=tolerancia, dias_tolerancia=dias_tolerancia)
            resultado = conciliador.conciliar(cedula, cfdis, movimientos)
            errores_totales.extend(resultado.errores)

            # --- Conciliar ingresos ---
            resultado_ingresos = None
            if cedula_ingresos:
                conc_ing = ConciliadorIngresos(tolerancia=tolerancia, dias_tolerancia=dias_tolerancia)
                resultado_ingresos = conc_ing.conciliar(
                    cedula_ingresos, cfdis, movimientos, moneda_banco,
                )
                folio = st.session_state.ingresos_folio_counter
                for reg in resultado_ingresos.registros:
                    if reg.moneda.upper() == moneda_banco.upper() and reg.cfdi is not None and reg.movimiento is not None and reg.folio_conciliacion is None:
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
            st.session_state.cfdis = cfdis
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
