package main

import (
	"bytes"
	"flag"
	"fmt"
	"os"
	"path/filepath"
	"regexp"
	"sort"
	"strconv"
	"strings"
	"time"
)

var (
	filePattern  = regexp.MustCompile(`^(\d{4})-[a-z0-9]+(-[a-z0-9]+)*\.md$`)
	datePattern  = regexp.MustCompile(`^\d{4}-\d{2}-\d{2}$`)
	linkPattern  = regexp.MustCompile(`\[([^\]]*)\]\(([^)]*)\)`)
	requiredKeys = []string{"id", "title", "status", "created", "summary"}

	validStatuses = map[string]map[string]bool{
		"decisions": {
			"proposed":   true,
			"accepted":   true,
			"deprecated": true,
			"superseded": true,
		},
		"rfcs": {
			"draft":       true,
			"proposed":    true,
			"accepted":    true,
			"implemented": true,
			"rejected":    true,
		},
	}
)

type DocItem struct {
	ID        string
	Title     string
	Status    string
	Created   string
	Summary   string
	Path      string
	RelPath   string
	Kind      string
	NumericID int
}

func ParseFrontMatter(content string) (map[string]string, error) {
	if !strings.HasPrefix(content, "---\n") {
		return nil, fmt.Errorf("front-matter ausente o no inicia con '---'")
	}
	endIdx := strings.Index(content[4:], "\n---\n")
	if endIdx == -1 {
		return nil, fmt.Errorf("delimitador de cierre '---' no encontrado")
	}
	rawYAML := content[4 : 4+endIdx]
	meta := make(map[string]string)
	lines := strings.Split(rawYAML, "\n")
	for _, line := range lines {
		line = strings.TrimSpace(line)
		if line == "" || strings.HasPrefix(line, "#") {
			continue
		}
		parts := strings.SplitN(line, ":", 2)
		if len(parts) == 2 {
			k := strings.TrimSpace(parts[0])
			v := strings.TrimSpace(parts[1])
			v = strings.Trim(v, `"'`)
			meta[k] = v
		}
	}
	return meta, nil
}

func FindDocsRoot(docsDir string) string {
	absDocs, err := filepath.Abs(docsDir)
	if err != nil {
		absDocs = docsDir
	}
	curr := absDocs
	for {
		if _, err := os.Stat(filepath.Join(curr, "go.mod")); err == nil {
			return curr
		}
		parent := filepath.Dir(curr)
		if parent == curr {
			break
		}
		curr = parent
	}
	if filepath.Base(absDocs) == "docs" {
		return filepath.Dir(absDocs)
	}
	return absDocs
}

