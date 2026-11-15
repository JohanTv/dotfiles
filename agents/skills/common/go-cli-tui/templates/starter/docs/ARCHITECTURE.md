# System Architecture Specification

## Overview

This system is built as a sovereign Go CLI & TUI tool following clean Hexagonal Architecture (Ports and Adapters), Twelve-Factor CLI design principles, and strict M2M (Machine-to-Machine) communication contracts.

```text
                  +--------------------------------+
                  |           cmd/app/             |
                  |     (Cobra CLI / Entrypoint)   |
                  +---------------+----------------+
                                  |
              +-------------------+-------------------+
              |                                       |
              v                                       v
    [ internal/presentation/ ]             [ internal/presentation/ ]
    [      cli (json / plain) ]             [       tui (Charm)     ]
              |                                       |
              +-------------------+-------------------+
                                  |
                                  v
                      [ internal/ports/in/ ]
                                  |
                                  v
                     [ internal/domain/ ]
                    (Pure business logic)
                                  |
                                  v
                      [ internal/ports/out/ ]
                                  |
                                  v
                    [ internal/adapters/storage/ ]
                    (ncruces/go-sqlite3 Wazero)
```

## Key Invariants

1. **Terminal Firewall:** When executed non-interactively or with `--json`, interactive Charm components are never instantiated.
2. **Zero CGO:** The binary compiles statically with `CGO_ENABLED=0` across all architectures using WebAssembly JIT via `ncruces/go-sqlite3`.
3. **WAL Concurrency:** SQLite is configured with separate connection pools: a single-connection writer pool and a multi-connection reader pool with `PRAGMA query_only=ON`.
