# Phase 1 Report Template

Report in the user's language. Label every "After" value as projected (Phase 1 does not edit).

```markdown
### Scope
- Audited: [projects/files, user-level included or not]
- Excluded: [worktrees (count), vendored copies and backups, other repos not named, files not read]
- Freshness: [repo: clean/dirty, N behind as of last fetch, last commit date]
- Assumptions: [what was assumed because the user could not be asked]

### Verdict
`no change` | `local reorganization` | `split` | `+ repo walls`: one-line justification tied to a concrete problem.

### Context Surface (cost, not outcome)
| File / surface | Lines (now ➔ projected) | Tokens est. (now ➔ projected) |
| :--- | :---: | :---: |
| `path/file.md` | XX ➔ YY | ~AAA ➔ ~BBB |
Include surfaces beyond the file (auto-memory index, skill-description catalog, hook-injected text) when relevant. Tokens = chars/4 estimate; "now" is measured, "projected" is an estimate.
### Findings
1. **[Principle]** `file.md:LINE`
   - Problem: concise description (duplication, contradiction, noise, orphan, burial of a critical rule).
   - Evidence: official | measured | user contract | hypothesis (+ source)
   - Current text → proposed diff: exact replacement, move, removal or ignore rule.
   - Behavior consequence: what changes for the agent.
   - Unverified: what was not checked.
2. **[Ambiguity / Contradiction]** `file.md:LINE`
   - Question for the user: concrete options A vs B.

### Repo Surface (only if the task includes a large repo)
- Ignore walls: present / absent / deficient (local or shared)
- Noise zones without a wall: [list]
- Instruction file structure: monolithic / router / absent
- Entrypoints: declared / missing

### Not verified
List checks not run (host/model/sample) and claims left as hypotheses.

### Approval needed for
List each gated action (deletions, global rule edits, split, shared config).
```
