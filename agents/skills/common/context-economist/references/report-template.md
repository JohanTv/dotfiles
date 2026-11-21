# Phase 1 Report Template

Report in the user's language. Label every "After" value as projected (Phase 1 does not edit).

```markdown
### Verdict
`no change` | `local reorganization` | `split` | `+ repo walls`: one-line justification tied to a concrete problem.

### Token Economy and Context Surface
| File | Lines (now ➔ projected) | Tokens est. (now ➔ projected) | Saving |
| :--- | :---: | :---: | :---: |
| `path/file.md` | XX ➔ YY | ~AAA ➔ ~BBB | -ZZ% |
| **Total** | **XX ➔ YY** | **~AAA ➔ ~BBB** | **-ZZ%** |
Tokens = chars/4 estimate. "Now" is measured; "projected" is an estimate.

### Findings
1. **[Principle]** `file.md:LINE`
   - Problem: concise description (duplication, contradiction, noise, orphan, burial of a critical rule).
   - Proposal: exact replacement, move, removal or ignore rule.
2. **[Ambiguity / Contradiction]** `file.md:LINE`
   - Question for the user: concrete options A vs B.

### Repo Surface (only if the task includes a large repo)
- Ignore walls: present / absent / deficient (local or shared)
- Noise zones without a wall: [list]
- Instruction file structure: monolithic / router / absent
- Entrypoints: declared / missing

### Approval needed for
List each gated action (deletions, global rule edits, split, shared config).
```
