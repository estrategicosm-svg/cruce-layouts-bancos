from datetime import datetime
from decimal import Decimal

import pandas as pd
import pytest

from parsers.cedula_ingresos_parser import CedulaIngresosParser


def _dataframe_con_estructura_real() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "RFC": "ABC010101AAA",
                "Cliente": "Cliente A",
                "UUID A": "UUID-1",
                "No Factura": "FAC-001",
                "Fecha": "2026-06-01",
                "Total": 11600.00,
                "Moneda": "MXN",
                "Amount MXN": 11600.00,
                "Amount USD": 0.00,
                "Forma de Pago": "TRANSFERENCIA",
                "Folio de Transferencia o Cheque": "TRF001",
                "Descripcion": "Servicio de consultoria",
            },
            {
                "RFC": "DEF020202BBB",
                "Cliente": "Cliente B",
                "UUID A": "UUID-2",
                "No Factura": "FAC-002",
                "Fecha": "2026-06-15",
                "Total": 5000.00,
                "Moneda": "USD",
                "Amount MXN": 0.00,
                "Amount USD": 5000.00,
                "Forma de Pago": "CHEQUE",
                "Folio de Transferencia o Cheque": "CHQ001",
                "Descripcion": "Exportacion de servicios",
            },
        ]
    )


def test_parsea_estructura_correcta():
    df = _dataframe_con_estructura_real()
    parser = CedulaIngresosParser()
    registros = parser.parsear_dataframe(df)

    assert len(registros) == 2

    r1 = registros[0]
    assert r1.uuid == "UUID-1"
    assert r1.rfc == "ABC010101AAA"
    assert r1.cliente == "Cliente A"
    assert r1.factura == "FAC-001"
    assert r1.total == Decimal("11600.00")
    assert r1.moneda == "MXN"
    assert r1.amount_mxn == Decimal("11600.00")
    assert r1.amount_usd == Decimal("0")
    assert r1.forma_pago == "TRANSFERENCIA"
    assert r1.folio_transferencia == "TRF001"
    assert r1.descripcion == "Servicio de consultoria"

    r2 = registros[1]
    assert r2.uuid == "UUID-2"
    assert r2.moneda == "USD"
    assert r2.amount_mxn == Decimal("0")
    assert r2.amount_usd == Decimal("5000.00")
    assert r2.forma_pago == "CHEQUE"
    assert r2.folio_transferencia == "CHQ001"


def test_faltan_columnas_lanza_error():
    df = pd.DataFrame([{"Cliente": "X"}])
    parser = CedulaIngresosParser()
    with pytest.raises(ValueError, match="Faltan columnas requeridas"):
        parser.parsear_dataframe(df)
