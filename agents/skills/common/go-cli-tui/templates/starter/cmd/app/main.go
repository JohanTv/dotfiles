package main

import (
	"context"
	"fmt"
	"os"
	"os/signal"
	"syscall"

	"github.com/spf13/cobra"
	"golang.org/x/term"

	"{{ .ModulePath }}/internal/bootstrap"
	"{{ .ModulePath }}/internal/presentation/errors"
)

var (
	Version = "dev"
	Commit  = "none"
	Date    = "unknown"

	jsonFlag bool
)

func newRootCmd(app *bootstrap.Application) *cobra.Command {
	rootCmd := &cobra.Command{
		Use:     "{{ .AppName }}",
		Short:   "{{ .AppTitle }} - {{ .Description }}",
		Version: Version,
		RunE: func(cmd *cobra.Command, args []string) error {
			ctx := cmd.Context()
			isTTY := term.IsTerminal(int(os.Stdout.Fd()))

			// Cortafuegos de Terminal: Si se solicita JSON o no es TTY, no tocar Bubble Tea
			if jsonFlag || !isTTY {
				items, err := app.ItemService.ListItems(ctx)
				if err != nil {
					return err
				}
				if jsonFlag {
					return app.JSONPresenter.RenderSuccess(items)
				}
				return app.PlainPresenter.RenderItems(items)
			}

			// Modo interactivo para humanos
			return app.TUIPresenter.Launch(ctx)
		},
	}

	rootCmd.PersistentFlags().BoolVar(&jsonFlag, "json", false, "Salida estructurada en JSON para agentes y pipelines")

	// Subcomandos canónicos
	rootCmd.AddCommand(newListCmd(app))

	return rootCmd
}

func newListCmd(app *bootstrap.Application) *cobra.Command {
	return &cobra.Command{
		Use:   "list",
		Short: "Lista los elementos registrados",
		RunE: func(cmd *cobra.Command, args []string) error {
			items, err := app.ItemService.ListItems(cmd.Context())
			if err != nil {
				return err
			}
			if jsonFlag {
				return app.JSONPresenter.RenderSuccess(items)
			}
			return app.PlainPresenter.RenderItems(items)
		},
	}
}

func main() {
	// Detectar flag --json en os.Args para silenciar stderr en caso de fallos de sintaxis Cobra
	isJSON := false
	for _, arg := range os.Args {
		if arg == "--json" {
			isJSON = true
			break
		}
	}

	errors.SafeExecute(isJSON, func() error {
		ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
		defer stop()

		app, cleanup, err := bootstrap.Initialize(ctx)
		if err != nil {
			errors.EmitError(
				err,
				errors.ErrorDetail{
					Code:        "INITIALIZATION_ERROR",
					Category:    errors.CategoryInternal,
					Message:     fmt.Sprintf("Fallo al inicializar el entorno: %v", err),
					Recoverable: false,
				},
				errors.ExitGeneralError,
				isJSON,
			)
			return err
		}
		defer cleanup()

		rootCmd := newRootCmd(app)
		if isJSON {
			rootCmd.SilenceErrors = true
			rootCmd.SilenceUsage = true
		}

		if err := rootCmd.ExecuteContext(ctx); err != nil {
			errors.EmitError(
				err,
				errors.ErrorDetail{
					Code:        "COMMAND_EXECUTION_ERROR",
					Category:    errors.CategoryUserInput,
					Message:     err.Error(),
					Recoverable: true,
				},
				errors.ExitUsageError,
				isJSON,
			)
			return err
		}
		return nil
	})
}
