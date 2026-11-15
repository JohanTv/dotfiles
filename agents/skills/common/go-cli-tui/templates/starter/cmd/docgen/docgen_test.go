package main

import (
	"os"
	"path/filepath"
	"testing"
)

func TestDocs_ConventionsAndMetadata(t *testing.T) {
	docsDir := "../../docs"
	if _, err := os.Stat(docsDir); os.IsNotExist(err) {
		docsDir = "docs"
	}
	items, errs := CollectDocs(docsDir)
	if len(errs) > 0 {
		for _, e := range errs {
			t.Errorf("error de convención documental: %s", e)
		}
	}
	if len(items) == 0 {
		t.Logf("aviso: 0 documentos encontrados en %s", docsDir)
	}
}

func TestDocs_RelativeLinks(t *testing.T) {
	docsDir := "../../docs"
	if _, err := os.Stat(docsDir); os.IsNotExist(err) {
		docsDir = "docs"
	}
	errs := CheckRelativeLinks(docsDir)
	if len(errs) > 0 {
		for _, e := range errs {
			t.Errorf("enlace roto o inválido: %s", e)
		}
	}
}

func TestDocs_IndexIsUpToDate(t *testing.T) {
	docsDir := "../../docs"
	if _, err := os.Stat(docsDir); os.IsNotExist(err) {
		docsDir = "docs"
	}
	items, errs := CollectDocs(docsDir)
	if len(errs) > 0 {
		t.Fatalf("no se puede validar el índice debido a errores en documentos: %v", errs)
	}

	expected := RenderIndex(items)
	indexPath := filepath.Join(docsDir, "INDEX.md")
	data, err := os.ReadFile(indexPath)
	if err != nil {
		t.Fatalf("no se pudo leer %s: %v", indexPath, err)
	}

	if string(data) != expected {
		t.Errorf("el archivo %s está desactualizado. Ejecuta 'make docs' para regenerarlo", indexPath)
	}
}
