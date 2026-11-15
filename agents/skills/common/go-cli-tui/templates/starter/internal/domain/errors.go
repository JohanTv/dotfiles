package domain

import "errors"

var (
	ErrNotFound = errors.New("recurso no encontrado")
	ErrConflict = errors.New("conflicto de estado")
)
