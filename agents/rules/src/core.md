# CLI Operations and Exploration Guidelines

### Primary Tooling:
- **Code/Text Search:** Always use `rg` (`-S` smart-case, `-n` line numbers, `-F` fixed strings).
  - *Token Economy:* Use `-l` to list matching files before dumping full contents.
  - *Strict Bounds:* Use `--max-columns 300` and `| head -n 50` to avoid saturating context. Exclude lockfiles: `-g '!*.lock' -g '!package-lock.json'`.
- **File/Folder Search:** Use `fd` (never `find`). Limit depth with `-d <N>` on broad queries (`fd -t d <name>`, `fd -t f <name>`).
- **JSON Queries:** Use `jq` to extract specific keys rather than dumping entire JSON payloads (e.g. `jq '.dependencies' package.json`; quote special keys: `jq '."$defs"'`).
- **In-Place Replacements (`sd`):** Use `sd` for regex replacements directly on files (fast, context-free): `sd 'pattern' 'replacement' file`.
- **Git Inspection:** Use compact formats (`git status -s`, `git diff --stat`, `git log --oneline -n 5`).

### Git Conventions and Commits:
- **Messages:** Conventional Commits (`feat:`, `fix:`, `refactor:`, `chore:`, etc.), single-line title only, in **English** (no extended descriptions/body, **no co-authors** or AI signatures like `Co-authored-by`).
- **Atomic Commits:** Group related changes into logical, balanced commits (avoid massive monoliths or trivial fragmentation).
- **Push Policy:** NEVER run `git push` unless explicitly ordered by the user (e.g., "push", "pushea", "haz push").

### Exclusions and Safety:
- **Dependencies and Caches:** Respect `.gitignore`. In searches rooted at `$HOME` (`~`), strictly exclude heavy caches: `-E ".bun" -E ".cache" -E ".npm" -E ".cargo" -E ".local/share" -E ".venv" -E "venv"`. Always prioritize the active workspace.
- **Secrets (.env):** Never search or expose `.env*` files containing live credentials in command output (only inspect `.env.example`).