func CollectDocs(docsDir string) ([]DocItem, []string) {
	var items []DocItem
	var errs []string
	seenIDs := make(map[string]string)

	kinds := []string{"decisions", "rfcs"}
	for _, kind := range kinds {
		dir := filepath.Join(docsDir, kind)
		if _, err := os.Stat(dir); os.IsNotExist(err) {
			continue
		}

		entries, err := os.ReadDir(dir)
		if err != nil {
			errs = append(errs, fmt.Sprintf("error leyendo directorio %s: %v", dir, err))
			continue
		}

		for _, entry := range entries {
			if entry.IsDir() || !strings.HasSuffix(entry.Name(), ".md") {
				continue
			}

			relPath := filepath.Join(kind, entry.Name())
			filePath := filepath.Join(dir, entry.Name())

			matches := filePattern.FindStringSubmatch(entry.Name())
			if matches == nil {
				errs = append(errs, fmt.Sprintf("%s: nombre de archivo inválido (debe cumplir NNNN-kebab-slug.md con 4 dígitos)", relPath))
				continue
			}
			filePrefixID := matches[1]

			data, err := os.ReadFile(filePath)
			if err != nil {
				errs = append(errs, fmt.Sprintf("%s: error leyendo archivo: %v", relPath, err))
				continue
			}

			meta, err := ParseFrontMatter(string(data))
			if err != nil {
				errs = append(errs, fmt.Sprintf("%s: front-matter inválido: %v", relPath, err))
				continue
			}

			for _, key := range requiredKeys {
				if val, ok := meta[key]; !ok || strings.TrimSpace(val) == "" {
					errs = append(errs, fmt.Sprintf("%s: campo obligatorio faltante o vacío en front-matter: '%s'", relPath, key))
				}
			}

			if meta["id"] != filePrefixID {
				errs = append(errs, fmt.Sprintf("%s: discrepancia de ID: front-matter '%s' != prefijo archivo '%s'", relPath, meta["id"], filePrefixID))
			}

			if prevPath, exists := seenIDs[meta["id"]]; exists {
				errs = append(errs, fmt.Sprintf("%s: ID duplicado '%s' (ya utilizado en %s)", relPath, meta["id"], prevPath))
			} else {
				seenIDs[meta["id"]] = relPath
			}

			if !datePattern.MatchString(meta["created"]) {
				errs = append(errs, fmt.Sprintf("%s: 'created' (%s) no tiene formato YYYY-MM-DD", relPath, meta["created"]))
			} else if _, err := time.Parse("2006-01-02", meta["created"]); err != nil {
				errs = append(errs, fmt.Sprintf("%s: 'created' (%s) no es una fecha válida de calendario: %v", relPath, meta["created"], err))
			}

			allowedStatuses, ok := validStatuses[kind]
			if !ok || !allowedStatuses[meta["status"]] {
				errs = append(errs, fmt.Sprintf("%s: estado inválido '%s' para categoría '%s'", relPath, meta["status"], kind))
			}

			numID, _ := strconv.Atoi(filePrefixID)

			items = append(items, DocItem{
				ID:        filePrefixID,
				Title:     meta["title"],
				Status:    meta["status"],
				Created:   meta["created"],
				Summary:   meta["summary"],
				Path:      filePath,
				RelPath:   relPath,
				Kind:      kind,
				NumericID: numID,
			})
		}
	}

	sort.Slice(items, func(i, j int) bool {
		return items[i].NumericID < items[j].NumericID
	})

	return items, errs
}

func CheckRelativeLinks(docsDir string) []string {
	var errs []string
	repoRoot := FindDocsRoot(docsDir)

	err := filepath.Walk(docsDir, func(path string, info os.FileInfo, err error) error {
		if err != nil {
			return err
		}
		if info.IsDir() || !strings.HasSuffix(info.Name(), ".md") {
			return nil
		}

		data, err := os.ReadFile(path)
		if err != nil {
			return err
		}

		relFile, _ := filepath.Rel(docsDir, path)
		matches := linkPattern.FindAllStringSubmatch(string(data), -1)
		for _, m := range matches {
			if len(m) < 3 {
				continue
			}
			rawTarget := strings.TrimSpace(m[2])
			if rawTarget == "" {
				errs = append(errs, fmt.Sprintf("%s: enlace vacío '[]()'", relFile))
				continue
			}

			if strings.HasPrefix(rawTarget, "http://") || strings.HasPrefix(rawTarget, "https://") ||
				strings.HasPrefix(rawTarget, "mailto:") {
				continue
			}

			if strings.HasPrefix(rawTarget, "file://") {
				errs = append(errs, fmt.Sprintf("%s: enlace absoluto 'file://' no portable: %s", relFile, rawTarget))
				continue
			}

			if strings.HasPrefix(rawTarget, "/") {
				errs = append(errs, fmt.Sprintf("%s: enlace absoluto con '/' no permitido (usa rutas relativas): %s", relFile, rawTarget))
				continue
			}

			targetFile := rawTarget
			if strings.Contains(rawTarget, "#") {
				parts := strings.Split(rawTarget, "#")
				if len(parts) > 2 {
					errs = append(errs, fmt.Sprintf("%s: ancla malformada (múltiples '#'): '%s'", relFile, rawTarget))
					continue
				}
				targetFile = parts[0]
				anchor := parts[1]
				if anchor == "" {
					errs = append(errs, fmt.Sprintf("%s: ancla vacía en enlace: '%s'", relFile, rawTarget))
					continue
				}
				if targetFile == "" {
					continue
				}
			}

			resolved := filepath.Clean(filepath.Join(filepath.Dir(path), targetFile))
			absResolved, err := filepath.Abs(resolved)
			if err != nil {
				absResolved = resolved
			}

			relToRoot, err := filepath.Rel(repoRoot, absResolved)
			if err != nil || strings.HasPrefix(relToRoot, "..") {
				errs = append(errs, fmt.Sprintf("%s: enlace fuera del repositorio no permitido: %s", relFile, targetFile))
				continue
			}

			if _, err := os.Stat(resolved); err != nil {
				errs = append(errs, fmt.Sprintf("%s: enlace roto a '%s' (no existe: %s)", relFile, targetFile, resolved))
			}
		}

		return nil
	})

	if err != nil {
		errs = append(errs, fmt.Sprintf("error explorando docsDir: %v", err))
	}
	return errs
}

