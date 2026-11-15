package bootstrap

import (
	"context"
	"fmt"
	"os"
	"path/filepath"
	"time"

	"{{ .ModulePath }}/internal/adapters/storage/sqlite"
	"{{ .ModulePath }}/internal/domain"
	"{{ .ModulePath }}/internal/ports/in"
	"{{ .ModulePath }}/internal/ports/out"
	"{{ .ModulePath }}/internal/presentation/json"
	"{{ .ModulePath }}/internal/presentation/plain"
	"{{ .ModulePath }}/internal/presentation/tui"
)

type Application struct {
	ItemService    in.ItemService
	JSONPresenter  *json.Presenter
	PlainPresenter *plain.Presenter
	TUIPresenter   *tui.Presenter
}

type itemServiceImpl struct {
	repo out.ItemRepository
}

func (s *itemServiceImpl) ListItems(ctx context.Context) ([]domain.Item, error) {
	return s.repo.FindAll(ctx)
}

func (s *itemServiceImpl) CreateItem(ctx context.Context, title string) (*domain.Item, error) {
	item := domain.Item{
		ID:        fmt.Sprintf("item-%d", time.Now().UnixNano()),
		Title:     title,
		CreatedAt: time.Now(),
	}
	if err := s.repo.Save(ctx, item); err != nil {
		return nil, err
	}
	return &item, nil
}

func Initialize(ctx context.Context) (*Application, func(), error) {
	homeDir, err := os.UserHomeDir()
	if err != nil {
		homeDir = "."
	}
	dbPath := filepath.Join(homeDir, ".local", "share", "{{ .AppName }}", "app.db")

	db, err := sqlite.Open(dbPath)
	if err != nil {
		return nil, nil, fmt.Errorf("fallo abriendo sqlite: %w", err)
	}

	repo := sqlite.NewRepository(db)
	service := &itemServiceImpl{repo: repo}

	// Si está vacío, sembrar un dato de demostración
	items, _ := repo.FindAll(ctx)
	if len(items) == 0 {
		_ = repo.Save(ctx, domain.Item{
			ID:        "item-init",
			Title:     "Primer elemento de bienvenida",
			CreatedAt: time.Now(),
		})
	}

	app := &Application{
		ItemService:    service,
		JSONPresenter:  json.NewPresenter(),
		PlainPresenter: plain.NewPresenter(),
		TUIPresenter:   tui.NewPresenter(service),
	}

	cleanup := func() {
		_ = db.Close()
	}

	return app, cleanup, nil
}
