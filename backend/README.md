# Auditor Fiscal SAT - Enterprise Backend

Este proyecto es el **Backend Oficial** del Auditor Fiscal SAT, diseñado bajo una arquitectura de **Monolito Modular** y **Domain-Driven Design (DDD)**.

## Estructura del Proyecto

El sistema divide estrictamente sus responsabilidades:

- `api/`: Capa de transporte web (FastAPI).
- `application/`: Casos de uso e interacción de dominios.
- `domains/`: Lógica de negocio (Banking, CFDI, SAT, Normalization, Conciliation).
- `infrastructure/`: Bases de datos (PostgreSQL), Colas (Redis), Storage (MinIO) y Seguridad (JWT).

## Stack Tecnológico

- **FastAPI** para API RESTful
- **SQLAlchemy 2.x** y **Alembic** para el ORM
- **PostgreSQL** para persistencia relacional
- **Celery** y **Redis** para colas de procesamiento
- **MinIO** para object storage (compatible con S3)

## Cómo iniciar (Fase 1)

1. Iniciar los contenedores base (DB, Redis, Storage):
   ```bash
   docker-compose up -d
   ```
2. Ejecutar la API:
   ```bash
   fastapi dev main.py
   ```
3. Visita la documentación interactiva en:
   [http://localhost:8000/docs](http://localhost:8000/docs)

## Estado de Validación (Fase 1)
- ✅ El ecosistema Python base fue validado correctamente (TestClient).
- ✅ FastAPI responde 200 en `/api/v1/health/live` y `/api/v1/health/ready`.
- ✅ Alembic genera migraciones correctamente.
- ✅ SQLAlchemy Base e importaciones de seguridad (JWT) funcionan.
- ✅ La estructura DDD cumple estrictamente con la Constitución Técnica V2.
- ⚠️ **Pendiente:** PostgreSQL, Redis y MinIO no fueron validados físicamente porque el entorno Windows carece de Docker Desktop.
