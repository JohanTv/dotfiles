# Patrones de Arquitectura TUI con el Ecosistema Charm (Bubble Tea, Lip Gloss)

Este documento describe las directrices para implementar interfaces interactivas desacopladas en Go usando The Elm Architecture (TEA).

---

## 1. El Ciclo Reactivo de Bubble Tea (TEA)

```
        +-----------------------------------+
        |                                   |
        v                                   |
     [ View ] ----> (Renderiza en TTY)     |
        ^                                   |
        |                                   |
    [ Update ] <--- [ tea.Msg ]             |
        |                  ^                |
        +--- (tea.Cmd) ----+----------------+
```

### Reglas Inquebrantables de TEA:
1. **`Update` 100% Síncrono e Instantáneo (<16ms):** Nunca realices I/O, consultas a base de datos, llamadas HTTP ni invocaciones `exec.Command` dentro del método `Update`. Bloquear `Update` congela el bucle de renderizado a 60 FPS.
2. **I/O Asíncrono vía `tea.Cmd`:** Cualquier operación bloqueante debe retornar un `tea.Cmd`, que ejecuta la goroutine en segundo plano y devuelve un `tea.Msg` al bucle principal al concluir.
3. **Estado Inmutable / CQS:** Trata el modelo en `Update` como un valor. Retorna siempre una copia modificada.

---

## 2. Patrón para Operaciones Asíncronas

```go
type ItemLoadedMsg struct {
    Items []domain.Item
    Err   error
}

func fetchItemsCmd(svc ports.ItemService) tea.Cmd {
    return func() tea.Msg {
        ctx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
        defer cancel()

        items, err := svc.ListItems(ctx)
        return ItemLoadedMsg{Items: items, Err: err}
    }
}

func (m Model) Update(msg tea.Msg) (tea.Model, tea.Cmd) {
    switch msg := msg.(type) {
    case tea.KeyMsg:
        if msg.String() == "r" {
            m.loading = true
            return m, fetchItemsCmd(m.service)
        }
    case ItemLoadedMsg:
        m.loading = false
        if msg.Err != nil {
            m.err = msg.Err
            return m, nil
        }
        m.items = msg.Items
        return m, nil
    }
    return m, nil
}
```

---

## 3. Estilos y Accesibilidad con Lip Gloss

- **Soporte No-TTY / `NO_COLOR`:** Respeta la especificación `NO_COLOR` automáticamente gracias a Lip Gloss.
- **Jerarquía Visual:**
  - Primario: Azules o Cyan para navegación y selecciones activas.
  - Éxito: Verde (`#04B575`).
  - Alerta / Destructivo: Rojo suave o magenta (`#FF5F87`).
  - Textos secundarios / metadatos: Gris (`#767676`).
- **Diseño Adaptativo:** Escucha el mensaje `tea.WindowSizeMsg` para ajustar anchos y alturas dinámicamente (`lipgloss.Width()`, `lipgloss.Height()`).

---

## 4. Pruebas Headless con `teatest`

Para verificar la lógica de la TUI en pipelines de CI sin requerir una pseudo-terminal (PTY) interactiva:

```go
func TestTUI_KeyboardNavigation(t *testing.T) {
    m := NewModel(fakeService)
    tm := teatest.NewTestModel(t, m)

    // Enviar teclas simuladas
    tm.Send(tea.KeyMsg{Type: tea.KeyDown})
    tm.Send(tea.KeyMsg{Type: tea.KeyEnter})

    // Esperar condición en la vista
    teatest.WaitFor(t, tm.Output(), func(out []byte) bool {
        return strings.Contains(string(out), "Item Seleccionado")
    })

    tm.Send(tea.KeyMsg{Type: tea.KeyCtrlC})
    tm.WaitFinished(t, teatest.WithFinalTimeout(time.Second))
}
```
