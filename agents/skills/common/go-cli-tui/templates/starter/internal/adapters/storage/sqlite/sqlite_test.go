package sqlite

import (
	"context"
	"testing"
	"time"

	"{{ .ModulePath }}/internal/domain"
)

func TestSQLiteRepository(t *testing.T) {
	db, err := Open(":memory:")
	if err != nil {
		t.Fatalf("error abriendo db en memoria: %v", err)
	}
	defer db.Close()

	repo := NewRepository(db)
	ctx := context.Background()

	item := domain.Item{
		ID:        "item-1",
		Title:     "Primer elemento de prueba",
		CreatedAt: time.Now().Truncate(time.Second),
	}

	if err := repo.Save(ctx, item); err != nil {
		t.Fatalf("error guardando item: %v", err)
	}

	items, err := repo.FindAll(ctx)
	if err != nil {
		t.Fatalf("error listando items: %v", err)
	}

	if len(items) != 1 {
		t.Fatalf("se esperaba 1 item, obtenidos %d", len(items))
	}

	if items[0].Title != item.Title {
		t.Errorf("título incorrecto: esperado '%s', obtenido '%s'", item.Title, items[0].Title)
	}
}
