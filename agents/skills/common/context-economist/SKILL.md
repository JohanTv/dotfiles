---
name: context-economist
description: Audit and optimize AI-agent context. Instruction files (AGENTS.md/CLAUDE.md/GEMINI.md, rules), prompts, skills, docs, and large-codebase noise. Covers token economy, progressive disclosure, SSOT, router/split refactors, contradiction detection, ignore walls, entrypoint pinning. Use when auditing rules, cutting token usage, splitting a bloated instruction file, or preparing a big repo for agent work. Not for ordinary coding or bug fixing.
---

# Context Economist

Orchestrator for auditing and optimizing the context injected into agents. Goal: maximum value per token with zero loss of rule intent. Details live in `references/` and are loaded on demand.

## When NOT to activate
Normal coding or bug fixes that do not touch instructions, context architecture or search/scan boundaries.

## Route (read only the matching reference, never by default)

| Task | Read first |
| :--- | :--- |
| Split, reorganize or slim an instruction file (AGENTS.md, CLAUDE.md, GEMINI.md, rules) | `references/refactor-instruction-file.md` |
| Large repo / monorepo, noisy searches, agent exploring blindly, `.ignore`, entrypoints | `references/large-codebase.md` |
| Writing the Phase 1 report | `references/report-template.md` |

## Principles

1. **Token economy.** Every always-loaded line must change agent behavior. No filler, courtesy or repetition. Prefer dense bullets over prose. Keep a one-line "why" only when it disambiguates an edge case.
2. **SSOT.** One canonical home per rule; other files link to it. A short reminder of a critical rule may stay next to its link. Dedupe across layers only if the higher layer is guaranteed to load in every agent/harness that needs the rule.
3. **Progressive disclosure, 4 layers.** L1 always-on prompt (universal invariants) → L2 repo instruction file (commands, project constraints; router in monorepos) → L3 skills (on-demand procedures) → L4 `references/` (deep docs, templates, catalogs).
4. **Placement criterion, not token quotas.** Place content by `load cost` vs `probability of being needed × cost of missing it`. Safety-critical rules stay always-on even if they apply to few tasks. Short, frequently used facts (package manager, test command) stay in the entrypoint. Never move content just because of its topic.
5. **Observable triggers.** Every skill/reference declares when to read it. The trigger must be recognizable from an action or object *without* reading the target.
6. **Normative tone.** Directives like "Do X", "Never Y", "Use A instead of B". No motivational or psychological text.
7. **No guessing.** If a rule has two reasonable readings or a gap, flag it and ask with concrete options A/B. Contradictions: resolve by explicit user instruction > nearest instruction file > local evidence; ask only if unresolved and it affects the change.
8. **Preserve before reduce.** Moving is always allowed; deleting a rule needs SSOT proof plus approval. Preserve force (must / must not / should), scope, timing and exceptions.
9. **Pruning scope.** Only docs, directives and orphan artifacts (unreferenced `.md`, dead links, stale build vars). Never delete executable source without compiler-level analysis and explicit authorization. Keep the rationale and rejected alternatives in ADRs/RFCs.
10. **Portability.** No hardcoded user paths; use `$HOME`, `~` or relative paths.
11. **"No change" is a valid verdict.** Splitting is justified only by a concrete problem (bloat, duplication, contradictions, noise). A compact file whose rules are needed together stays as is.

## Situation → action

| Situation | Action |
| :--- | :--- |
| Redundant sections in one file | Merge into one concise section |
| Same rule in two files | Pick SSOT (higher layer, if reliably loaded); replace the other with a link or short reminder |
| Operational rule mixed with long explanation | One-line rule in place; deep guide to `docs/` or `references/` |
| Contradictory rules | Resolve per principle 7 before any restructuring |
| Orphan file (no index, no build ref) | Propose removal; delete only after approval |
| Entry file bloated across several domains | Router + focused docs (see refactor reference) |
| Generated code / mocks / snapshots polluting search | Ignore walls (see large-codebase reference) |

## Workflow

**Phase 1: Diagnose (read-only).**
Map context sources (global rules, project files, skills, docs). Measure: `wc -l`, plus tokens as an estimate (chars/4, labeled estimate). Detect duplicates, contradictions, orphans, noise. Issue a verdict: `no change` | `local reorganization` | `split` | `+ repo walls`. Report with `references/report-template.md`.

**Approval gate.** Required before: deleting files or rules, editing global rules, splitting, adding repo-shared config (`.ignore`, etc.). Not required for a rule-preserving in-place edit of one non-global file.

**Phase 2: Remediate.**
- Backup: if the file is tracked in git, none (git is the backup). Otherwise copy to the session scratchpad, never next to the file.
- Apply the smallest change that fixes the diagnosed problem.
- Validate: preservation checklist (see refactor reference), route test when a split was done, and the repo's own verifiers if they exist (`make` targets, doc checks, link checks).
- Leave changes in the working tree. Commit/push only on explicit user order.

## Safeguards
- Do not alter intent or relax safety restrictions without approval.
- Do not bury safety-critical rules in routed docs.
- Do not create many tiny overlapping docs.
- Do not add project opinions absent from the source.
- Use the user's/project's tooling conventions for search and edits.
- Report to the user in the language set by their global instructions, regardless of this file's language.
