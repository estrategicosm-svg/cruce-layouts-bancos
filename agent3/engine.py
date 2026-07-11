"""Motor de conciliacion banco-first.

Parte de los movimientos bancarios y busca candidatos en cedula + XML.
Produce la tabla intermedia auditable.

Regla critica: solo monto nunca concilia definitivamente.
Referencia fuerte + monto exacto -> ALTA / CONCILIADO.
Solo monto -> BAJA / PROPUESTA_REVISAR.

Cada fila del layout = 1 fila en la tabla intermedia.
GRUPO_ID vincula registros de la misma POLIZA.

Cada movimiento bancario se identifica univocamente con MOVIMIENTO_ID (tecnico)
y con CRUCE_ID (operativo visible: EMPRESA-TIPO-BANCO-CONSECUTIVO).
"""
from __future__ import annotations

import re

import hashlib
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Optional

from agent3.matcher import (
    Naturaleza,
    _monto_para_comparar,
    _es_elegible,
    score_candidate,
)
from agent3.models import (
    EstatusRegistro,
    TablaIntermediateRow,
    TipoMatch,
)
from core.utils import normalizar_uuid

logger = logging.getLogger(__name__)


EMPRESA_CODES = {
    "CSC": "CSC",
    "INTRA": "INTRA",
    "ICOLD": "ICOLD",
    "TRANSCRUCES": "TRANS",
}

BANCO_CODES = {
    "BANAMEX": "BNMX",
    "BBVA": "BBVA",
    "BAJIO": "BAJIO",
    "BANCO DEL BAJÍO": "BAJIO",
    "BANREGIO": "BREG",
    "IBC": "IBC",
    "MONEX": "MONEX",
    "AMEX": "AMEX",
    "AMERICAN EXPRESS": "AMEX",
}


def _extraer_empresa(archivo_banco: str) -> str:
    """Extract empresa code from file path like 'CSC/CSC_BAJIO_...'"""
    parts = archivo_banco.replace("\\", "/").split("/")
    if parts:
        first = parts[0].upper()
        return EMPRESA_CODES.get(first, first)
    return "DESC"


def _mapear_banco_code(banco: str) -> str:
    """Map banco name to short code for CRUCE_ID."""
    return BANCO_CODES.get(banco.upper().strip(), banco.upper()[:4])


def _naturaleza_tipo_cruce(naturaleza: str) -> str:
    """Map naturaleza to CRUCE_ID tipo code: EGR or ING."""
    if naturaleza == "ABONO":
        return "ING"
    return "EGR"


@dataclass
class EngineConfig:
    tolerancia_monto: Decimal = Decimal("1.00")
    tolerancia_dias: int = 5


@dataclass
class _BusquedaResultado:
    movimientos: list = field(default_factory=list)
    metodo: str = ""


@dataclass
class BankMovementRecord:
    """Registro completo de un movimiento bancario normalizado."""
    MOVIMIENTO_ID: str
    ARCHIVO_BANCO: str
    FILA_BANCO: int
    EMPRESA: str
    BANCO: str
    CUENTA: str
    MONEDA: str
    FECHA: str
    CONCEPTO: str
    CARGO: Decimal
    ABONO: Decimal
    REFERENCIA: str
    REFERENCIA_CLASIFICACION: str
    FECHA_VALIDA: bool
    NATURALEZA: str
    CRUCE_ID: str = ""


