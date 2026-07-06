from __future__ import annotations

import io
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime
from decimal import Decimal
from typing import Optional

from core.models import CFDI


class XMLParser:
    NAMESPACES = {
        "cfdi4": "http://www.sat.gob.mx/cfd/4",
        "cfdi3": "http://www.sat.gob.mx/cfd/3",
        "tfd": "http://www.sat.gob.mx/TimbreFiscalDigital",
    }

    def __init__(self) -> None:
        self.errores: list[str] = []

    def parsear_xml(self, contenido: bytes, nombre_archivo: str | None = None) -> Optional[CFDI]:
        try:
            root = ET.fromstring(contenido)
            return self._extraer_datos(root, nombre_archivo)
        except Exception as exc:
            self.errores.append(f"{nombre_archivo or 'XML'}: {exc}")
            return None

    def parsear_zip(self, archivo_zip: bytes) -> list[CFDI]:
        resultados: list[CFDI] = []
        try:
            with zipfile.ZipFile(io.BytesIO(archivo_zip)) as zf:
                for nombre in zf.namelist():
                    if nombre.lower().endswith(".xml"):
                        cfdi = self.parsear_xml(zf.read(nombre), nombre)
                        if cfdi:
                            resultados.append(cfdi)
        except Exception as exc:
            self.errores.append(f"Error procesando ZIP: {exc}")
        return resultados

    def _extraer_datos(self, root: ET.Element, nombre_archivo: str | None) -> CFDI:
        ns = self._resolver_namespace(root)
        comprobante = root.attrib
        emisor = root.find("cfdi:Emisor", ns)
        receptor = root.find("cfdi:Receptor", ns)
        timbre = root.find(".//tfd:TimbreFiscalDigital", ns)
        fecha = comprobante.get("Fecha", "")

        return CFDI(
            uuid=(timbre.attrib.get("UUID", "") if timbre is not None else "").upper(),
            rfc_emisor=emisor.attrib.get("Rfc", "") if emisor is not None else "",
            rfc_receptor=receptor.attrib.get("Rfc", "") if receptor is not None else "",
            nombre_emisor=emisor.attrib.get("Nombre", "") if emisor is not None else "",
            nombre_receptor=receptor.attrib.get("Nombre", "") if receptor is not None else "",
            fecha=datetime.fromisoformat(fecha.replace("T", " ")) if fecha else datetime.min,
            subtotal=Decimal(comprobante.get("SubTotal", "0")),
            iva=self._sumar_impuestos(root, ns, "Traslado", "002"),
            iva_retenido=self._sumar_impuestos(root, ns, "Retencion", "002"),
            isr_retenido=self._sumar_impuestos(root, ns, "Retencion", "001"),
            total=Decimal(comprobante.get("Total", "0")),
            moneda=comprobante.get("Moneda", "MXN"),
            tipo_cambio=Decimal(comprobante.get("TipoCambio", "1")),
            tipo_cfdi=comprobante.get("TipoDeComprobante", ""),
            metodo_pago=comprobante.get("MetodoPago", ""),
            forma_pago=comprobante.get("FormaPago", ""),
            serie=comprobante.get("Serie", ""),
            folio=comprobante.get("Folio", ""),
            archivo=nombre_archivo,
            validado=True,
        )

    def _resolver_namespace(self, root: ET.Element) -> dict[str, str]:
        cfdi_uri = root.tag.split("}")[0].strip("{") if root.tag.startswith("{") else self.NAMESPACES["cfdi4"]
        return {"cfdi": cfdi_uri, "tfd": self.NAMESPACES["tfd"]}

    def _sumar_impuestos(self, root: ET.Element, ns: dict[str, str], nodo: str, impuesto: str) -> Decimal:
        total = Decimal("0")
        for elemento in root.findall(f".//cfdi:{nodo}", ns):
            if elemento.attrib.get("Impuesto") == impuesto:
                total += Decimal(elemento.attrib.get("Importe", "0"))
        return total
