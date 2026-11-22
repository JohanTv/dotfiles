# Load Surface and Host Limits

Facts below were verified on 2026-11-21 against official docs; they drift, so re-verify before relying on them.

## What actually loads (Claude Code)
- CLAUDE.md files in the hierarchy above the cwd load at launch; subdirectory CLAUDE.md files load when Claude reads, writes or edits a file there. Rules without `paths:` load at launch; rules with `paths:` load when matching files are opened.
- `@path` imports expand at load time: they organize a file, they do not save context. Real deferral = skills, path-scoped rules, or plain pointers.
- Auto memory: the first 200 lines or 25 KB of `MEMORY.md` load at session start (setting `autoMemoryEnabled`, env `CLAUDE_CODE_DISABLE_AUTO_MEMORY=1`). It is model-written: check it for duplicates or contradictions of user rules.
- `claudeMdExcludes` skips irrelevant ancestor CLAUDE.md files (monorepos); it cannot exclude managed policy files.
- Official guidance: keep each CLAUDE.md under about 200 lines; longer files cost context and may reduce adherence. Investigate, do not target the number. Files over 4 MiB are skipped.

## Measure it
- Resolve the real config dir before looking for memory or user files: check `$CLAUDE_CONFIG_DIR` and the paths named in the loaded global instructions; `~/.claude` is only the default.
- `/context all` → Memory files list; `/memory` to browse; an `InstructionsLoaded` hook logs which files load, when and why (observational, cannot block).
- A CLAUDE.md alone misses the skill-description catalog, hook-injected text and `MEMORY.md`: count them.
- When sectioning by heading, ignore `#` lines inside code fences (they create phantom sections). Bytes are not tokens: label any ratio `est.`.

## Skill descriptions are always loaded
Every skill description sits in the catalog in every session and drives auto-activation. Audit each: declare explicit task intent, avoid generic quality words ("optimize", "improve") as sole triggers, keep it short (an upper bound of 1024 characters is reported for the Agent Skills format; unverified here).

## Other hosts (shared files, symlinks)
- Antigravity (agy): a single rule file is truncated at 24,000 bytes after expanding `@[label](path)`; active global and always-on rules share a 20,000-token budget and the largest files are demoted to pointers. Project `AGENTS.md`/`GEMINI.md`/`.agents/rules/*.md` load up to the repo root. A CLAUDE.md symlinked as AGENTS.md must satisfy the lowest limit.
- OpenCode and others: no verified limits; measure before assuming.