@dataclass
class EngineResult:
    filas: list[TablaIntermediateRow] = field(default_factory=list)
    movimientos_universo: list[BankMovementRecord] = field(default_factory=list)

    @property
    def total_grupos(self) -> int:
        return len({f.GRUPO_ID for f in self.filas})

    def _grupos_con_estatus(self, estatus: EstatusRegistro) -> set:
        return {f.GRUPO_ID for f in self.filas if f.ESTATUS == estatus}

    @property
    def grupos_conciliados(self) -> int:
        return len(self._grupos_con_estatus(EstatusRegistro.CONCILIADO))

    @property
    def grupos_propuesta_revisar(self) -> int:
        return len(self._grupos_con_estatus(EstatusRegistro.PROPUESTA_REVISAR))

    @property
    def grupos_ambiguos(self) -> int:
        return len(self._grupos_con_estatus(EstatusRegistro.AMBIGUO))

    @property
    def grupos_sin_candidato(self) -> int:
        return len(self._grupos_con_estatus(EstatusRegistro.SIN_CANDIDATO))

    @property
    def conciliados(self) -> int:
        return sum(1 for f in self.filas
                   if f.ESTATUS == EstatusRegistro.CONCILIADO)

    @property
    def conciliados_exactos(self) -> int:
        return sum(1 for f in self.filas
                   if f.ESTATUS == EstatusRegistro.CONCILIADO
                   and f.DIFERENCIA == Decimal("0"))

    @property
    def conciliados_tolerancia(self) -> int:
        return sum(1 for f in self.filas
                   if f.ESTATUS == EstatusRegistro.CONCILIADO
                   and f.DIFERENCIA > Decimal("0"))

    @property
    def propuesta_revisar(self) -> int:
        return sum(1 for f in self.filas
                   if f.ESTATUS == EstatusRegistro.PROPUESTA_REVISAR)

    @property
    def ambiguos(self) -> int:
        return sum(1 for f in self.filas
                   if f.ESTATUS == EstatusRegistro.AMBIGUO)

    @property
    def sin_candidato(self) -> int:
        return sum(1 for f in self.filas
                   if f.ESTATUS == EstatusRegistro.SIN_CANDIDATO)

    @property
    def movimientos_asignados(self) -> int:
        return len({f.MOVIMIENTO_ID for f in self.filas if f.MOVIMIENTO_ID})

    @property
    def movimientos_bancarios_totales(self) -> int:
        return len(self.movimientos_universo)


def _es_cargo(mov) -> bool:
    return Decimal(str(mov.cargo)) > Decimal("0") and Decimal(str(mov.abono)) == Decimal("0")


def _es_abono(mov) -> bool:
    return Decimal(str(mov.abono)) > Decimal("0") and Decimal(str(mov.cargo)) == Decimal("0")


def _fecha_valida(fecha) -> bool:
    if fecha is None:
        return False
    try:
        return 2000 <= fecha.year <= 2100
    except AttributeError:
        return False


def _formato_fecha(fecha) -> str:
    if fecha is None:
        return ""
    try:
        return fecha.strftime("%Y-%m-%d")
    except Exception:
        return ""


def _movimiento_id(mov, archivo_banco: str) -> str:
    banco = getattr(mov, "banco", "") or ""
    cuenta = getattr(mov, "cuenta", "") or ""
    moneda = getattr(mov, "moneda", "") or ""
    fecha = _formato_fecha(getattr(mov, "fecha", None))
    cargo = str(getattr(mov, "cargo", "0"))
    abono = str(getattr(mov, "abono", "0"))
    ref = getattr(mov, "referencia", "") or ""
    fila = str(getattr(mov, "_fila_origen", 0))
    return f"{archivo_banco}|{fila}|{banco}|{cuenta}|{moneda}|{fecha}|{cargo}|{abono}|{ref}"


def _movimiento_id_hash(mov, archivo_banco: str) -> str:
    raw = _movimiento_id(mov, archivo_banco)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16].upper()


_REF_TRUNCADAS_INVALIDAS = {
    "ERENCIA", "ORIZADA", "REFERENCIA", "AUTORIZADA", "AUTORIZACION",
    "REFERNCIA", "REFENCIA", "OPERACION", "OPERACIÓN"
}
_REF_TRUNCADAS_REGEX = re.compile(
    r"^(?:ERENCIA|ORIZADA|REFERNCIA|REFENCIA|REFERENCIA|AUTORIZADA|AUTORIZACION)$",
    re.IGNORECASE
)


def _clasificar_referencia(ref: str, concepto: str) -> str:
    if not ref:
        return "SIN_REFERENCIA_VISIBLE"
    ref_upper = ref.strip().upper()
    if ref_upper in _REF_TRUNCADAS_INVALIDAS or _REF_TRUNCADAS_REGEX.match(ref_upper):
        return "SIN_REFERENCIA_VISIBLE"
    if ref_upper.startswith("CLABE") or len(ref_upper) == 18 and ref_upper.isdigit():
        return "CLAVE_RASTREO_EXPLICITA"
    if ref_upper.startswith("T+") or "WIRE" in ref_upper:
        return "WIRE_EXPLICITO"
    if "AUTH" in ref_upper or "AUTORIZACION" in ref_upper:
        return "AUTORIZACION_EXPLICITA"
    if "NRO" in ref_upper or "NUM" in ref_upper or "OPER" in ref_upper:
        return "NUMERO_OPERACION_EXPLICITO"
    return "REFERENCIA_EXPLICITA"


