# Dependency Matrix - Fase 16 Audit

Este documento mapea la jerarquía de dependencias direccionales (DAG) entre los diferentes módulos del núcleo Enterprise para garantizar que no existan ciclos de dependencia y que las capas inferiores no consuman a las superiores.

## Gráfico de Capas (Directional Acyclic Graph)

### Nivel 0 (Base Incondicional)
*No dependen de ningún otro dominio, proveen las interfaces y modelos fundacionales.*
- `domains/shared`: Contiene `CanonicalXML`, `CanonicalTransaction`, `UnitOfWork` (Interface), `BaseRepository`. 

### Nivel 1 (Dominios de Infraestructura Lógica)
*Dependen exclusivamente del Nivel 0.*
- `domains/configuration`: Consumido por motores que requieren parámetros.
- `domains/rules`: Consumido por motores que requieren evaluación de lógica inyectada.
- `domains/normalization`: Transforma estructuras crudas a Nivel 0.
- `domains/workflow`: Trazabilidad de estados abstractos.

### Nivel 2 (Dominios de Reglas de Negocio Aisladas)
*Dependen de Nivel 0 y Nivel 1.*
- `domains/documents`: Construye identidades y deduplicación.
- `domains/sat`: Depende de `shared` y consume `rules` para reglas fiscales estáticas (IVA, Retenciones).
- `domains/conciliation`: Depende de `shared` para cruces. No depende de contabilidad ni SAT. Mantiene aislamiento puro.

### Nivel 3 (Dominios Orquestadores de Negocio)
*Dependen de Nivel 0, 1 y 2.*
- `domains/accounting`: Consume `shared`, `configuration` (vital para cuentas) y `rules`. 

### Nivel 4 (Agregadores Finales)
*Consumen los resultados de todos los niveles inferiores para el dictamen de auditoría.*
- `domains/evidence`: Empaqueta resultados de `documents`, `sat`, `accounting` y `conciliation` en un `EvidencePackage` sellado.

## Análisis de Ciclos y Violaciones
- **Ciclos Encontrados**: 0. La arquitectura es estrictamente direccional de arriba hacia abajo.
- **Fuga de Infraestructura**: 0. `infrastructure/` depende de `domains/` para importar las abstracciones, garantizando la Inversión de Dependencias (DIP) de los principios SOLID.
