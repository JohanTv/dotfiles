package sqlite

import (
	"context"
	"time"

	"{{ .ModulePath }}/internal/domain"
	"{{ .ModulePath }}/internal/ports/out"
)

type Repository struct {
	db *DB
}

var _ out.ItemRepository = (*Repository)(nil)

func NewRepository(db *DB) *Repository {
	return &Repository{db: db}
}

func (r *Repository) FindAll(ctx context.Context) ([]domain.Item, error) {
	rows, err := r.db.Reader.QueryContext(ctx, "SELECT id, title, created_at FROM items ORDER BY created_at DESC")
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var items []domain.Item
	for rows.Next() {
		var it domain.Item
		var created string
		if err := rows.Scan(&it.ID, &it.Title, &created); err != nil {
			return nil, err
		}
		it.CreatedAt, _ = time.Parse(time.RFC3339, created)
		items = append(items, it)
	}
	return items, rows.Err()
}

func (r *Repository) Save(ctx context.Context, item domain.Item) error {
	query := "INSERT INTO items (id, title, created_at) VALUES (?, ?, ?)"
	_, err := r.db.Writer.ExecContext(ctx, query, item.ID, item.Title, item.CreatedAt.Format(time.RFC3339))
	return err
}
