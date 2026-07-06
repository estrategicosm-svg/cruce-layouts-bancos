from datetime import datetime
from decimal import Decimal

from conciliacion.conciliador import Conciliador
from core.models import CFDI, CedulaRegistro, MovimientoBancario


def _registro(poliza: str, uuid: str, cruce: str, importe: str) -> CedulaRegistro:
    return CedulaRegistro(
        poliza=poliza,
        cliente="Proveedor",
        rfc="ABC010101AAA",
        uuid=uuid,
        importe=Decimal(importe),
        base_iva_16=Decimal("100.00"),
        base_iva_8=Decimal("0"),
        base_iva_0=Decimal("0"),
        exentos=Decimal("0"),
        iva=Decimal("16.00"),
        retenciones=Decimal("0"),
        moneda="MXN",
        tipo_cambio=Decimal("1"),
        fecha_pago=datetime(2026, 6, 1),
        banco="Banco",
        cruce_bancario=cruce,
    )


def _cfdi(uuid: str, total: str) -> CFDI:
    return CFDI(
        uuid=uuid,
        rfc_emisor="ABC010101AAA",
        rfc_receptor="XAXX010101000",
        nombre_emisor="Proveedor",
        nombre_receptor="Empresa",
        fecha=datetime(2026, 6, 1),
        subtotal=Decimal(total),
        iva=Decimal("16.00"),
        iva_retenido=Decimal("0"),
        isr_retenido=Decimal("0"),
        total=Decimal(total),
        moneda="MXN",
        tipo_cambio=Decimal("1"),
        tipo_cfdi="I",
        metodo_pago="PUE",
        forma_pago="03",
    )


def _movimiento(ref: str, abono: str) -> MovimientoBancario:
    return MovimientoBancario(
        banco="Banco",
        cuenta="123",
        fecha=datetime(2026, 6, 1),
        concepto="Pago",
        cargo=Decimal("0"),
        abono=Decimal(abono),
        moneda="MXN",
        referencia=ref,
    )


def test_concilia_registro_con_xml_y_banco():
    registro = CedulaRegistro(
        poliza="P-1",
        cliente="Proveedor",
        rfc="ABC010101AAA",
        uuid="UUID-1",
        importe=Decimal("116.00"),
        base_iva_16=Decimal("100.00"),
        base_iva_8=Decimal("0"),
        base_iva_0=Decimal("0"),
        exentos=Decimal("0"),
        iva=Decimal("16.00"),
        retenciones=Decimal("0"),
        moneda="MXN",
        tipo_cambio=Decimal("1"),
        fecha_pago=datetime(2026, 6, 1),
        banco="Banco",
        cruce_bancario="REF1",
    )
    cfdi = CFDI(
        uuid="UUID-1",
        rfc_emisor="ABC010101AAA",
        rfc_receptor="XAXX010101000",
        nombre_emisor="Proveedor",
        nombre_receptor="Empresa",
        fecha=datetime(2026, 6, 1),
        subtotal=Decimal("100.00"),
        iva=Decimal("16.00"),
        iva_retenido=Decimal("0"),
        isr_retenido=Decimal("0"),
        total=Decimal("116.00"),
        moneda="MXN",
        tipo_cambio=Decimal("1"),
        tipo_cfdi="I",
        metodo_pago="PUE",
        forma_pago="03",
    )
    movimiento = MovimientoBancario(
        banco="Banco",
        cuenta="123",
        fecha=datetime(2026, 6, 1),
        concepto="Pago",
        cargo=Decimal("0"),
        abono=Decimal("116.00"),
        moneda="MXN",
        referencia="REF1",
    )

    resultado = Conciliador().conciliar([registro], [cfdi], [movimiento])

    assert resultado.conciliados == 1
    assert resultado.registros[0].estatus == "CONCILIADO"


def test_folio_conciliacion_consecutivo():
    registros = [
        _registro("P-1", "UUID-1", "REF1", "116.00"),
        _registro("P-2", "UUID-2", "REF2", "200.00"),
        _registro("P-3", "UUID-3", "REF_NADA", "300.00"),
    ]
    cfdis = [
        _cfdi("UUID-1", "116.00"),
        _cfdi("UUID-2", "200.00"),
        _cfdi("UUID-3", "300.00"),
    ]
    movimientos = [
        _movimiento("REF1", "116.00"),
        _movimiento("REF2", "200.00"),
    ]

    resultado = Conciliador().conciliar(registros, cfdis, movimientos)

    r1, r2, r3 = resultado.registros

    assert r1.folio_conciliacion == 1
    assert r2.folio_conciliacion == 2
    assert r3.folio_conciliacion is None

    assert r1.estatus == "CONCILIADO"
    assert r2.estatus == "CONCILIADO"
    assert r3.estatus == "SIN BANCO"
