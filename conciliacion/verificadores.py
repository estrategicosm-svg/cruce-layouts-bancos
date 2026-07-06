from __future__ import annotations

from core.models import CedulaRegistro


def tiene_referencia_bancaria(registro: CedulaRegistro) -> bool:
    return bool(registro.cruce_bancario)
