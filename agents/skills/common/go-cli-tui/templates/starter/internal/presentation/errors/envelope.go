package errors

import (
	"encoding/json"
	"fmt"
	"os"
)

type ErrorCategory string

const (
	CategoryUserInput       ErrorCategory = "user_input"
	CategoryStateConflict   ErrorCategory = "state_conflict"
	CategoryAuth            ErrorCategory = "auth"
	CategoryUpstreamService ErrorCategory = "upstream_service"
	CategoryInternal        ErrorCategory = "internal"
)

// Códigos POSIX semánticos
const (
	ExitSuccess        = 0
	ExitGeneralError   = 1
	ExitUsageError     = 2
	ExitAuthError      = 3
	ExitNotFound       = 4
	ExitTransientError = 5
	ExitSoftwareError  = 70 // EX_SOFTWARE
)

type ErrorDetail struct {
	Code             string                 `json:"code"`
	Category         ErrorCategory          `json:"category"`
	Message          string                 `json:"message"`
	Target           string                 `json:"target,omitempty"`
	Hint             string                 `json:"hint,omitempty"`
	SuggestedCommand string                 `json:"suggested_command,omitempty"`
	Recoverable      bool                   `json:"recoverable"`
	Context          map[string]interface{} `json:"context,omitempty"`
}

type ResponseEnvelope struct {
	OK    bool         `json:"ok"`
	Error *ErrorDetail `json:"error,omitempty"`
	Data  interface{}  `json:"data,omitempty"`
}

func EmitError(err error, detail ErrorDetail, exitCode int, jsonMode bool) {
	if exitCode == 0 {
		exitCode = ExitGeneralError
	}
	if detail.Code == "" {
		detail.Code = "EXECUTION_ERROR"
	}
	if detail.Category == "" {
		detail.Category = CategoryUserInput
	}
	if detail.Message == "" && err != nil {
		detail.Message = err.Error()
	}

	if jsonMode {
		env := ResponseEnvelope{
			OK:    false,
			Error: &detail,
		}
		enc := json.NewEncoder(os.Stdout)
		enc.SetIndent("", "  ")
		_ = enc.Encode(env)
		os.Exit(exitCode)
	}

	fmt.Fprintf(os.Stderr, "✖ Error [%s]: %s\n", detail.Code, detail.Message)
	if detail.Hint != "" {
		fmt.Fprintf(os.Stderr, "💡 Sugerencia: %s\n", detail.Hint)
	}
	if detail.SuggestedCommand != "" {
		fmt.Fprintf(os.Stderr, "👉 Ejecuta: %s\n", detail.SuggestedCommand)
	}
	os.Exit(exitCode)
}

func SafeExecute(jsonMode bool, fn func() error) {
	defer func() {
		if r := recover(); r != nil {
			EmitError(
				fmt.Errorf("%v", r),
				ErrorDetail{
					Code:        "INTERNAL_PANIC",
					Category:    CategoryInternal,
					Message:     fmt.Sprintf("Panic recuperado: %v", r),
					Hint:        "Error inesperado en runtime. Reporta este incidente.",
					Recoverable: false,
				},
				ExitSoftwareError,
				jsonMode,
			)
		}
	}()

	if err := fn(); err != nil {
		// El error ya fue gestionado en el comando o fn
	}
}
