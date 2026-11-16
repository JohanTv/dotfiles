---
name: oss-name-checker
description: Valida en tiempo real y sin alucinaciones la disponibilidad de nombres, alias y paquetes para proyectos Open Source en registros públicos (PyPI, crates.io, npm, GitHub y comandos de Unix). Activa esta habilidad cuando el usuario proponga nombres para un proyecto, busque alias libres, bautice herramientas o solicite evaluar colisiones de marca y riesgo de namespace.
---

# Skill: Validador de Nombres y Disponibilidad Open Source (`oss-name-checker`)

Esta habilidad proporciona un **oráculo determinista en tiempo real** para verificar si un nombre propuesto para una herramienta, librería o proyecto de código abierto está verdaderamente disponible o si sufre de colisiones graves en registros públicos o en el entorno local de terminal.

> [!IMPORTANT]
> **Prohibición de adivinación:** NUNCA afirmes que un nombre está "libre" basándote únicamente en tu conocimiento previo de entrenamiento (los registros de PyPI, npm y crates.io cambian a diario). Ejecuta SIEMPRE `oss-name-checker` antes de dar un dictamen de disponibilidad.

---

## 1. El Bucle de Bautizo Canónico (Naming Workflow)

Cuando el usuario pida bautizar un proyecto o evaluar candidatos:

1. **Fase 1 (Generación Creativa):** Propón entre 3 y 6 nombres conceptuales basados en etimología (raíces griegas/latinas), metáforas ontológicas o brevedad mnemotécnica, asignando un alias corto para terminal (ej. `allostasis:alo`, `conexo:cnx`).
2. **Fase 2 (Verificación Determinista):** Ejecuta `oss-name-checker` con el flag `--markdown`.
3. **Fase 3 (Presentación):** Entrega la tabla GFM generada directamente al usuario destacando los candidatos clasificados como `EXCELLENT` o `GOOD`.

---

## 2. Comandos y Sintaxis

La herramienta está disponible globalmente en el sistema como `oss-name-checker` (y en el script de la skill):

```bash
# 1. Validación de múltiples candidatos con salida en tabla Markdown:
oss-name-checker candidato1:alias1 candidato2:alias2 candidato3:alias3 --markdown

# 2. Validación de un candidato individual:
oss-name-checker allostasis --alias alo

# 3. Salida estructurada JSON (ideal para procesar en subagentes o pipelines):
oss-name-checker allostasis turgor --json

# 4. Validación masiva desde un archivo de texto (un candidato por línea):
oss-name-checker --file /ruta/a/candidatos.txt --markdown
```

*Nota:* Si por alguna razón el binario global no estuviese en `$PATH`, puedes invocar directamente el script de la skill:
```bash
python3 ~/.agents/skills/oss-name-checker/scripts/name_checker.py <argumentos>
```

---

## 3. Registros y Entornos Consultados

El checker consulta APIs oficiales en vivo sin requerir claves API ni dependencias externas:
1. **PyPI (Python):** `https://pypi.org/pypi/<name>/json`
2. **crates.io (Rust):** `https://crates.io/api/v1/crates/<name>`
3. **npm (Node.js):** `https://registry.npmjs.org/<name>`
4. **GitHub Repositories:** Relevancia, estrellas y existencia vía `gh api` o HTTP público.
5. **Unix Command Collision:** Verifica colisión con binarios instalados en `$PATH` o comandos nativos de la shell del host (`which`, `type`).

---

## 4. Escala de Riesgo y Clasificación

El script asigna un puntaje de riesgo de 0 a 100:

| Rango de Puntos | Nivel de Riesgo | Significado Operativo | Acción Recomendada |
| :---: | :---: | :--- | :--- |
| **0 pts** | 🟢 `EXCELLENT` | Nombre 100% libre en PyPI, crates, npm, GitHub y sin colisión Unix. | **Aprobado para uso inmediato.** |
| **1 – 20 pts** | 🟡 `GOOD` | Libre en los registros clave; menciones mínimas o inactivas en GitHub. | **Recomendado** tras verificar que el repo no tenga tracción. |
| **21 – 50 pts** | 🟠 `MODERATE` | Colisión parcial en un registro secundario o proyecto menor. | Proceder con cautela o preferir otro candidato. |
| **> 50 pts** | 🔴 `DISCARDED` | Colisión en registros oficiales principales o alias ocupado en Linux. | **Descartar.** Evita conflictos de instalación y soporte. |
