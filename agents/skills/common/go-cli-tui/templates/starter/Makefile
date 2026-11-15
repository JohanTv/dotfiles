APP_NAME ?= {{ .AppName }}
BIN_DIR  := bin
BINARY   := $(BIN_DIR)/$(APP_NAME)
PREFIX   ?= $(HOME)/.local/bin

VERSION := $(shell git describe --tags --always --dirty 2>/dev/null || echo "v0.1.0-dev")
COMMIT  := $(shell git rev-parse --short HEAD 2>/dev/null || echo "none")
DATE    := $(shell date -u +"%Y-%m-%dT%H:%M:%SZ")

LDFLAGS := -X main.Version=$(VERSION) -X main.Commit=$(COMMIT) -X main.Date=$(DATE)

.PHONY: all build test docs docs-check clean install check

all: build docs-check test

build:
	@mkdir -p $(BIN_DIR)
	CGO_ENABLED=0 go build -trimpath -ldflags "$(LDFLAGS)" -o $(BINARY) ./cmd/$(APP_NAME)
	@echo "✔ Binario compilado en $(BINARY)"

test:
	go test -race -v ./...

docs:
	@go run ./cmd/docgen
	@echo "✔ Documentación e índice regenerados."

docs-check:
	@go run ./cmd/docgen --check
	@echo "✔ Documentación consistente y sin enlaces rotos."

check: docs-check test

install: build
	@mkdir -p $(PREFIX)
	@install -m 755 $(BINARY) $(PREFIX)/$(APP_NAME)
	@echo "✔ Instalado en $(PREFIX)/$(APP_NAME)"

clean:
	@rm -rf $(BIN_DIR)
	@echo "✔ Limpieza completada."