def _buscar_uuid(uuid: str, index_xml: dict) -> Optional[object]:
    return index_xml.get(normalizar_uuid(uuid))


def _buscar_referencia(ref: str, index_banco: dict) -> list:
    if not ref:
        return []
    return index_banco.get(ref.strip().upper(), [])


def _buscar_monto(
    monto, movimientos, tolerancia, naturaleza,
    fecha_ref=None, tolerancia_dias=5,
) -> list:
    candidatos = []
    for m in movimientos:
        if not _es_elegible(m, naturaleza):
            continue
        monto_mov = _monto_para_comparar(m, naturaleza)
        if abs(monto_mov - monto) <= tolerancia:
            if fecha_ref and _fecha_valida(getattr(m, "fecha", None)):
                try:
                    if abs((fecha_ref - m.fecha).days) <= tolerancia_dias:
                        candidatos.append(m)
                except Exception:
                    candidatos.append(m)
            else:
                candidatos.append(m)
    return candidatos


def _agrupar_cedulas_egresos(cedulas: list) -> dict:
    por_poliza = {}
    for c in cedulas:
        poliza = getattr(c, "poliza", None) or "_sin_poliza"
        por_poliza.setdefault(poliza, []).append(c)
    return {f"egreso_{p}": regs for p, regs in por_poliza.items()}


def _agrupar_cedulas_ingresos(cedulas: list) -> dict:
    por_folio = {}
    for c in cedulas:
        folio = getattr(c, "folio_transferencia", None) or f"_auto_{id(c)}"
        por_folio.setdefault(folio, []).append(c)
    return {f"ingreso_{f}": regs for f, regs in por_folio.items()}


def _buscar_movimiento_para_grupo(
    registros, index_xml, index_ref_banco,
    movimientos, config, total_grupo, naturaleza,
) -> _BusquedaResultado:
    for r in registros:
        ref_banco = getattr(r, "cruce_bancario", "") or ""
        if not ref_banco and naturaleza == Naturaleza.INGRESOS:
            ref_banco = getattr(r, "folio_transferencia", "") or ""
        if ref_banco:
            candidatos = _buscar_referencia(ref_banco, index_ref_banco)
            elegibles = [c for c in candidatos if _es_elegible(c, naturaleza)]
            if len(elegibles) == 1:
                return _BusquedaResultado(movimientos=elegibles, metodo="REFERENCIA")
            elif len(elegibles) > 1:
                exactos = [c for c in elegibles
                           if abs(_monto_para_comparar(c, naturaleza) - total_grupo) <= config.tolerancia_monto]
                if len(exactos) == 1:
                    return _BusquedaResultado(movimientos=exactos, metodo="REFERENCIA")

    for r in registros:
        uuid = getattr(r, "uuid", None) or ""
        if uuid:
            cfdi = _buscar_uuid(uuid, index_xml)
            if cfdi:
                ref = getattr(cfdi, "referencia_pago", "") or ""
                candidatos = _buscar_referencia(ref, index_ref_banco)
                elegibles = [c for c in candidatos if _es_elegible(c, naturaleza)]
                if len(elegibles) == 1:
                    return _BusquedaResultado(movimientos=elegibles, metodo="REFERENCIA")

    candidatos_monto = _buscar_monto(
        total_grupo, movimientos, config.tolerancia_monto, naturaleza,
    )
    if len(candidatos_monto) == 1:
        return _BusquedaResultado(movimientos=candidatos_monto, metodo="MONTO")
    elif len(candidatos_monto) > 1:
        return _BusquedaResultado(movimientos=[], metodo="AMBIGUO_MONTOS")

    return _BusquedaResultado()


def _crear_fila(**kw) -> TablaIntermediateRow:
    return TablaIntermediateRow(**kw)


