"""Error de comando con código registrado, mensaje, pista y salida (contrato de errores de `plane-tracker/1`).

Expone: CliError (con to_dict() y render()).
No hace: terminar el programa ni imprimir; solo `cli.main()` captura un CliError y decide (fase 7).
El código de salida sale del registro (vocabulary.ERRORS); un código no registrado es un defecto del programa y lanza ValueError.
"""

from plane_cli import vocabulary


class CliError(Exception):
    def __init__(self, code, message, hint=None, exit_code=None, detail=None):
        if code not in vocabulary.ERRORS:
            raise ValueError(f"código de error no registrado: {code}")
        super().__init__(message)
        self.code, self.message, self.hint, self.detail = code, message, hint, detail
        self.exit_code = vocabulary.ERRORS[code] if exit_code is None else exit_code

    def to_dict(self):
        """Sobre de error de `--json` (sale por stdout con el código de salida correspondiente)."""
        doc = {"schema": vocabulary.SCHEMA, "status": "error", "code": self.code, "message": self.message, "exit": self.exit_code}
        if self.hint:
            doc["hint"] = self.hint
        if self.detail:
            doc["detail"] = self.detail
        return doc

    def render(self):
        """Texto para stderr: el mensaje y, si lo hay, la pista en otra línea."""
        return self.message + (f"\n{self.hint}" if self.hint else "")
