package out

import (
	"context"

	"{{ .ModulePath }}/internal/domain"
)

type ItemRepository interface {
	FindAll(ctx context.Context) ([]domain.Item, error)
	Save(ctx context.Context, item domain.Item) error
}
