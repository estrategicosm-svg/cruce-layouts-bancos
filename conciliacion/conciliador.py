from __future__ import annotations

import time
from collections import Counter, defaultdict
from decimal import Decimal

from core.models import CedulaRegistro, CFDI, MovimientoBancario, ResultadoConciliacion


class Conciliador:
    ESTATUS = {
        "CONCILIADO": "CONCILIADO",
        "DIFERENCIA": "DIFERENCIA DE IMPORTE",
        "SIN_XML": "SIN XML",
        "SIN_BANCO": "SIN BANCO",
        "DUPLICADO": "POSIBLE DUPLICADO",
        "MONEDA_DIF": "MONEDA DIFERENTE",
        "FECHA_FUERA": "FECHA FUERA DE RANGO",
        "REF_FALTANTE": "REFERENCIA BANCARIA FALTANTE",
        "REVISAR": "REVISAR MANUALMENTE",
    }

    def __init__(self, tolerancia: Decimal = Decimal("1.00"), dias_tolerancia: int = 5) -> None:
        self.tolerancia = tolerancia
        self.dias_tolerancia = dias_tolerancia
        self.errores: list[str] = []
        self.uuid_counter: Counter[str] = Counter()

    def conciliar(
        self,
        cedula: list[CedulaRegistro],
        cfdis: list[CFDI],
        movimientos: list[MovimientoBancario],
    ) -> ResultadoConciliacion:
        inicio = time.perf_counter()
        self.uuid_counter = Counter(reg.uuid for reg in cedula if reg.uuid)
        indices_cfdi = self._indexar_cfdis(cfdis)
        indices_bancarios = self._indexar_movimientos(movimientos)

        resultados: list[CedulaRegistro] = []
        for registro in cedula:
            try:
                resultados.append(self._conciliar_registro(registro, indices_cfdi, indices_bancarios))
            except Exception as exc:
                self.errores.append(f"Error en poliza {registro.poliza}: {exc}")
                registro.estatus = self.ESTATUS["REVISAR"]
                registro.observaciones = str(exc)
                resultados.append(registro)

        return self._generar_resultados(resultados, time.perf_counter() - inicio)

    def _conciliar_registro(
        self,
        registro: CedulaRegistro,
        indices_cfdi: dict[str, CFDI],
        indices_bancarios: dict[str, list[MovimientoBancario]],
    ) -> CedulaRegistro:
        cfdi = indices_cfdi.get(registro.uuid)
        if not cfdi:
            registro.estatus = self.ESTATUS["SIN_XML"]
            registro.observaciones = "No se encontro XML por UUID"
            return registro

        registro.cfdi = cfdi
        observaciones: list[str] = []

        if abs(cfdi.total - registro.importe) > self.tolerancia:
            observaciones.append(f"Diferencia XML vs cedula: {cfdi.total - registro.importe}")
            registro.estatus = self.ESTATUS["DIFERENCIA"]

        movimiento = self._buscar_movimiento(registro, indices_bancarios)
        if movimiento:
            registro.movimiento = movimiento
            if abs(registro.importe - movimiento.monto) > self.tolerancia:
                observaciones.append(f"Diferencia banco vs cedula: {movimiento.monto - registro.importe}")
                registro.estatus = self.ESTATUS["DIFERENCIA"]
            if abs((registro.fecha_pago - movimiento.fecha).days) > self.dias_tolerancia:
                observaciones.append("Fecha bancaria fuera de rango")
                registro.estatus = self.ESTATUS["FECHA_FUERA"]
        else:
            observaciones.append("No se encontro movimiento bancario por referencia o importe")
            if not registro.estatus:
                registro.estatus = self.ESTATUS["SIN_BANCO"]

        if registro.moneda and cfdi.moneda and registro.moneda.upper() != cfdi.moneda.upper():
            observaciones.append("Moneda distinta entre cedula y XML")
            registro.estatus = self.ESTATUS["MONEDA_DIF"]

        if self.uuid_counter.get(registro.uuid, 0) > 1 and registro.estatus == self.ESTATUS["CONCILIADO"]:
            observaciones.append("UUID repetido en cedula")
            registro.estatus = self.ESTATUS["DUPLICADO"]

        if not registro.estatus:
            registro.estatus = self.ESTATUS["CONCILIADO"]
        registro.observaciones = "; ".join(observaciones) or "OK"
        return registro

    def _buscar_movimiento(
        self,
        registro: CedulaRegistro,
        indices_bancarios: dict[str, list[MovimientoBancario]],
    ) -> MovimientoBancario | None:
        if registro.cruce_bancario:
            movimientos = indices_bancarios.get(registro.cruce_bancario, [])
            if len(movimientos) == 1:
                return movimientos[0]
            if len(movimientos) > 1:
                exactos = [mov for mov in movimientos if abs(mov.monto - registro.importe) <= self.tolerancia]
                return exactos[0] if len(exactos) == 1 else None
        return self._busqueda_flexible(registro, indices_bancarios)

    def _busqueda_flexible(
        self,
        registro: CedulaRegistro,
        indices_bancarios: dict[str, list[MovimientoBancario]],
    ) -> MovimientoBancario | None:
        candidatos = [
            mov
            for movimientos in indices_bancarios.values()
            for mov in movimientos
            if abs(mov.monto - registro.importe) <= self.tolerancia
            and abs((registro.fecha_pago - mov.fecha).days) <= self.dias_tolerancia
        ]
        return candidatos[0] if len(candidatos) == 1 else None

    def _indexar_cfdis(self, cfdis: list[CFDI]) -> dict[str, CFDI]:
        return {cfdi.uuid.upper(): cfdi for cfdi in cfdis if cfdi.uuid}

    def _indexar_movimientos(self, movimientos: list[MovimientoBancario]) -> dict[str, list[MovimientoBancario]]:
        indices: dict[str, list[MovimientoBancario]] = defaultdict(list)
        for movimiento in movimientos:
            if movimiento.cruce_bancario:
                indices[movimiento.cruce_bancario].append(movimiento)
        return dict(indices)

    def _generar_resultados(self, registros: list[CedulaRegistro], tiempo: float) -> ResultadoConciliacion:
        total_importe = sum((registro.importe for registro in registros), Decimal("0"))
        conciliados = [registro for registro in registros if registro.estatus == self.ESTATUS["CONCILIADO"]]
        total_conciliado = sum((registro.importe for registro in conciliados), Decimal("0"))
        total_diferencia = total_importe - total_conciliado
        return ResultadoConciliacion(
            total_registros=len(registros),
            conciliados=len(conciliados),
            diferencias=sum(1 for registro in registros if "DIFERENCIA" in (registro.estatus or "")),
            sin_xml=sum(1 for registro in registros if registro.estatus == self.ESTATUS["SIN_XML"]),
            sin_banco=sum(1 for registro in registros if registro.estatus == self.ESTATUS["SIN_BANCO"]),
            errores=self.errores,
            registros=registros,
            total_importe=total_importe,
            total_conciliado=total_conciliado,
            total_diferencia=total_diferencia,
            tiempo_procesamiento=tiempo,
        )
