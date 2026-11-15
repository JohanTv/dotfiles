# 📚 Índice Maestro de Documentación y Arquitectura (Allostasis & Dotfiles)

> Este directorio (`docs/`) centraliza la investigación, especificaciones de arquitectura, decisiones ontológicas y planes de implementación de **Allostasis (`alo`)** y el saneamiento del entorno de **Dotfiles**.
> Si abres una nueva sesión, consulta este índice para entender el estado del proyecto y la trazabilidad de decisiones.

---

## 🗺️ Mapa de Documentación

### 1. Plan Director y Hoja de Ruta
* 🧭 **[`PLAN_MAESTRO_REFACTORING_Y_OSS.md`](PLAN_MAESTRO_REFACTORING_Y_OSS.md):**  
  **El documento guía.** Describe las **5 fases del proyecto** (desde el saneamiento de reglas de dotfiles hasta el lanzamiento Open Source de Allostasis en Go), el árbol canónico de carpetas (`cmd/alo/`, `internal/...`), la delimitación de contextos (DDD) y el arnés de pruebas.

### 2. Especificación Técnica y Arquitectura de Sistemas
* 🏗️ **[`CRITICA_Y_ARQUITECTURA_GO_HEXAGONAL.md`](CRITICA_Y_ARQUITECTURA_GO_HEXAGONAL.md):**  
  **La biblia técnica de implementación en Go (73 KB, 1,476 líneas).**  
  - Dualidad innegociable: CLI Headless estructurado (`--json` para agentes de IA) vs TUI reactiva a 60 fps (para humanos con Charm: Bubble Tea, Lip Gloss, Huh).
  - Adopción de `ncruces/go-sqlite3` (Wazero JIT, zero-CGO, FTS5 unicode61, dual-pool WAL).
  - Orquestación de Git con aislamiento de grupos de procesos (`Setpgid`), timeouts defensivos y detección de capacidades (`git merge-tree`).
  - Aplicación estricta de SOLID (ISP con interfaces segregadas mínimas) y Bounded Contexts.
  - Doble despliegue del motor de workspaces: subcomando `alo ws` o binario standalone `alo-ws`.

* 🛡️ **[`ESTRATEGIA_VERIFICACION_Y_AUDITORIA_PREMORTEM.md`](ESTRATEGIA_VERIFICACION_Y_AUDITORIA_PREMORTEM.md):**  
  **Auditoría de Red Teaming y Pre-Mortem.**  
  - Análisis metodológico de por qué las pruebas de runtime (fuzzing/adversariales) no aplican a documentos.
  - Identificación y mitigación de 7 modos de fallo críticos antes de escribir código (concurrencia de múltiples procesos en SQLite, migraciones sobre DB legacy, wazero compilation cache, fallback Docker/CI).
  - Matriz de trazabilidad de los 14 RFCs y ADRs existentes hacia la nueva arquitectura.

* 🖥️ **[`INFORME_VIABILIDAD_TECNICA_GO_Y_CHARM_TUI.md`](INFORME_VIABILIDAD_TECNICA_GO_Y_CHARM_TUI.md):**  
  Estudio comparativo inicial Go vs Python, benchmarking de cold-start (<10ms), diseño de wireframes interactivos y componentes del ecosistema Charm (`charm.land`).

### 3. Identidad, Naming y Validación
* 🧬 **[`INFORME_CONSISTENCIA_ALOSTASIS.md`](INFORME_CONSISTENCIA_ALOSTASIS.md):**  
  Validación ontológica y biológica del nombre **Allostasis** frente a los principios de diseño (P1-P5): mapeo de la *carga alostática* con el soporte invisible, regulación endógena vs spyware gerencial, Ley de Little y ergonomía de terminal (`alo`).

* 🔍 **[`INFORME_NAMING_Y_DISPONIBILIDAD_OSS.md`](INFORME_NAMING_Y_DISPONIBILIDAD_OSS.md):**  
  Registro de validación en vivo contra APIs públicas (PyPI, crates.io, npm, GitHub y comandos de Linux) de más de 20 candidatos explorados.

* 🎨 **[`PROMPTS_IDENTIDAD_VISUAL_ALLOSTASIS.md`](PROMPTS_IDENTIDAD_VISUAL_ALLOSTASIS.md):**  
  Especificaciones técnicas JSON para motores de difusión (Banana Pro / FLUX / SDXL). Contiene el **Activo 1 (Isotipo "Dynamic Möbius Wave")** y el **Activo 2 (Banner Panorámico de GitHub)** con sus parámetros de cámara, iluminación, paleta `#080B10` / `#00F5D4` / `#FFB703` y variaciones.

---

## 🛠️ Herramientas y Skills Creadas

1. **Herramienta CLI:** [`~/Code/oss-name-checker/`](file:///home/johantv/Code/oss-name-checker/) — Script modular de validación en vivo de marcas en registros públicos.
2. **Skill Permanente de Arquitectura:** [`~/.agents/skills/go-cli-tui/SKILL.md`](file:///home/johantv/.agents/skills/go-cli-tui/SKILL.md) (fuente en `agents/skills/common/go-cli-tui/`) — Reglas de diseño reutilizables para cualquier CLI en Go con TUI de Charm y operación para agentes de IA.

---

## 🚦 Estado de Fases de Ejecución

- [x] **Fase de Investigación, Naming y Especificación:** 100% Completada y documentada en este directorio.
- [ ] **Fase 0 (Dotfiles Hygiene):** Pendiente de aplicar cambios a `core.md`, `skills-index.md` y `work.md`.
- [ ] **Fase 1 (Extracción Soberana):** Pendiente de ejecutar `git-filter-repo` hacia `~/Code/allostasis`.
- [ ] **Fase 2 (Núcleo de Dominio en Go):** Pendiente de iniciar implementación de `internal/domain/`.
- [ ] **Fase 3 (Adaptadores e Infraestructura):** SQLite Wazero y Git CLI wrapper.
- [ ] **Fase 4 (TUI y Lanzamiento OSS):** Bubble Tea + GoReleaser.
