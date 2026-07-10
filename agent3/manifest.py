"""Verificacion SHA-256 de archivos de entrada."""

from __future__ import annotations

import hashlib
from pathlib import Path


def calcular_sha256(filepath: Path) -> str:
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest().upper()


def verificar_manifest(manifest_path: Path, directorio: Path) -> dict[str, bool]:
    resultados = {}
    if not manifest_path.exists():
        return resultados

    for line in manifest_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("  ", 1)
        if len(parts) != 2:
            continue
        hash_esperado, nombre = parts
        archivo = directorio / nombre
        if not archivo.exists():
            resultados[nombre] = False
            continue
        hash_actual = calcular_sha256(archivo)
        resultados[nombre] = hash_actual == hash_esperado.upper()

    return resultados
