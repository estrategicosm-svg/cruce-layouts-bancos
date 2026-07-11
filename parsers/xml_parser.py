from __future__ import annotations

import io
import zipfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Optional

from core.models import CFDI


@dataclass
class ParseZipResult:
    total: int = 0
    exitosos: list[CFDI] = field(default_factory=list)
    fallos: list[dict] = field(default_factory=list)

    @property
    def exitosos_count(self) -> int:
        return len(self.exitosos)

    @property
    def fallos_count(self) -> int:
        return len(self.fallos)


class XMLParser:
    NAMESPACES = {
        "cfdi4": "http://www.sat.gob.mx/cfd/4",
        "cfdi3": "http://www.sat.gob.mx/cfd/3",
        "tfd": "http://www.sat.gob.mx/TimbreFiscalDigital",
    }

    def __init__(self) -> None:
        self.errores: list[str] = []

    def parsear_xml(self, contenido: bytes, nombre_archivo: str | None = None, origen_xml: str = "") -> Optional[CFDI]:
        try:
            root = ET.fromstring(contenido)
            cfdi = self._extraer_datos(root, nombre_archivo)
            if cfdi and origen_xml:
                cfdi.origen_xml = origen_xml
            return cfdi
        except Exception as exc:
            self.errores.append(f"{nombre_archivo or 'XML'}: {exc}")
            return None

    def parsear_zip(self, archivo_zip: bytes, origen_xml: str = "") -> ParseZipResult:
        resultado = ParseZipResult()
        try:
            with zipfile.ZipFile(io.BytesIO(archivo_zip)) as zf:
                for nombre in zf.namelist():
                    if nombre.lower().endswith(".xml"):
                        resultado.total += 1
                        try:
                            contenido = zf.read(nombre)
                        except RuntimeError as exc:
                            msg = str(exc).lower()
                            if "password" in msg or "encrypted" in msg or "bad password" in msg:
                                error_msg = f"{nombre}: ZIP protegido con contraseña — no se pudo leer."
                            else:
                                error_msg = f"{nombre}: {exc}"
                            resultado.fallos.append({"archivo": nombre, "error": error_msg})
                            self.errores.append(error_msg)
                            continue
                        cfdi = self.parsear_xml(contenido, nombre, origen_xml)
                        if cfdi:
                            resultado.exitosos.append(cfdi)
                        else:
                            ultimo_error = self.errores[-1] if self.errores else "Error desconocido"
                            resultado.fallos.append({"archivo": nombre, "error": ultimo_error})
        except RuntimeError as exc:
            msg = str(exc).lower()
            if "password" in msg or "encrypted" in msg or "bad password" in msg:
                error_msg = "El ZIP está protegido con contraseña. Descomprímelo manualmente y sube los XML individuales."
            else:
                error_msg = f"Error procesando ZIP: {exc}"
            self.errores.append(error_msg)
            resultado.fallos.append({"archivo": "(ZIP)", "error": error_msg})
        except Exception as exc:
            error_msg = f"Error procesando ZIP: {exc}"
            self.errores.append(error_msg)
            resultado.fallos.append({"archivo": "(ZIP)", "error": error_msg})
        return resultado

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
