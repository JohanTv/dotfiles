package sqlite

import (
	"context"
	"database/sql"
	_ "embed"
	"fmt"
	"os"
	"path/filepath"
	"runtime"

	_ "github.com/ncruces/go-sqlite3/driver"
	_ "github.com/ncruces/go-sqlite3/embed"
)

//go:embed schema.sql
var schemaSQL string

type DB struct {
	Writer *sql.DB
	Reader *sql.DB
}

func Open(dbPath string) (*DB, error) {
	var writeDSN, readDSN string
	isMem := false

	if dbPath == ":memory:" {
		isMem = true
		writeDSN = "file:app_mem?mode=memory&cache=shared&_pragma=busy_timeout(5000)&_pragma=foreign_keys(ON)"
		readDSN = writeDSN
	} else {
		if err := os.MkdirAll(filepath.Dir(dbPath), 0755); err != nil {
			return nil, fmt.Errorf("error creando directorio para sqlite: %w", err)
		}
		writeDSN = fmt.Sprintf("file:%s?_pragma=busy_timeout(5000)&_pragma=journal_mode(WAL)&_pragma=synchronous(NORMAL)&_pragma=foreign_keys(ON)", dbPath)
		readDSN = fmt.Sprintf("file:%s?_pragma=busy_timeout(5000)&_pragma=journal_mode(WAL)&_pragma=synchronous(NORMAL)&_pragma=foreign_keys(ON)&_pragma=query_only(ON)", dbPath)
	}

	writer, err := sql.Open("sqlite3", writeDSN)
	if err != nil {
		return nil, fmt.Errorf("error abriendo writer sqlite: %w", err)
	}
	writer.SetMaxOpenConns(1)
	writer.SetConnMaxLifetime(0)

	var reader *sql.DB
	if isMem {
		reader = writer
	} else {
		reader, err = sql.Open("sqlite3", readDSN)
		if err != nil {
			writer.Close()
			return nil, fmt.Errorf("error abriendo reader sqlite: %w", err)
		}
		reader.SetMaxOpenConns(runtime.NumCPU() * 2)
		reader.SetMaxIdleConns(runtime.NumCPU())
	}

	db := &DB{Writer: writer, Reader: reader}
	if err := db.Migrate(context.Background()); err != nil {
		db.Close()
		return nil, fmt.Errorf("error ejecutando migraciones iniciales: %w", err)
	}

	return db, nil
}

func (db *DB) Migrate(ctx context.Context) error {
	_, err := db.Writer.ExecContext(ctx, schemaSQL)
	return err
}

func (db *DB) Close() error {
	var errW, errR error
	if db.Writer != nil {
		errW = db.Writer.Close()
	}
	if db.Reader != nil && db.Reader != db.Writer {
		errR = db.Reader.Close()
	}
	if errW != nil {
		return errW
	}
	return errR
}
