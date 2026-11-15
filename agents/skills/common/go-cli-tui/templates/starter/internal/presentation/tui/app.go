package tui

import (
	"context"
	"fmt"
	"strings"

	tea "github.com/charmbracelet/bubbletea"

	"{{ .ModulePath }}/internal/domain"
	"{{ .ModulePath }}/internal/ports/in"
)

type ItemsLoadedMsg struct {
	Items []domain.Item
	Err   error
}

type Model struct {
	service in.ItemService
	items   []domain.Item
	cursor  int
	loading bool
	err     error
}

func NewModel(service in.ItemService) Model {
	return Model{
		service: service,
		loading: true,
	}
}

func (m Model) Init() tea.Cmd {
	return m.fetchItemsCmd()
}

func (m Model) fetchItemsCmd() tea.Cmd {
	return func() tea.Msg {
		items, err := m.service.ListItems(context.Background())
		return ItemsLoadedMsg{Items: items, Err: err}
	}
}

func (m Model) Update(msg tea.Msg) (tea.Model, tea.Cmd) {
	switch msg := msg.(type) {
	case tea.KeyMsg:
		switch msg.String() {
		case "q", "ctrl+c":
			return m, tea.Quit
		case "up", "k":
			if m.cursor > 0 {
				m.cursor--
			}
		case "down", "j":
			if m.cursor < len(m.items)-1 {
				m.cursor++
			}
		case "r":
			m.loading = true
			return m, m.fetchItemsCmd()
		}
	case ItemsLoadedMsg:
		m.loading = false
		m.err = msg.Err
		if msg.Err == nil {
			m.items = msg.Items
		}
	}
	return m, nil
}

func (m Model) View() string {
	var b strings.Builder
	b.WriteString(TitleStyle.Render("{{ .AppTitle }} · Explorador TUI") + "\n\n")

	if m.loading {
		b.WriteString("  Cargando datos...\n")
		return b.String()
	}

	if m.err != nil {
		b.WriteString(fmt.Sprintf("  Error: %v\n", m.err))
		return b.String()
	}

	if len(m.items) == 0 {
		b.WriteString("  No hay elementos registrados en la base de datos.\n")
	} else {
		for i, it := range m.items {
			cursor := " "
			style := ItemStyle
			if m.cursor == i {
				cursor = ">"
				style = SelectedItemStyle
			}
			b.WriteString(style.Render(fmt.Sprintf("%s %s (%s)", cursor, it.Title, it.ID)) + "\n")
		}
	}

	b.WriteString("\n" + MutedStyle.Render("  [j/k o flechas]: navegar • [r]: refrescar • [q]: salir") + "\n")
	return b.String()
}

type Presenter struct {
	service in.ItemService
}

func NewPresenter(service in.ItemService) *Presenter {
	return &Presenter{service: service}
}

func (p *Presenter) Launch(ctx context.Context) error {
	pProg := tea.NewProgram(NewModel(p.service))
	_, err := pProg.Run()
	return err
}
