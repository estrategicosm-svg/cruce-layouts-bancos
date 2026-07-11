from datetime import datetime
from decimal import Decimal

from conciliacion.conciliador_ingresos import ConciliadorIngresos
from core.models import CFDI, CedulaIngresoRegistro, MovimientoBancario


def _registro(uuid: str, moneda: str, total: str, folio_transferencia: str) -> CedulaIngresoRegistro:
    return CedulaIngresoRegistro(
        uuid=uuid,
        cliente="Cliente",
        rfc="ABC010101AAA",
        factura="FAC-001",
        fecha=datetime(2026, 6, 1),
        total=Decimal(total),
        moneda=moneda,
        amount_mxn=Decimal(total) if moneda == "MXN" else Decimal("0"),
        amount_usd=Decimal(total) if moneda == "USD" else Decimal("0"),
        forma_pago="TRANSFERENCIA",
        folio_transferencia=folio_transferencia,
        descripcion="Servicio",
    )


def _cfdi(uuid: str, total: str) -> CFDI:
    return CFDI(
        uuid=uuid,
        rfc_emisor="ABC010101AAA",
        rfc_receptor="XAXX010101000",
        nombre_emisor="Cliente",
        nombre_receptor="Empresa",
        fecha=datetime(2026, 6, 1),
        subtotal=Decimal(total),
        iva=Decimal("0"),
        iva_retenido=Decimal("0"),
        isr_retenido=Decimal("0"),
        total=Decimal(total),
        moneda="MXN",
        tipo_cambio=Decimal("1"),
        tipo_cfdi="I",
        metodo_pago="PUE",
        forma_pago="03",
    )


def _movimiento(ref: str, monto: str) -> MovimientoBancario:
    return MovimientoBancario(
        banco="Banco",
        cuenta="123",
        fecha=datetime(2026, 6, 1),
        concepto="Pago",
        cargo=Decimal("0"),
        abono=Decimal(monto),
        moneda="MXN",
        referencia=ref,
    )


def test_registro_usd_no_concilia_contra_banco_mxn():
    registro = _registro("UUID-1", "USD", "5000.00", "TRF001")
    cfdi = _cfdi("UUID-1", "5000.00")
    movimiento = _movimiento("TRF001", "5000.00")

    conciliador = ConciliadorIngresos()
    resultado = conciliador.conciliar([registro], [cfdi], [movimiento])

    assert len(resultado.registros) == 1
    r = resultado.registros[0]
    assert r.folio_conciliacion is None
    assert r.cfdi is not None
    assert r.movimiento is None
    assert r.estatus == "SIN BANCO"


def test_registro_mxn_concilia_con_banco_mxn():
    registro = _registro("UUID-1", "MXN", "11600.00", "TRF001")
    cfdi = _cfdi("UUID-1", "11600.00")
    movimiento = _movimiento("TRF001", "11600.00")

    conciliador = ConciliadorIngresos()
    resultado = conciliador.conciliar([registro], [cfdi], [movimiento])

    assert len(resultado.registros) == 1
    r = resultado.registros[0]
    assert r.cfdi is not None
    assert r.movimiento is not None
    assert r.estatus == "CONCILIADO"


def test_folio_empieza_en_300():
    conciliador = ConciliadorIngresos()
    registros = [
        _registro("UUID-1", "MXN", "11600.00", "TRF001"),
        _registro("UUID-2", "MXN", "200.00", "TRF002"),
    ]
    cfdis = [_cfdi("UUID-1", "11600.00"), _cfdi("UUID-2", "200.00")]
    movimientos = [_movimiento("TRF001", "11600.00"), _movimiento("TRF002", "200.00")]

    resultado = conciliador.conciliar(registros, cfdis, movimientos)

    r1, r2 = resultado.registros
    assert r1.folio_conciliacion is None
    assert r2.folio_conciliacion is None

    folio = 300
    for r in resultado.registros:
        if r.cfdi is not None and r.movimiento is not None:
            r.folio_conciliacion = folio
            folio += 1

    assert r1.folio_conciliacion == 300
    assert r2.folio_conciliacion == 301


def test_registro_sin_xml_no_concilia():
    registro = _registro("UUID-INEXISTENTE", "MXN", "11600.00", "TRF001")
    conciliador = ConciliadorIngresos()
    resultado = conciliador.conciliar([registro], [], [])

    assert len(resultado.registros) == 1
    r = resultado.registros[0]
    assert r.cfdi is None
    assert r.movimiento is None
    assert r.estatus == "SIN XML"
