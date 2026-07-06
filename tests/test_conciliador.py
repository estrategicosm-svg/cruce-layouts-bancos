from datetime import datetime
from decimal import Decimal

from conciliacion.conciliador import Conciliador
from core.models import CFDI, CedulaRegistro, MovimientoBancario


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
