# Traceability Matrix - Fase 16 Audit

Matriz de trazabilidad que garantiza que cada requerimiento del núcleo de auditoría está cubierto por una implementación probada y aislada, cumpliendo la Constitución Técnica.

| Requerimiento (Fase) | Componente Responsable | Archivos Clave | Cobertura de Pruebas |
|---|---|---|---|
| 1-3. Parsers Bancarios Crudos | `parsers/legacy_pdf_engine.py` | `legacy_pdf_engine.py` | Media (Requiere mock de OCR real) |
| 4. Modelos Canónicos | `domains/shared/canonical_models.py` | `canonical_models.py` | Total (BasePydantic) |
| 5. Normalización Determinística | `domains/normalization/` | `bank_statement.py`, `cfdi.py` | Alta |
| 6. Persistencia DDD / UoW | `infrastructure/database/orm/` | `base.py`, `repositories/` | Media (Tests de integración a db de prueba pendientes en gran escala) |
| 7. Workflow State Machine | `domains/workflow/` | `states.py`, `transitions.py` | Alta |
| 8. Conciliación Determinística | `domains/conciliation/` | `engine.py`, `strategies.py` | Total (Pruebas unitarias) |
| 9. Identidad Documental y Hash | `domains/documents/` | `identity.py`, `metadata.py` | Alta |
| 10. Motor SAT (Reglas de IVA) | `domains/sat/` | `engine.py`, `iva_rule.py` | Total |
| 11. Motor de Evidencias (Expediente) | `domains/evidence/` | `builder.py`, `models.py` | Alta |
| 12. Motor de Reglas (Configurable) | `domains/rules/` | `engine.py`, `registry.py` | Alta |
| 13. Tenant & Configuration | `domains/configuration/` | `engine.py`, `models.py` | Total (Jerarquía evaluada) |
| 14. Motor Contable (Partida Doble)| `domains/accounting/` | `engine.py`, `egreso_rule.py` | Total |
| 15. Conciliación Avanzada | `domains/conciliation/` | `strategies.py`, `resolver.py` | Total (Performance Subset Sum verificado) |

## Trazabilidad de Estados (Workflow)
Todo documento que ingresa al sistema y pasa por las Fases 4-15 deja una huella en `domains/workflow/models.py (WorkflowEvent)`, garantizando la reconstrucción total de la vida del registro para auditorías externas sin tocar logs efímeros.
