from __future__ import annotations

from pathlib import Path


MAX_UPLOAD_MB = 250


def validar_extension(nombre: str, extensiones: set[str]) -> None:
    extension = Path(nombre).suffix.lower().lstrip(".")
    if extension not in extensiones:
        raise ValueError(f"Extension no permitida: {extension}")


def validar_tamano(contenido: bytes, max_mb: int = MAX_UPLOAD_MB) -> None:
    if len(contenido) > max_mb * 1024 * 1024:
        raise ValueError(f"Archivo mayor a {max_mb} MB")
