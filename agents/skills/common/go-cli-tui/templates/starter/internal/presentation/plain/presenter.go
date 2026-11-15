package plain

import (
	"fmt"
	"os"

	"{{ .ModulePath }}/internal/domain"
)

type Presenter struct{}

func NewPresenter() *Presenter {
	return &Presenter{}
}

func (p *Presenter) RenderItems(items []domain.Item) error {
	if len(items) == 0 {
		fmt.Println("No hay elementos registrados.")
		return nil
	}

	for _, item := range items {
		fmt.Fprintf(os.Stdout, "%s\t%s\t%s\n", item.ID, item.Title, item.CreatedAt.Format("2006-01-02 15:04:05"))
	}
	return nil
}
