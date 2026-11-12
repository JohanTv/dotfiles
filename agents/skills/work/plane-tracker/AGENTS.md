# Orientation for AI Agents: `plane-tracker` CLI Development

Instrucciones para agentes trabajando en el código, pruebas, arquitectura o documentación de `plane-tracker`.

---

## 1. Contexto y Frontera Mental (Zero-Confusion)

- **Propósito Dual:**
  - **Como Herramienta Operativa:** Es un CLI para interactuar con la instancia corporativa de Plane CE v1.2.3 (descrito en [`SKILL.md`](./SKILL.md) y [`references/`](./references/)).
  - **Como Codebase en Desarrollo:** Es un proyecto local en Python puro (3.10+ stdlib) con su propio ciclo de vida, backlog y decisiones técnicas.
- **Regla de Oro:** **NO confundir Plane CE con el backlog de este CLI.**
  - **Backlog Interno:** Defectos conocidos, mejoras diferidas y tareas del CLI viven en [`docs/BACKLOG.md`](./docs/BACKLOG.md).
  - **Diseño & ADRs:** Decisiones arquitectónicas y propuestas viven en [`docs/INDEX.md`](./docs/INDEX.md), [`docs/decisions/`](./docs/decisions/) y [`docs/rfcs/`](./docs/rfcs/).
  - **Nunca** ejecutes búsquedas automáticas (`plane-tracker list`) ni crees tickets en Plane CE para registrar bugs o mejoras del CLI, a menos que el usuario lo instruya explícitamente.

---

## 2. Arquitectura y Restricciones de Código

Consulta [`ARCHITECTURE.md`](./ARCHITECTURE.md) antes de añadir o refactorizar módulos.

- **Stack:** Solo biblioteca estándar de Python (3.10+). Sin dependencias externas (`pip`).
- **Entrypoint:** `scripts/plane.py` ajusta `sys.path` y llama a `plane_cli.cli.main()`.
- **Estructura Modular:** El código reside en `scripts/plane_cli/`, con módulos satélite como `session_clock.py` y `flow_metrics.py` en `scripts/`.
- **Tope Duro de Líneas:** **450 líneas máximo por archivo** (verificado estrictamente por `tests/test_structure.py`). Si un módulo supera el límite, sepáralo funcionalmente.
- **Contrato JSON:** El CLI utiliza el contrato envelope `plane-tracker/1` (`plane_cli/envelope.py` y `plane_cli/vocabulary.py`).
- **Persistencia & Red:** SQLite con WAL en `~/.cache/plane/worklogs.db`. Lecturas resilientes offline y outbox transaccional para escrituras si Plane está caído.

---

## 3. Suite de Pruebas y Validación

La suite de pruebas corre con el ejecutor paralelo nativo:

```bash
# Ejecutar toda la suite en paralelo
python3 tests/run_parallel.py

# Ejecutar un módulo de test específico o filtro
python3 tests/run_parallel.py test_docs
python3 tests/run_parallel.py test_structure

# Congelar reloj en fecha/hora fija si se evalúan ventanas temporales
python3 tests/run_parallel.py --freeze "2026-11-12T12:00:00-05:00" test_clock
```

- **Verificación Estructural Obligatoria:** Si modificas código, corre `test_structure` para asegurar que ningún archivo exceda 450 líneas.
- **Verificación Documental:** Si agregas o editas documentación en `docs/`:
  1. Mantén front-matter válido en RFCs/ADRs (`id`, `title`, `status`, `created`, `summary`).
  2. Regenera el índice: `python3 scripts/docs_index.py`.
  3. Ejecuta `python3 tests/run_parallel.py test_docs` para validar links y consistencia del índice.

---

## 4. Flujo para Resolver Tareas o Bugs del CLI

1. **Revisar Backlog:** Consulta [`docs/BACKLOG.md`](./docs/BACKLOG.md) para entender el defecto o requerimiento técnico.
2. **Consultar Principios:** Revisa [`docs/principles.md`](./docs/principles.md) y [`references/CLI_DESIGN_GUARD.md`](./references/CLI_DESIGN_GUARD.md).
3. **Implementar con TDD:** Crea o ajusta el caso de prueba en `tests/test_<feature>.py` y modifica el módulo en `scripts/plane_cli/`.
4. **Validar:** Corre las pruebas asociadas y `test_structure`.
5. **Documentar:** Actualiza `docs/BACKLOG.md` (mover a *Recently Implemented* si aplica) o `docs/CHANGELOG.md`.
