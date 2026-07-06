from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from core.models import CFDI, CedulaIngresoRegistro, MovimientoBancario, ResultadoConciliacionIngresos


class ConciliadorIngresos:
    ESTATUS = {
        "CONCILIADO": "CONCILIADO",
        "DIFERENCIA": "DIFERENCIA DE IMPORTE",
        "SIN_XML": "SIN XML",
        "SIN_BANCO": "SIN BANCO",
        "MONEDA_DIF": "MONEDA DIFERENTE",
        "FECHA_FUERA": "FECHA FUERA DE RANGO",
        "REVISAR": "REVISAR MANUALMENTE",
    }

    def __init__(self, tolerancia: Decimal = Decimal("1.00"), dias_tolerancia: int = 5) -> None:
        self.tolerancia = tolerancia
        self.dias_tolerancia = dias_tolerancia
        self.errores: list[str] = []

    def conciliar(
        self,
        registros: list[CedulaIngresoRegistro],
        cfdis: list[CFDI],
        movimientos: list[MovimientoBancario],
        moneda_banco: str,
    ) -> ResultadoConciliacionIngresos:
        indices_cfdi = {cfdi.uuid.upper(): cfdi for cfdi in cfdis if cfdi.uuid}
        indices_bancarios: dict[str, list[MovimientoBancario]] = defaultdict(list)
        for mov in movimientos:
            if mov.cruce_bancario:
                indices_bancarios[mov.cruce_bancario].append(mov)

        resultados: list[CedulaIngresoRegistro] = []
        for registro in registros:
            if registro.moneda.upper() != moneda_banco.upper():
                resultados.append(registro)
                continue
            try:
                resultados.append(self._conciliar_registro(registro, indices_cfdi, indices_bancarios))
            except Exception as exc:
                self.errores.append(f"Error en UUID {registro.uuid}: {exc}")
                registro.estatus = self.ESTATUS["REVISAR"]
                resultados.append(registro)

        conciliados = sum(1 for r in resultados if r.estatus == self.ESTATUS["CONCILIADO"])
        sin_xml = sum(1 for r in resultados if r.estatus == self.ESTATUS["SIN_XML"])
        sin_banco = sum(1 for r in resultados if r.estatus == self.ESTATUS["SIN_BANCO"])
        diferencias = sum(1 for r in resultados if r.estatus == self.ESTATUS["DIFERENCIA"])

        return ResultadoConciliacionIngresos(
            total_registros=len(resultados),
            conciliados=conciliados,
            sin_xml=sin_xml,
            sin_banco=sin_banco,
            diferencias=diferencias,
            errores=self.errores,
            registros=resultados,
        )

    def _conciliar_registro(
        self,
        registro: CedulaIngresoRegistro,
        indices_cfdi: dict[str, CFDI],
        indices_bancarios: dict[str, list[MovimientoBancario]],
    ) -> CedulaIngresoRegistro:
        cfdi = indices_cfdi.get(registro.uuid)
        if not cfdi:
            registro.estatus = self.ESTATUS["SIN_XML"]
            registro.observaciones = "No se encontro XML por UUID"
            return registro

        registro.cfdi = cfdi
        observaciones: list[str] = []

        if abs(cfdi.total - registro.total) > self.tolerancia:
            observaciones.append(f"Diferencia XML vs cedula: {cfdi.total - registro.total}")
            registro.estatus = self.ESTATUS["DIFERENCIA"]

        movimiento = self._buscar_movimiento(registro, indices_bancarios)
        if movimiento:
            registro.movimiento = movimiento
            if abs(registro.total - movimiento.monto) > self.tolerancia:
                observaciones.append(f"Diferencia banco vs cedula: {movimiento.monto - registro.total}")
                registro.estatus = self.ESTATUS["DIFERENCIA"]
            if abs((registro.fecha - movimiento.fecha).days) > self.dias_tolerancia:
                observaciones.append("Fecha bancaria fuera de rango")
                registro.estatus = self.ESTATUS["FECHA_FUERA"]
        else:
            observaciones.append("No se encontro movimiento bancario por referencia o importe")
            if not registro.estatus:
                registro.estatus = self.ESTATUS["SIN_BANCO"]

        if not registro.estatus:
            registro.estatus = self.ESTATUS["CONCILIADO"]
        registro.observaciones = "; ".join(observaciones) or "OK"
        return registro

    def _buscar_movimiento(
        self,
        registro: CedulaIngresoRegistro,
        indices_bancarios: dict[str, list[MovimientoBancario]],
    ) -> MovimientoBancario | None:
        if registro.folio_transferencia:
            movimientos = indices_bancarios.get(registro.folio_transferencia, [])
            if len(movimientos) == 1:
                return movimientos[0]
            if len(movimientos) > 1:
                exactos = [mov for mov in movimientos if abs(mov.monto - registro.total) <= self.tolerancia]
                return exactos[0] if len(exactos) == 1 else None
        return self._busqueda_flexible(registro, indices_bancarios)

    def _busqueda_flexible(
        self,
        registro: CedulaIngresoRegistro,
        indices_bancarios: dict[str, list[MovimientoBancario]],
    ) -> MovimientoBancario | None:
        candidatos = [
            mov
            for movimientos in indices_bancarios.values()
            for mov in movimientos
            if abs(mov.monto - registro.total) <= self.tolerancia
            and abs((registro.fecha - mov.fecha).days) <= self.dias_tolerancia
        ]
        return candidatos[0] if len(candidatos) == 1 else None