def _crear_filas_para_grupo(
    grupo_id, registros, resultado_busqueda, total_grupo,
    config, archivo_banco, naturaleza, movimientos_asignados: set,
    cruce_id_map: dict[str, str],
) -> list[TablaIntermediateRow]:
    filas = []
    poliza = getattr(registros[0], "poliza", "") or ""
    empresa = "SAT"
    moneda = getattr(registros[0], "moneda", "MXN") or "MXN"

    fecha_attr = "fecha_pago" if naturaleza == Naturaleza.EGRESOS else "fecha"
    importe_attr = "importe" if naturaleza == Naturaleza.EGRESOS else "total"

    es_referencia = resultado_busqueda.metodo == "REFERENCIA"
    mov = resultado_busqueda.movimientos[0] if resultado_busqueda.movimientos else None

    candidato_hash = ""
    if mov:
        candidato_hash = _movimiento_id_hash(mov, archivo_banco)

    cand_cruce = cruce_id_map.get(candidato_hash, "") if candidato_hash else ""

    if resultado_busqueda.metodo == "AMBIGUO_MONTOS":
        for r in registros:
            fecha_ref = getattr(r, fecha_attr, None)
            filas.append(_crear_fila(
                GRUPO_ID=grupo_id, POLIZA=poliza, EMPRESA=empresa,
                BANCO=archivo_banco, MONEDA=moneda,
                FECHA_LAYOUT=_formato_fecha(fecha_ref) if _fecha_valida(fecha_ref) else "",
                TOTAL_GRUPO=total_grupo,
                CRUCE_ID="", CANDIDATO_CRUCE_ID="",
                MOVIMIENTO_ID="", CANDIDATO_MOVIMIENTO_ID="",
                ARCHIVO_BANCO=archivo_banco,
                FILA_BANCO=0, FECHA_BANCO="",
                CARGO=Decimal("0"), ABONO=Decimal("0"),
                DIFERENCIA=Decimal(str(getattr(r, importe_attr))),
                TIPO_MATCH=TipoMatch.NINGUNO,
                NIVEL_CONFIANZA="NINGUNO",
                ESTATUS=EstatusRegistro.AMBIGUO,
            ))
        return filas

    if mov is None:
        for r in registros:
            fecha_ref = getattr(r, fecha_attr, None)
            filas.append(_crear_fila(
                GRUPO_ID=grupo_id, POLIZA=poliza, EMPRESA=empresa,
                BANCO=archivo_banco, MONEDA=moneda,
                FECHA_LAYOUT=_formato_fecha(fecha_ref) if _fecha_valida(fecha_ref) else "",
                TOTAL_GRUPO=total_grupo,
                CRUCE_ID="", CANDIDATO_CRUCE_ID="",
                MOVIMIENTO_ID="", CANDIDATO_MOVIMIENTO_ID="",
                ARCHIVO_BANCO=archivo_banco,
                FILA_BANCO=0, FECHA_BANCO="",
                CARGO=Decimal("0"), ABONO=Decimal("0"),
                DIFERENCIA=Decimal(str(getattr(r, importe_attr))),
                TIPO_MATCH=TipoMatch.NINGUNO,
                NIVEL_CONFIANZA="NINGUNO",
                ESTATUS=EstatusRegistro.SIN_CANDIDATO,
            ))
        return filas

    mov_raw = _movimiento_id(mov, archivo_banco)
    mov_reutilizado = mov_raw in movimientos_asignados
    if not mov_reutilizado:
        movimientos_asignados.add(mov_raw)

    cargo_mov = Decimal(str(mov.cargo))
    abono_mov = Decimal(str(mov.abono))
    monto_mov = _monto_para_comparar(mov, naturaleza)
    diff_grupo = abs(total_grupo - monto_mov)

    if mov_reutilizado:
        for r in registros:
            fecha_ref = getattr(r, fecha_attr, None)
            filas.append(_crear_fila(
                GRUPO_ID=grupo_id, POLIZA=poliza, EMPRESA=empresa,
                BANCO=archivo_banco, MONEDA=moneda,
                FECHA_LAYOUT=_formato_fecha(fecha_ref) if _fecha_valida(fecha_ref) else "",
                TOTAL_GRUPO=total_grupo,
                CRUCE_ID="", CANDIDATO_CRUCE_ID="",
                MOVIMIENTO_ID="", CANDIDATO_MOVIMIENTO_ID="",
                ARCHIVO_BANCO=archivo_banco,
                FILA_BANCO=0, FECHA_BANCO="",
                CARGO=Decimal("0"), ABONO=Decimal("0"),
                DIFERENCIA=Decimal(str(getattr(r, importe_attr))),
                TIPO_MATCH=TipoMatch.NINGUNO,
                NIVEL_CONFIANZA="NINGUNO",
                ESTATUS=EstatusRegistro.AMBIGUO,
            ))
        return filas

    if not _fecha_valida(getattr(mov, "fecha", None)):
        for r in registros:
            fecha_ref = getattr(r, fecha_attr, None)
            filas.append(_crear_fila(
                GRUPO_ID=grupo_id, POLIZA=poliza, EMPRESA=empresa,
                BANCO=archivo_banco, MONEDA=moneda,
                FECHA_LAYOUT=_formato_fecha(fecha_ref) if _fecha_valida(fecha_ref) else "",
                TOTAL_GRUPO=total_grupo,
                CRUCE_ID="", CANDIDATO_CRUCE_ID=cand_cruce,
                MOVIMIENTO_ID="", CANDIDATO_MOVIMIENTO_ID="",
                ARCHIVO_BANCO=archivo_banco,
                FILA_BANCO=getattr(mov, "_fila_origen", 0),
                FECHA_BANCO="",
                CARGO=cargo_mov, ABONO=abono_mov,
                DIFERENCIA=diff_grupo,
                TIPO_MATCH=TipoMatch.NINGUNO,
                NIVEL_CONFIANZA="NINGUNO",
                ESTATUS=EstatusRegistro.SIN_CANDIDATO,
            ))
        return filas

    conf, tipo = score_candidate(
        grupo_total=total_grupo,
        tolerancia=config.tolerancia_monto,
        tiene_referencia=es_referencia,
        monto_comparar=monto_mov,
    )

    if tipo == TipoMatch.NINGUNO:
        estatus = EstatusRegistro.SIN_CANDIDATO
    elif tipo == TipoMatch.MONTO:
        estatus = EstatusRegistro.PROPUESTA_REVISAR
    elif diff_grupo <= config.tolerancia_monto:
        estatus = EstatusRegistro.CONCILIADO
    else:
        estatus = EstatusRegistro.DIFERENCIA

    mov_id_asignado = ""
    cand_id = candidato_hash
    cruce_asignado = ""
    if estatus in (EstatusRegistro.CONCILIADO, EstatusRegistro.DIFERENCIA):
        mov_id_asignado = candidato_hash
        cruce_asignado = cand_cruce

    for r in registros:
        fecha_ref = getattr(r, fecha_attr, None)
        filas.append(_crear_fila(
            GRUPO_ID=grupo_id, POLIZA=poliza, EMPRESA=empresa,
            BANCO=archivo_banco, MONEDA=moneda,
            FECHA_LAYOUT=_formato_fecha(fecha_ref) if _fecha_valida(fecha_ref) else "",
            TOTAL_GRUPO=total_grupo,
            CRUCE_ID=cruce_asignado, CANDIDATO_CRUCE_ID=cand_cruce,
            MOVIMIENTO_ID=mov_id_asignado,
            CANDIDATO_MOVIMIENTO_ID=cand_id,
            ARCHIVO_BANCO=archivo_banco,
            FILA_BANCO=getattr(mov, "_fila_origen", 0),
            FECHA_BANCO=_formato_fecha(getattr(mov, "fecha", None)),
            CARGO=cargo_mov, ABONO=abono_mov,
            DIFERENCIA=diff_grupo,
            TIPO_MATCH=tipo,
            NIVEL_CONFIANZA=conf,
            ESTATUS=estatus,
        ))

    return filas


