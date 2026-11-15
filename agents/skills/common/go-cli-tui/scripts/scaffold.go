package main

import (
	"bytes"
	"flag"
	"fmt"
	"io/fs"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
)

type Config struct {
	AppName     string
	AppTitle    string
	ModulePath  string
	Description string
	TargetDir   string
	Minimal     bool
}

func main() {
	appName := flag.String("name", "", "Nombre de la aplicación (ej: mytool)")
	modulePath := flag.String("module", "", "Ruta del módulo Go (ej: github.com/user/mytool)")
	targetDir := flag.String("target", "", "Directorio de destino (por defecto: ./<name>)")
	appTitle := flag.String("title", "", "Título legible de la aplicación")
	desc := flag.String("description", "Herramienta moderna CLI/TUI construida en Go", "Descripción concisa de la aplicación")
	minimal := flag.Bool("minimal", false, "Modo minimalista: solo Core Hexagonal + Headless CLI (omite TUI)")
	flag.Parse()

	if *appName == "" || *modulePath == "" {
		fmt.Fprintf(os.Stderr, "Uso: go run scaffold.go --name <nombre> --module <go-module-path> [--target <dir>] [--description <desc>]\n")
		os.Exit(1)
	}

	cleanName := strings.ToLower(strings.TrimSpace(*appName))
	title := *appTitle
	if title == "" {
		title = strings.Title(cleanName)
	}

	target := *targetDir
	if target == "" {
		target = filepath.Join(".", cleanName)
	}
	absTarget, err := filepath.Abs(target)
	if err != nil {
		fmt.Fprintf(os.Stderr, "Error resolviendo ruta destino: %v\n", err)
		os.Exit(1)
	}

	cfg := Config{
		AppName:     cleanName,
		AppTitle:    title,
		ModulePath:  strings.TrimSpace(*modulePath),
		Description: strings.TrimSpace(*desc),
		TargetDir:   absTarget,
		Minimal:     *minimal,
	}

	// Localizar el directorio templates/starter respecto al script o symlink
	execPath, err := os.Executable()
	if err != nil {
		execPath = "."
	}
	baseDir := filepath.Dir(execPath)
	starterDir := filepath.Join(baseDir, "..", "templates", "starter")
	if _, err := os.Stat(starterDir); os.IsNotExist(err) {
		// Fallback para ejecución con 'go run'
		wd, _ := os.Getwd()
		starterDir = filepath.Join(wd, "templates", "starter")
		if _, err := os.Stat(starterDir); os.IsNotExist(err) {
			// Intentar desde la ruta de dotfiles
			home, _ := os.UserHomeDir()
			starterDir = filepath.Join(home, "Code", "dotfiles", "agents", "skills", "common", "go-cli-tui", "templates", "starter")
		}
	}

	if _, err := os.Stat(starterDir); os.IsNotExist(err) {
		fmt.Fprintf(os.Stderr, "Error: No se encontró el directorio de plantillas en %s\n", starterDir)
		os.Exit(1)
	}

	fmt.Printf("🚀 Inicializando proyecto '%s' en %s...\n", cfg.AppName, cfg.TargetDir)

	if err := os.MkdirAll(cfg.TargetDir, 0755); err != nil {
		fmt.Fprintf(os.Stderr, "Error creando directorio destino: %v\n", err)
		os.Exit(1)
	}

	// Copiar y renderizar plantilla
	err = filepath.Walk(starterDir, func(path string, info fs.FileInfo, err error) error {
		if err != nil {
			return err
		}
		if info.IsDir() {
			return nil
		}

		relPath, err := filepath.Rel(starterDir, path)
		if err != nil {
			return err
		}

		// Reemplazar nombre dinámico de cmd/app por cmd/<appName>
		targetRelPath := relPath
		if strings.HasPrefix(targetRelPath, filepath.Join("cmd", "app")) {
			targetRelPath = filepath.Join("cmd", cfg.AppName, strings.TrimPrefix(targetRelPath, filepath.Join("cmd", "app")))
		}

		destPath := filepath.Join(cfg.TargetDir, targetRelPath)
		if err := os.MkdirAll(filepath.Dir(destPath), 0755); err != nil {
			return err
		}

		data, err := os.ReadFile(path)
		if err != nil {
			return err
		}

		// Reemplazo atómico de placeholders
		content := string(data)
		content = strings.ReplaceAll(content, "{{ .ModulePath }}", cfg.ModulePath)
		content = strings.ReplaceAll(content, "{{ .AppName }}", cfg.AppName)
		content = strings.ReplaceAll(content, "{{ .AppTitle }}", cfg.AppTitle)
		content = strings.ReplaceAll(content, "{{ .Description }}", cfg.Description)

		return os.WriteFile(destPath, []byte(content), info.Mode())
	})

	if err != nil {
		fmt.Fprintf(os.Stderr, "Error copiando plantillas: %v\n", err)
		os.Exit(1)
	}

	fmt.Println("✔ Estructura de carpetas y archivos base creada.")

	// Post-bootstrap: go mod tidy y make docs
	fmt.Println("📦 Resolviendo dependencias Go (go mod tidy)...")
	runCmd(cfg.TargetDir, "go", "mod", "tidy")

	fmt.Println("📑 Generando índice y validando documentación...")
	runCmd(cfg.TargetDir, "go", "run", "./cmd/docgen")

	fmt.Println("🧪 Ejecutando suite de pruebas inicial...")
	runCmd(cfg.TargetDir, "go", "test", "-race", "./...")

	fmt.Println("\n✨ ¡Proyecto inicializado con éxito!")
	fmt.Printf("👉 Para comenzar:\n")
	fmt.Printf("   cd %s\n", cfg.TargetDir)
	fmt.Printf("   make build\n")
	fmt.Printf("   bin/%s --help\n", cfg.AppName)
}

func runCmd(dir, name string, args ...string) {
	cmd := exec.Command(name, args...)
	cmd.Dir = dir
	var stderr bytes.Buffer
	cmd.Stderr = &stderr
	if err := cmd.Run(); err != nil {
		fmt.Printf("  ⚠ Aviso en '%s %s': %v\n  %s\n", name, strings.Join(args, " "), err, stderr.String())
	}
}
