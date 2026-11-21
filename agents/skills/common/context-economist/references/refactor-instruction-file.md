# Refactor an Instruction File

Procedure to assess a long instruction file and choose the smallest useful change: leave it, reorganize in place, or split into a compact router plus focused docs. Treat the entry file as a router, not a rule warehouse.

## 1. Identify the target
- Default to the user's named file; else the file most broadly loaded by the current agent setup (`AGENTS.md`, `CLAUDE.md`, `GEMINI.md`, rules).
- Several candidates and unclear choice → list them and ask.

## 2. Inspect
- Read the target fully. List existing `docs/` or rules dirs. Check backup state (git-tracked? else scratchpad copy, see SKILL.md).

## 3. Detect contradictions first
Scan for conflicting style rules, package managers, test commands, safety boundaries, precedence statements, and same-rule-different-wording duplicates. Resolve via SKILL.md principle 7. Do not restructure around an unresolved contradiction.

## 4. Choose the smallest useful change
- Ask: does splitting solve a concrete problem? If the file is compact or its rules are normally needed together → keep unchanged or reorganize in place.
- No change justified → explain why and stop. No backups, no new docs.
- Local reorganization: skip the docs map; limit edits and validation to what changed.
- Honor an explicit user request to split.

## 5. Classify rules by use, not topic
- **Stay in entrypoint:** always-on rules, safety-critical rules, short frequent facts/commands that prevent common mistakes.
- **Move to docs:** lengthy procedures, explanations or examples with an independent trigger needed only for some tasks.
- Weigh frequency of use and consequence of a missed rule.

## 6. Design the docs map
- Follow the project's existing convention (`docs/`, `.claude/rules/`, `.cursor/rules/`, ...); default to `docs/` for cross-agent portability.
- Preserve platform formats: frontmatter, imports, path globs, extensions.
- Mechanism caveat: in Claude Code, `@file` imports in CLAUDE.md load eagerly, so they do not defer cost. For lazy loading use skills, path-scoped rules, or plain docs referenced from a router (verify support for the agent in use).
- Reuse existing doc names; otherwise derive focused names from rule clusters. Add `docs/README.md` only if it aids navigation across several docs.
- Each route names an observable action/object, when to read, and the path. Derive triggers from the source rules; add no new requirements.

## 7. Edit conservatively
Rewrite the entrypoint with: scope statement, core principles, on-demand index, always-on safety/tool rules, precedence. Keep long-form guidance in one authoritative location; the entrypoint may keep a short constraint reminder linking to it, kept consistent.

### Entrypoint shape (adapt wording)
```md
# Agent Instructions

> Scope: entrypoint. Only always-on rules here; task details in docs/.

## Core Principles
- [default behavior / language]
- [safety boundary]
- [primary tool or evidence policy]

## Read-On-Demand Index
| Task or object | Read first | Trigger and timing |
| --- | --- | --- |
| [observable action] | `docs/[file].md` | Before [action] |

## Always-On Rules
- [short critical rules]

## Priority
1. User's current explicit instruction.
2. Nearest project instruction file.
3. This file.
4. Routed docs.
```

## 8. Validate (temporary work, not written to the repo unless asked)
1. **Preservation checklist:** per original rule category → new location, one verification keyword/heading, pass/fail.
2. **Force check** for moved/rewritten rules only: must / must not / should, applicability, timing, exceptions equal to the original.
3. **Counts:** `wc -l` before/after, plus estimated tokens of the always-loaded part.
4. **Keyword search:** `rg -n '<kw1>|<kw2>' <entry> <docs...>`. It detects omissions; it does not prove semantic preservation.
5. **Contradiction check:** no routed doc contradicts the entrypoint.
6. **Route test (required after a split):** write 3-5 realistic task prompts, each with the expected doc(s), plus one negative case that should load none. Using only the entrypoint, state which docs would be read; every trigger must be recognizable without opening the target. Any miss → fix the trigger wording.

## Guardrails
- Do not delete rules for verbosity; move them.
- Do not bury safety-critical rules only in routed docs.
- Do not create many tiny overlapping docs.
- Do not add opinions absent from the source unless asked.