def _construir_universo_movimientos(
    movimientos: list,
    archivo_banco: str,
) -> list[BankMovementRecord]:
    records = []
    for m in movimientos:
        ref = getattr(m, "referencia", "") or ""
        concepto = getattr(m, "concepto", "") or ""
        fecha = getattr(m, "fecha", None)
        archivo_origen = getattr(m, "_archivo_origen", archivo_banco)
        empresa = _extraer_empresa(archivo_origen)
        records.append(BankMovementRecord(
            MOVIMIENTO_ID=_movimiento_id_hash(m, archivo_banco),
            ARCHIVO_BANCO=archivo_origen,
            FILA_BANCO=getattr(m, "_fila_origen", 0),
            EMPRESA=empresa,
            BANCO=getattr(m, "banco", "") or "",
            CUENTA=getattr(m, "cuenta", "") or "",
            MONEDA=getattr(m, "moneda", "") or "",
            FECHA=_formato_fecha(fecha),
            CONCEPTO=concepto,
            CARGO=Decimal(str(m.cargo)),
            ABONO=Decimal(str(m.abono)),
            REFERENCIA=ref,
            REFERENCIA_CLASIFICACION=_clasificar_referencia(ref, concepto),
            FECHA_VALIDA=_fecha_valida(fecha),
            NATURALEZA="CARGO" if _es_cargo(m) else ("ABONO" if _es_abono(m) else "MIXTO"),
        ))
    return records


