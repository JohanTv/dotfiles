# Refactor an Instruction File

Procedure to assess a long instruction file and choose the smallest useful change: leave it, reorganize in place, or split into a compact router plus focused docs. Treat the entry file as a router, not a rule warehouse.

> For a Phase 1 audit read §2, §3 and §5. §6 to §8 apply only in Phase 2 after approval.

## 1. Identify the target
- Default to the user's named file; else the file most broadly loaded by the current agent setup (`AGENTS.md`, `CLAUDE.md`, `GEMINI.md`, rules).
- Several candidates and unclear choice → list them and ask.

## 2. Inspect
- Read the target fully. List existing `docs/` or rules dirs. Before any edit, record the baseline (resolved real path, sha256, backup path; see SKILL.md Phase 2).
- Claude Code ≥ v2.1.283 documents `/doctor prompt-audit` (stale, conflicting or dangling-reference findings with proposed edits; read-only until you apply them). Use it as a pre-scan and treat its findings as hypotheses.

## 3. Detect contradictions first
Scan for conflicting style rules, package managers, test commands, safety boundaries, precedence statements, skill templates or examples that tell the agent to copy existing code or use a pattern the entrypoint forbids, docs that deny files that exist, and same-rule-different-wording duplicates. Resolve via SKILL.md principle 7. Do not restructure around an unresolved contradiction.

## 4. Choose the smallest useful change
- Ask: does splitting solve a concrete problem? If the file is compact or its rules are normally needed together → keep unchanged or reorganize in place.
- No change justified → explain why and stop. No backups, no new docs.
- Local reorganization: skip the docs map; limit edits and validation to what changed.
- Honor an explicit user request to split.

## 5. Classify rules by use, not topic
- **Stay in entrypoint:** always-on rules, safety-critical rules, short frequent facts/commands that prevent common mistakes.
- **Move to docs:** lengthy procedures, explanations or examples with an independent trigger needed only for some tasks.
- Weigh frequency of use and consequence of a missed rule.
- **Cut candidates (never auto-delete).** Litmus: would deleting the line make the agent err? Candidates: inferable from code/structure/filenames; standard language or framework conventions; self-evident advice ("write clean code"); already owned by a canonical source (name it); obsolete one-off fixes; workarounds written for older model behavior; checks that must run deterministically (route to hook/CI/permission, but do not add the mechanism without approval). Each candidate needs original text, evidence and behavior consequence; necessity you cannot prove stays `unknown`, not deleted.
- **Scope check.** User-level files load in every project: keep only cross-project rules there. Project names, deploy targets, paths and credentials belong to the project file; routing pointers with a trigger may stay.

## 6. Design the docs map
- Follow the project's existing convention (`docs/`, `.claude/rules/`, `.cursor/rules/`, ...); default to `docs/` for cross-agent portability.
- Preserve platform formats: frontmatter, imports, path globs, extensions.
- Mechanism caveat: in Claude Code, `@file` imports in CLAUDE.md load eagerly, so they do not defer cost. For lazy loading use skills, path-scoped rules, or plain docs referenced from a router (verify support for the agent in use).
- Reuse existing doc names; otherwise derive focused names from rule clusters. Add `docs/README.md` only if it aids navigation across several docs.
- Each route names an observable action/object, when to read, and the path. Derive triggers from the source rules; add no new requirements.
- **Carrier by two questions:** does the trigger self-report (command, file or keyword shows the intent)? is a violation recoverable?

  | Trigger | Recoverable | Irreversible |
  | --- | --- | --- |
  | Self-reports | skill or reference with trigger | existing enforcement (permission/hook) if mechanically decidable, plus a minimal always-on authorization line |
  | Observable tool event only | on-demand reference; consider a reminder hook | reminder hook plus a minimal always-on constraint |
  | Neither | always-on if error cost × frequency justifies it | always-on |

  A hook firing, its output being visible and the model obeying it are three different facts; verify each. Do not add a hook just to shrink a file, and never add one without approval.
- Extra index entries only when keyed by a different lookup path and missed reads were measured; entries are pointers, never copies.

## 7. Edit conservatively
Move verbatim, compress separately. Copy a moved block byte for byte; derive the short entrypoint version afterwards as its own edit. Compressing while moving silently drops qualifiers (conditions, numbers, negations). Before writing any pointer ("see X"), confirm the target actually contains the text: a pointer to missing content is worse than a visible loss.

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

## Priority (only if the source defines one)
[as in the source]
```

## 8. Validate (temporary work, not written to the repo unless asked)
1. **Preservation checklist:** per original rule category → new location, one verification keyword/heading, disposition (`moved-verbatim` | `deduped` (cite canonical source) | `corrected` (cite authority) | `retired` (cite approval)), pass/fail. A change that fits no disposition is a regression: restore it.
2. **Force check** for moved/rewritten rules only: must / must not / should, applicability, timing, exceptions equal to the original, plus a word-level diff of operative clauses (conditions, numbers, enumerations, negations), e.g. `git diff --word-diff`; every non-equal hunk must map to a declared change.
3. **Counts (a cost, not a result):** `wc -l` before/after, plus estimated tokens of the always-loaded part.
4. **Keyword search:** `rg -n '<kw1>|<kw2>' <entry> <docs...>`. It detects omissions; it does not prove semantic preservation.
   For blocks moved verbatim, keyword hits are not enough: a multi-line `grep -F`/`rg -F -f` pattern ORs its lines, so a half-moved block still matches (tested). Save the original block to a file and test full-string containment: `rg -U -F -c -- "$(cat orig.txt)" target.md`, or `python3 -c 'from pathlib import Path as P; print(P("orig.txt").read_bytes() in P("target.md").read_bytes())'`.
5. **Contradiction check:** no routed doc contradicts the entrypoint.
6. **Route test (required after a split):** write 3-5 realistic task prompts, each with the expected doc(s), plus one negative case that should load none. Using only the entrypoint, state which docs would be read; every trigger must be recognizable without opening the target. Any miss → fix the trigger wording.
   When possible, confirm in the real host: fresh session, same cwd, expected files loaded (`/context all` → Memory files, `/memory`, or an `InstructionsLoaded` hook log), then the representative tasks plus one control that must not load the doc. Report host, model, sample size and what was not run; anything not run is `unverified`, and one success is not evidence of better adherence.

## Guardrails
- Do not bury safety-critical rules only in routed docs.
- Do not create many tiny overlapping docs.
- Do not add opinions absent from the source unless asked.
