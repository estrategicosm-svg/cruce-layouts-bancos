# Architecture Decision Records (ADR) - Fase 16 Audit

Este documento registra las decisiones arquitectónicas fundamentales tomadas durante la evolución del Auditor Fiscal SAT hasta la Fase 15, y audita su nivel de cumplimiento.

## ADR-001: Monolito Modular con Dominio Orientado (DDD)
- **Estado**: Cumplido
- **Evaluación**: Se verificó que los subdominios (`accounting`, `conciliation`, `configuration`, `documents`, `evidence`, `normalization`, `rules`, `sat`, `shared`, `workflow`) existen aisldados dentro de `backend/domains/`. 
- **Hallazgo [BAJO]**: Es necesario asegurar que los nuevos programadores mantengan esta estructura.

## ADR-002: Inversión de Dependencias (Cero Infraestructura en Dominio)
- **Estado**: Cumplido
- **Evaluación**: Un escaneo estricto sobre `backend/domains/` arrojó **cero** importaciones de `sqlalchemy`, `psycopg2` o librerías de persistencia de base de datos.
- **Detalle**: Los dominios declaran interfaces (e.g. `ConfigurationRepository`), que son implementadas en `backend/infrastructure/database/orm/repositories/`.

## ADR-003: Modelos Canónicos como Contrato Único
- **Estado**: Cumplido
- **Evaluación**: Los módulos (`accounting`, `sat`, `conciliation`) operan exclusivamente con `CanonicalXML`, `CanonicalTransaction`, `CanonicalDocument`. Esto ha evitado el acoplamiento a los parsers bancarios o formatos XML específicos.

## ADR-004: Evitar IA y Heurísticas Probabilísticas
- **Estado**: Cumplido
- **Evaluación**: Los motores (Conciliación Avanzada, Motor Contable, SAT) operan con árboles de decisión determinísticos, matemáticas (Subset Sum con DP/Backtracking) y reglas configurables explícitas. El `confidence_score` se calcula de forma incondicional basada en reglas paramétricas.

## ADR-005: Identidad Documental y Hash (Auditoría Forense)
- **Estado**: Cumplido
- **Evaluación**: `DocumentIdentity` utiliza SHA256 para prevenir alteraciones y garantizar la búsqueda en milisegundos sin reprocesamiento.