def asignar_cruce_ids(records: list[BankMovementRecord]) -> dict[str, str]:
    """Assign deterministic CRUCE_ID to each BankMovementRecord.

    Sorting: EMPRESA -> TIPO -> BANCO -> FECHA -> ARCHIVO_ORIGEN -> FILA_ORIGEN -> MOVIMIENTO_ID
    Consecutivo restarts at 001 for each unique EMPRESA+TIPO+BANCO.

    Returns a dict mapping MOVIMIENTO_ID -> CRUCE_ID.
    """
    def sort_key(r: BankMovementRecord):
        tipo = _naturaleza_tipo_cruce(r.NATURALEZA)
        banco_code = _mapear_banco_code(r.BANCO)
        return (r.EMPRESA, tipo, banco_code, r.FECHA, r.ARCHIVO_BANCO, r.FILA_BANCO, r.MOVIMIENTO_ID)

    sorted_records = sorted(records, key=sort_key)

    counters: dict[tuple, int] = defaultdict(int)
    mapping: dict[str, str] = {}

    for r in sorted_records:
        tipo = _naturaleza_tipo_cruce(r.NATURALEZA)
        banco_code = _mapear_banco_code(r.BANCO)
        key = (r.EMPRESA, tipo, banco_code)
        counters[key] += 1
        consecutivo = f"{counters[key]:03d}"
        cruce_id = f"{r.EMPRESA}-{tipo}-{banco_code}-{consecutivo}"
        r.CRUCE_ID = cruce_id
        mapping[r.MOVIMIENTO_ID] = cruce_id

    return mapping


def conciliar_banco_first(
    movimientos_bancarios: list,
    cedulas_egresos: list,
    cedulas_ingresos: list,
    cfdis: list,
    config: Optional[EngineConfig] = None,
    archivo_banco: str = "banco.xlsx",
) -> EngineResult:
    if config is None:
        config = EngineConfig()

    result = EngineResult()

    result.movimientos_universo = _construir_universo_movimientos(
        movimientos_bancarios, archivo_banco,
    )

    cruce_id_map = asignar_cruce_ids(result.movimientos_universo)

    index_xml = {}
    for cfdi in cfdis:
        index_xml[normalizar_uuid(cfdi.uuid)] = cfdi

    index_ref_banco = {}
    for m in movimientos_bancarios:
        ref = getattr(m, "referencia", None) or ""
        if ref:
            index_ref_banco.setdefault(ref.strip().upper(), []).append(m)

    movimientos_egresos = [m for m in movimientos_bancarios if _es_cargo(m)]
    movimientos_ingresos = [m for m in movimientos_bancarios if _es_abono(m)]

    mov_asig_eg: set = set()
    mov_asig_ing: set = set()

    grupos_egresos = _agrupar_cedulas_egresos(cedulas_egresos)
    for grupo_id, registros in grupos_egresos.items():
        total_grupo = sum(Decimal(str(r.importe)) for r in registros)
        busqueda = _buscar_movimiento_para_grupo(
            registros, index_xml, index_ref_banco,
            movimientos_egresos, config, total_grupo, Naturaleza.EGRESOS,
        )
        filas = _crear_filas_para_grupo(
            grupo_id, registros, busqueda, total_grupo,
            config, archivo_banco, Naturaleza.EGRESOS, mov_asig_eg,
            cruce_id_map,
        )
        result.filas.extend(filas)

    grupos_ingresos = _agrupar_cedulas_ingresos(cedulas_ingresos)
    for grupo_id, registros in grupos_ingresos.items():
        total_grupo = sum(Decimal(str(r.total)) for r in registros)
        busqueda = _buscar_movimiento_para_grupo(
            registros, index_xml, index_ref_banco,
            movimientos_ingresos, config, total_grupo, Naturaleza.INGRESOS,
        )
        filas = _crear_filas_para_grupo(
            grupo_id, registros, busqueda, total_grupo,
            config, archivo_banco, Naturaleza.INGRESOS, mov_asig_ing,
            cruce_id_map,
        )
        result.filas.extend(filas)

    return result
