package tui

import "github.com/charmbracelet/lipgloss"

var (
	PrimaryColor = lipgloss.Color("#7D56F4")
	SuccessColor = lipgloss.Color("#04B575")
	MutedColor   = lipgloss.Color("#626262")

	TitleStyle = lipgloss.NewStyle().
			Bold(true).
			Foreground(lipgloss.Color("#FFFDF5")).
			Background(PrimaryColor).
			Padding(0, 1)

	ItemStyle = lipgloss.NewStyle().
			PaddingLeft(2)

	SelectedItemStyle = lipgloss.NewStyle().
				PaddingLeft(1).
				Foreground(PrimaryColor).
				Bold(true)

	MutedStyle = lipgloss.NewStyle().
			Foreground(MutedColor)
)