func RenderIndex(items []DocItem) string {
	var buf bytes.Buffer
	buf.WriteString("<!-- AUTO-GENERATED BY cmd/docgen - DO NOT EDIT DIRECTLY -->\n")
	buf.WriteString("# Índice Canónico de Decisiones de Arquitectura y RFCs\n\n")
	buf.WriteString("Este documento es generado de forma determinista por `cmd/docgen` a partir de los metadatos YAML en `docs/decisions/` y `docs/rfcs/`.\n\n")

	buf.WriteString("## Decisiones de Arquitectura (ADRs)\n\n")
	buf.WriteString("| ID | Título | Estado | Resumen |\n")
	buf.WriteString("| :--- | :--- | :---: | :--- |\n")
	for _, item := range items {
		if item.Kind == "decisions" {
			title := strings.ReplaceAll(item.Title, "|", "\\|")
			title = strings.ReplaceAll(title, "\n", " ")
			summary := strings.ReplaceAll(item.Summary, "|", "\\|")
			summary = strings.ReplaceAll(summary, "\n", " ")
			buf.WriteString(fmt.Sprintf("| **%s** | [%s](%s) | %s | %s |\n",
				item.ID, title, item.RelPath, item.Status, summary))
		}
	}

	buf.WriteString("\n## Solicitudes de Cambio y Propuestas Técnicas (RFCs)\n\n")
	buf.WriteString("| ID | Título | Estado | Resumen |\n")
	buf.WriteString("| :--- | :--- | :---: | :--- |\n")
	for _, item := range items {
		if item.Kind == "rfcs" {
			title := strings.ReplaceAll(item.Title, "|", "\\|")
			title = strings.ReplaceAll(title, "\n", " ")
			summary := strings.ReplaceAll(item.Summary, "|", "\\|")
			summary = strings.ReplaceAll(summary, "\n", " ")
			buf.WriteString(fmt.Sprintf("| **%s** | [%s](%s) | %s | %s |\n",
				item.ID, title, item.RelPath, item.Status, summary))
		}
	}

	buf.WriteString("\n---\n*Para añadir una nueva entrada, utiliza `go run ./cmd/docgen --new [rfc|decision] <slug> --title \"...\"`.*\n")
	return buf.String()
}

func NextAvailableID(items []DocItem) int {
	maxID := 0
	for _, item := range items {
		if item.NumericID > maxID {
			maxID = item.NumericID
		}
	}
	return maxID + 1
}

func CreateDocScaffold(docsDir, kind, slug, title string) (string, error) {
	if kind != "decisions" && kind != "rfcs" {
		return "", fmt.Errorf("tipo de documento inválido '%s': debe ser 'decisions' o 'rfcs'", kind)
	}

	trimmedTitle := strings.TrimSpace(title)
	if trimmedTitle == "" {
		return "", fmt.Errorf("el título no puede estar vacío")
	}

	cleanSlug := strings.ToLower(strings.TrimSpace(slug))
	cleanSlug = strings.ReplaceAll(cleanSlug, " ", "-")
	if cleanSlug == "" {
		return "", fmt.Errorf("el slug no puede estar vacío")
	}

	items, docErrs := CollectDocs(docsDir)
	if len(docErrs) > 0 {
		return "", fmt.Errorf("no se puede crear scaffold porque existen documentos con errores: %s", strings.Join(docErrs, "; "))
	}

	nextID := NextAvailableID(items)
	idStr := fmt.Sprintf("%04d", nextID)

	filename := fmt.Sprintf("%s-%s.md", idStr, cleanSlug)
	if !filePattern.MatchString(filename) {
		return "", fmt.Errorf("el slug '%s' genera un nombre de archivo inválido '%s'", slug, filename)
	}

	targetDir := filepath.Join(docsDir, kind)
	filePath := filepath.Join(targetDir, filename)

	if err := os.MkdirAll(targetDir, 0755); err != nil {
		return "", err
	}

	today := time.Now().Format("2006-01-02")
	content := fmt.Sprintf(`---
id: "%s"
title: "%s"
status: "%s"
created: "%s"
summary: "Resumen conciso del propósito técnico y justificación."
---

# %s · %s

## Contexto

Describe el problema, motivación técnica y el estado previo del sistema.

## Decisión / Propuesta

Detalla los cambios arquitecturales, interfaces y contratos.

## Consecuencias

- Consecuencias positivas o simplificaciones operativas.
- Riesgos mitigados o compensaciones técnicas.
`, idStr, trimmedTitle, map[string]string{"decisions": "accepted", "rfcs": "proposed"}[kind], today, idStr, trimmedTitle)

	if err := os.WriteFile(filePath, []byte(content), 0644); err != nil {
		return "", err
	}

	return filePath, nil
}

