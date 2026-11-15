# Persistencia SQLite Pure-Go con Wazero (`ncruces/go-sqlite3`)

Este documento especifica el patrón arquitectural para persistencia embebida sin CGO (`CGO_ENABLED=0`), logrando binarios estáticos portables y concurrencia segura con Write-Ahead Logging (WAL).

---

## 1. Justificación de Pure-Go frente a `mattn/go-sqlite3`

| Aspecto | `mattn/go-sqlite3` | `ncruces/go-sqlite3` (Wazero JIT) |
| :--- | :--- | :--- |
| **CGO** | Requiere CGO (`CGO_ENABLED=1`), toolchain C instalada (gcc/clang). | **Cero CGO (`CGO_ENABLED=0`)**, compila en cualquier entorno. |
| **Cross-Compilation** | Compleja; requiere cross-compilers para cada arquitectura/OS. | **Nativa y trivial:** `GOOS=darwin GOARCH=arm64 go build`. |
| **Rendimiento** | Nativo C. | Compilación JIT vía WebAssembly a solo ~5-15% del rendimiento nativo. |
| **Extensiones** | Requiere flags de compilación C. | Trae embebidos FTS5, JSON1, Math functions y Geopoly. |

---

## 2. Patrón Dual-Pool WAL (Writer / Reader Isolation)

SQLite en modo WAL soporta múltiples lectores simultáneos, pero **exactamente un único escritor** a la vez. Si dos goroutines intentan escribir simultáneamente en el mismo pool de conexiones, SQLite puede retornar `sqlite: database is locked (busy)`.

Para garantizar cero bloqueos concurrentes:

```go
type DB struct {
    Writer *sql.DB // MaxOpenConns = 1
    Reader *sql.DB // MaxOpenConns = NumCPU * 2
}

func Open(dbPath string) (*DB, error) {
    // Configurar DSN con pragmas WAL esenciales
    dsn := fmt.Sprintf("file:%s?_pragma=busy_timeout(5000)&_pragma=journal_mode(WAL)&_pragma=synchronous(NORMAL)&_pragma=foreign_keys(ON)", dbPath)

    // Pool de Escritura: exactamente 1 conexión abierta para serializar mutaciones
    writer, err := sql.Open("sqlite3", dsn)
    if err != nil {
        return nil, err
    }
    writer.SetMaxOpenConns(1)
    writer.SetConnMaxLifetime(0)

    // Pool de Lectura: escalable según núcleos de CPU, con query_only defensivo
    readerDSN := dsn + "&_pragma=query_only(ON)"
    reader, err := sql.Open("sqlite3", readerDSN)
    if err != nil {
        writer.Close()
        return nil, err
    }
    reader.SetMaxOpenConns(runtime.NumCPU() * 2)
    reader.SetMaxIdleConns(runtime.NumCPU())

    return &DB{Writer: writer, Reader: reader}, nil
}
```

---

## 3. Pruebas Rápidas en Memoria (`test_mem`)

Para suites de pruebas unitarias ultrarrápidas (<10ms por test) sin tocar disco:

```go
func NewTestDB(t *testing.T) *DB {
    t.Helper()
    // Base de datos en memoria compartida y única por test
    dsn := fmt.Sprintf("file:mem_%s?mode=memory&cache=shared&_pragma=foreign_keys(ON)", t.Name())
    db, err := sql.Open("sqlite3", dsn)
    if err != nil {
        t.Fatalf("fallo al abrir db en memoria: %v", err)
    }
    // IMPORTANTE: En SQLite en memoria compartida, mantener al menos 1 conexión abierta
    // para evitar que la base de datos se destruya al cerrarse la última conexión.
    db.SetMaxOpenConns(1)
    t.Cleanup(func() { db.Close() })

    // Ejecutar migraciones DDL...
    return &DB{Writer: db, Reader: db}
}
```

---

## 4. DDL Embebido con `embed.FS`

Mantén el esquema SQL en archivos separados versionados, embebidos directamente en el binario final:

```go
//go:embed schema.sql
var schemaFS embed.FS

func (db *DB) Migrate(ctx context.Context) error {
    schema, err := schemaFS.ReadFile("schema.sql")
    if err != nil {
        return fmt.Errorf("error al leer schema.sql embebido: %w", err)
    }
    _, err = db.Writer.ExecContext(ctx, string(schema))
    return err
}
```
