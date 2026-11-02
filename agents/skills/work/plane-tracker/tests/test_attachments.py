"""Pruebas unitarias de adjuntos: validación client-side de extensiones no permitidas y manejo de respuestas HTTP de Plane."""
import io
import os
import tempfile
import unittest
from unittest import mock
import urllib.error

import sys
sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from plane_cli import attachments
from plane_cli.errors import CliError
from plane_cli import cmd_tickets_write as ctw


class TestValidateAttachmentPaths(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp_dir.cleanup()

    def _create_file(self, filename, content=b"contenido de prueba"):
        path = os.path.join(self.tmp_dir.name, filename)
        with open(path, "wb") as handle:
            handle.write(content)
        return path

    def test_valid_files_pass_validation(self):
        p1 = self._create_file("nota.txt")
        p2 = self._create_file("documento.pdf")
        p3 = self._create_file("guia.md")
        attachments.validate_attachment_paths([p1, p2, p3])

    def test_missing_file_raises_not_found(self):
        missing = os.path.join(self.tmp_dir.name, "no_existe.txt")
        with self.assertRaises(CliError) as ctx:
            attachments.validate_attachment_paths([missing])
        self.assertEqual(ctx.exception.code, "not_found")
        self.assertIn("no es un archivo", ctx.exception.message)

    def test_oversized_file_raises_invalid_input(self):
        large = self._create_file("grande.bin")
        with mock.patch("os.path.getsize", return_value=attachments.ATTACH_MAX_BYTES + 1):
            with self.assertRaises(CliError) as ctx:
                attachments.validate_attachment_paths([large])
            self.assertEqual(ctx.exception.code, "invalid_input")
            self.assertIn("supera 50 MB", ctx.exception.message)

    def test_sql_extension_rejected_client_side(self):
        sql_file = self._create_file("migracion.sql")
        with self.assertRaises(CliError) as ctx:
            attachments.validate_attachment_paths([sql_file])
        self.assertEqual(ctx.exception.code, "invalid_input")
        self.assertIn(".sql", ctx.exception.message)
        self.assertIn("extensión no admitida", ctx.exception.message)
        self.assertIsNotNone(ctx.exception.hint)
        self.assertIn(".txt", ctx.exception.hint)
        self.assertIn(".md", ctx.exception.hint)

    def test_sql_extension_case_insensitive(self):
        for name in ("schema.SQL", "backup.Sql", "script.sQl"):
            f = self._create_file(name)
            with self.assertRaises(CliError) as ctx:
                attachments.validate_attachment_paths([f])
            self.assertEqual(ctx.exception.code, "invalid_input")
            self.assertIn(".sql", ctx.exception.message)
            self.assertIn(".txt", ctx.exception.hint)


class TestUploadAttachment(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.file_path = os.path.join(self.tmp_dir.name, "prueba.dat")
        with open(self.file_path, "wb") as handle:
            handle.write(b"12345")

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_server_invalid_file_type_converted_to_friendly_clierror(self):
        err = urllib.error.HTTPError(
            "http://plane/api/v1/.../issue-attachments/",
            400,
            "Bad Request",
            {},
            io.BytesIO(b'{"error":"Invalid file type.","status":false}'),
        )
        with mock.patch("plane_cli.attachments.api_request", side_effect=err):
            with self.assertRaises(CliError) as ctx:
                attachments.upload_attachment("http://plane", "api-key", "ws", "p1", "i1", self.file_path)
            self.assertEqual(ctx.exception.code, "invalid_input")
            self.assertIn("tipo de archivo no permitido", ctx.exception.message)
            self.assertIn(".txt", ctx.exception.hint)
            self.assertIn(".md", ctx.exception.hint)

    def test_server_other_http_error_calls_fail_http(self):
        err = urllib.error.HTTPError(
            "http://plane/api/v1/.../issue-attachments/",
            500,
            "Internal Server Error",
            {},
            io.BytesIO(b'{"detail":"internal crash"}'),
        )
        with mock.patch("plane_cli.attachments.api_request", side_effect=err):
            with self.assertRaises(CliError) as ctx:
                attachments.upload_attachment("http://plane", "api-key", "ws", "p1", "i1", self.file_path)
            self.assertEqual(ctx.exception.code, "http_error")
            self.assertIn("500", ctx.exception.message)

    def test_successful_upload_flow(self):
        def fake_api(url, *args, **kwargs):
            if kwargs.get("method") == "POST":
                return {
                    "asset_id": "asset-uuid-1",
                    "upload_data": {
                        "url": "http://storage/upload",
                        "fields": {"key": "val"},
                    },
                }
            if kwargs.get("method") == "PATCH":
                return {"is_uploaded": True}
            return {}

        mock_resp = mock.MagicMock()
        mock_resp.__enter__.return_value = mock_resp
        with mock.patch("plane_cli.attachments.api_request", side_effect=fake_api):
            with mock.patch("urllib.request.urlopen", return_value=mock_resp):
                name, size = attachments.upload_attachment("http://plane", "api-key", "ws", "p1", "i1", self.file_path)
                self.assertEqual(name, "prueba.dat")
                self.assertEqual(size, 5)


class TestCmdTicketsWriteAttachments(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp_dir.cleanup()

    def _create_file(self, filename):
        path = os.path.join(self.tmp_dir.name, filename)
        with open(path, "wb") as handle:
            handle.write(b"data")
        return path

    def test_create_with_sql_attachment_fails_before_submitting_issue(self):
        sql_file = self._create_file("test.sql")
        args = mock.MagicMock()
        args.title = "Test issue"
        args.attach = [sql_file]
        args.project = None
        args.state = None
        args.labels = None
        args.description = None
        args.priority = None
        args.start_date = None
        args.due_date = None

        with mock.patch("plane_cli.cmd_tickets_write.get_projects_map", return_value={"OMNIFY": {"id": "p1"}}):
            with mock.patch("plane_cli.cmd_tickets_write._submit_issue") as mock_submit:
                with self.assertRaises(CliError) as ctx:
                    ctw.cmd_create(args, None, "http://plane", "key", "ws", "p1")
                self.assertEqual(ctx.exception.code, "invalid_input")
                self.assertIn(".sql", ctx.exception.message)
                mock_submit.assert_not_called()

    def test_create_records_attachment_failure_without_aborting_created_ticket(self):
        txt_file = self._create_file("test.txt")
        args = mock.MagicMock()
        args.title = "Test issue"
        args.attach = [txt_file]
        args.project = None
        args.json = True
        args.priority = None
        args.start_date = None
        args.due_date = None
        args.state = None
        args.labels = None
        args.description = None

        with mock.patch("plane_cli.cmd_tickets_write.get_projects_map", return_value={"OMNIFY": {"id": "p1"}}):
            with mock.patch("plane_cli.cmd_tickets_write._submit_issue", return_value={"id": "iss-1", "name": "Test issue", "sequence_id": 10}):
                with mock.patch("plane_cli.cmd_tickets_write.upload_attachment", side_effect=CliError("invalid_input", "Rechazado", hint="Sugerencia")):
                    # No debe lanzar excepción; debe registrar el error en attachment_errors
                    with mock.patch("builtins.print") as mock_print:
                        ctw.cmd_create(args, None, "http://plane", "key", "ws", "p1")
                        printed = mock_print.call_args[0][0]
                        self.assertIn("attachment_errors", printed)
                        self.assertIn("Rechazado", printed)


if __name__ == "__main__":
    unittest.main()