func main() {
	checkOnly := flag.Bool("check", false, "Verifica el estado del índice y enlaces sin modificar archivos")
	nextIDOnly := flag.Bool("next-id", false, "Calcula e imprime el siguiente ID secuencial disponible")
	newKind := flag.String("new", "", "Tipo de scaffold a crear ('decision' o 'rfc')")
	newTitle := flag.String("title", "", "Título descriptivo para el nuevo scaffold")
	docsPath := flag.String("docs", "docs", "Ruta al directorio de documentación")
	flag.Parse()

	if *nextIDOnly {
		items, _ := CollectDocs(*docsPath)
		fmt.Printf("%04d\n", NextAvailableID(items))
		return
	}

	if *newKind != "" {
		kind := *newKind
		if kind == "decision" {
			kind = "decisions"
		} else if kind == "rfc" {
			kind = "rfcs"
		}
		args := flag.Args()
		if len(args) < 1 {
			fmt.Fprintf(os.Stderr, "Error: debes especificar un slug (ej: go run ./cmd/docgen --new rfc <slug> --title \"...\")\n")
			os.Exit(1)
		}
		slug := args[0]
		title := *newTitle
		if title == "" {
			title = strings.ReplaceAll(slug, "-", " ")
			title = strings.Title(title)
		}

		filePath, err := CreateDocScaffold(*docsPath, kind, slug, title)
		if err != nil {
			fmt.Fprintf(os.Stderr, "Error creando scaffold: %v\n", err)
			os.Exit(1)
		}
		fmt.Printf("✔ Documento creado: %s\n", filePath)

		items, _ := CollectDocs(*docsPath)
		rendered := RenderIndex(items)
		_ = os.WriteFile(filepath.Join(*docsPath, "INDEX.md"), []byte(rendered), 0644)
		fmt.Printf("✔ Índice docs/INDEX.md actualizado.\n")
		return
	}

	items, docErrors := CollectDocs(*docsPath)
	linkErrors := CheckRelativeLinks(*docsPath)
	allErrors := append(docErrors, linkErrors...)

	if len(allErrors) > 0 {
		fmt.Fprintf(os.Stderr, "✖ Errores detectados en la documentación (%d):\n", len(allErrors))
		for _, e := range allErrors {
			fmt.Fprintf(os.Stderr, "  - %s\n", e)
		}
		os.Exit(1)
	}

	expectedIndex := RenderIndex(items)
	indexPath := filepath.Join(*docsPath, "INDEX.md")

	if *checkOnly {
		currentBytes, err := os.ReadFile(indexPath)
		if err != nil {
			fmt.Fprintf(os.Stderr, "✖ No se pudo leer %s: %v\n", indexPath, err)
			os.Exit(1)
		}
		if string(currentBytes) != expectedIndex {
			fmt.Fprintf(os.Stderr, "✖ %s está desactualizado. Ejecuta 'make docs' para regenerarlo.\n", indexPath)
			os.Exit(1)
		}
		fmt.Println("✔ Todos los documentos, enlaces e índice están en perfecto estado de consistencia.")
		return
	}

	if err := os.WriteFile(indexPath, []byte(expectedIndex), 0644); err != nil {
		fmt.Fprintf(os.Stderr, "Error escribiendo %s: %v\n", indexPath, err)
		os.Exit(1)
	}

	fmt.Printf("✔ Índice generado exitosamente en %s (%d entradas indexadas).\n", indexPath, len(items))
}
