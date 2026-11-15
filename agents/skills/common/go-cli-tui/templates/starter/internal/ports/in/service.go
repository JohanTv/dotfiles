package in

import (
	"context"

	"{{ .ModulePath }}/internal/domain"
)

type ItemService interface {
	ListItems(ctx context.Context) ([]domain.Item, error)
	CreateItem(ctx context.Context, title string) (*domain.Item, error)
}
