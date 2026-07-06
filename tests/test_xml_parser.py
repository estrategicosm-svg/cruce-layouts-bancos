import io
import struct
import zipfile

from parsers.xml_parser import XMLParser, ParseZipResult


def _valid_cfdi_xml(uuid: str = "VALID-UUID-001") -> bytes:
    return (
        '<cfdi:Comprobante xmlns:cfdi="http://www.sat.gob.mx/cfd/4" '
        'xmlns:tfd="http://www.sat.gob.mx/TimbreFiscalDigital" '
        'Fecha="2026-06-01T12:00:00" SubTotal="1000.00" Total="1160.00" '
        'Moneda="MXN" TipoCambio="1" TipoDeComprobante="I" MetodoPago="PUE" '
        'FormaPago="03">'
        '<cfdi:Emisor Rfc="AAA010101AAA" Nombre="EMISOR"/>'
        '<cfdi:Receptor Rfc="XAXX010101000" Nombre="RECEPTOR"/>'
        '<cfdi:Conceptos>'
        '<cfdi:Concepto>'
        '<cfdi:Impuestos>'
        '<cfdi:Traslados>'
        '<cfdi:Traslado Impuesto="002" TasaOCuota="0.160000" Importe="160.00"/>'
        '</cfdi:Traslados>'
        '</cfdi:Impuestos>'
        '</cfdi:Concepto>'
        '</cfdi:Conceptos>'
        '<cfdi:Complemento>'
        f'<tfd:TimbreFiscalDigital UUID="{uuid}"/>'
        '</cfdi:Complemento>'
        '</cfdi:Comprobante>'
    ).encode("utf-8")


def _crear_zip_con_password(data: dict[str, bytes], password: bytes) -> bytes:
    """Crea un ZIP con flag de encriptación (PKWARE) sin comprimir."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as zf:
        for name, content in data.items():
            zi = zipfile.ZipInfo(name)
            zi.compress_type = zipfile.ZIP_STORED
            zf.writestr(zi, content)
    raw = bytearray(buf.getvalue())
    for name in data:
        encoded = name.encode("utf-8")
        idx = raw.find(b"PK\x03\x04")
        while idx >= 0:
            name_len = struct.unpack_from("<H", raw, idx + 26)[0]
            if name_len == len(encoded) and raw[idx + 30:idx + 30 + name_len] == encoded:
                flag_bits = struct.unpack_from("<H", raw, idx + 6)[0]
                struct.pack_into("<H", raw, idx + 6, flag_bits | 0x01)
                break
            idx = raw.find(b"PK\x03\x04", idx + 1)
        idx = raw.find(b"PK\x01\x02")
        while idx >= 0:
            name_len = struct.unpack_from("<H", raw, idx + 28)[0]
            if name_len == len(encoded) and raw[idx + 46:idx + 46 + name_len] == encoded:
                flag_bits = struct.unpack_from("<H", raw, idx + 8)[0]
                struct.pack_into("<H", raw, idx + 8, flag_bits | 0x01)
                break
            idx = raw.find(b"PK\x01\x02", idx + 1)
    return bytes(raw)


def test_zip_mixto_reporta_conteos():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("valido.xml", _valid_cfdi_xml())
        zf.writestr("invalido.xml", b"<root><broken>")
        zf.writestr("otro_valido.xml", _valid_cfdi_xml("VALID-UUID-002"))

    parser = XMLParser()
    resultado = parser.parsear_zip(buf.getvalue())

    assert isinstance(resultado, ParseZipResult)
    assert resultado.total == 3
    assert resultado.exitosos_count == 2
    assert resultado.fallos_count == 1
    assert resultado.fallos[0]["archivo"] == "invalido.xml"
    assert resultado.exitosos[0].uuid == "VALID-UUID-001"
    assert resultado.exitosos[1].uuid == "VALID-UUID-002"
    assert len(parser.errores) >= 1


def test_zip_sin_xml_no_cuenta_fallos():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("readme.txt", b"no soy xml")
        zf.writestr("datos.csv", b"a,b,c")

    parser = XMLParser()
    resultado = parser.parsear_zip(buf.getvalue())

    assert resultado.total == 0
    assert resultado.exitosos_count == 0
    assert resultado.fallos_count == 0


def test_zip_con_password_reporta_error():
    data = {"cfdi.xml": _valid_cfdi_xml()}
    zip_bytes = _crear_zip_con_password(data, b"secret123")

    parser = XMLParser()
    resultado = parser.parsear_zip(zip_bytes)

    assert resultado.total == 1
    assert resultado.exitosos_count == 0
    assert resultado.fallos_count == 1
    assert "contrase" in resultado.fallos[0]["error"].lower() or "password" in resultado.fallos[0]["error"].lower()
    assert any("contrase" in e.lower() or "password" in e.lower() for e in parser.errores)


def test_zip_vacio_reporta_error():
    parser = XMLParser()
    resultado = parser.parsear_zip(b"")

    assert resultado.total == 0
    assert resultado.exitosos_count == 0
    assert resultado.fallos_count == 1
    assert resultado.fallos[0]["archivo"] == "(ZIP)"
    assert any("Error procesando ZIP" in e for e in parser.errores)
