"""Pruebas unitarias para `plane-worktree` (RFC 0002).

Verifica el comportamiento transaccional y atómico de la gestión multi-repo
de worktrees por ticket con Git real en directorios temporales aislados.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest


SCRIPT_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "..", "bin", "work", "plane-worktree")
)


def run_cmd(cmd, cwd=None):
    res = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    return res.returncode, res.stdout, res.stderr


class PlaneWorktreeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = self.tmp.name

        # 1. Crear remoto bare origin.git
        self.origin = os.path.join(self.root, "origin.git")
        run_cmd(["git", "init", "--bare", self.origin])

        # 2. Inicializar repo base temporal para empujar rama dev y staging al remoto
        seed = os.path.join(self.root, "seed")
        os.makedirs(seed, exist_ok=True)
        run_cmd(["git", "init", "-b", "main", seed])
        run_cmd(["git", "-C", seed, "config", "user.name", "Test User"])
        run_cmd(["git", "-C", seed, "config", "user.email", "test@example.com"])
        with open(os.path.join(seed, "README.md"), "w") as f:
            f.write("# seed\n")
        run_cmd(["git", "-C", seed, "add", "README.md"])
        run_cmd(["git", "-C", seed, "commit", "-m", "init"])
        run_cmd(["git", "-C", seed, "remote", "add", "origin", self.origin])
        run_cmd(["git", "-C", seed, "push", "origin", "main"])
        run_cmd(["git", "-C", seed, "checkout", "-b", "dev"])
        run_cmd(["git", "-C", seed, "push", "origin", "dev"])
        run_cmd(["git", "-C", seed, "checkout", "-b", "staging"])
        run_cmd(["git", "-C", seed, "push", "origin", "staging"])

        # 3. Clonar repo-a y repo-b desde origin
        self.repo_a = os.path.join(self.root, "repo-a")
        self.repo_b = os.path.join(self.root, "repo-b")
        run_cmd(["git", "clone", self.origin, self.repo_a])
        run_cmd(["git", "clone", self.origin, self.repo_b])
        for r in (self.repo_a, self.repo_b):
            run_cmd(["git", "-C", r, "config", "user.name", "Test User"])
            run_cmd(["git", "-C", r, "config", "user.email", "test@example.com"])

        self.wt_dir = os.path.join(self.root, ".worktrees")
        os.makedirs(self.wt_dir, exist_ok=True)

    def run_script(self, args, cwd=None):
        return run_cmd([sys.executable, SCRIPT_PATH] + args, cwd=cwd or self.root)

    def test_happy_path_multi_repo(self):
        code, out, err = self.run_script([
            "add", "OMNIFY-238", "operator-recovery",
            self.repo_a, self.repo_b,
            "--dir", self.wt_dir
        ])
        self.assertEqual(code, 0, f"Error: {err}")
        dest_parent = os.path.join(self.wt_dir, "OMNIFY-238-operator-recovery")
        self.assertTrue(os.path.isdir(dest_parent))

        # Verificar repo-a
        wt_a = os.path.join(dest_parent, "repo-a")
        self.assertTrue(os.path.isdir(wt_a))
        _, branch_a, _ = run_cmd(["git", "-C", wt_a, "branch", "--show-current"])
        self.assertEqual(branch_a.strip(), "feat/OMNIFY-238-operator-recovery")

        # Verificar repo-b
        wt_b = os.path.join(dest_parent, "repo-b")
        self.assertTrue(os.path.isdir(wt_b))
        _, branch_b, _ = run_cmd(["git", "-C", wt_b, "branch", "--show-current"])
        self.assertEqual(branch_b.strip(), "feat/OMNIFY-238-operator-recovery")

    def test_repo_slug_override(self):
        code, out, err = self.run_script([
            "add", "OMNIFY-238", "shared-desc",
            f"{self.repo_a}=custom-a", self.repo_b,
            "--dir", self.wt_dir
        ])
        self.assertEqual(code, 0, f"Error: {err}")
        dest_parent = os.path.join(self.wt_dir, "OMNIFY-238-shared-desc")

        wt_a = os.path.join(dest_parent, "repo-a")
        _, branch_a, _ = run_cmd(["git", "-C", wt_a, "branch", "--show-current"])
        self.assertEqual(branch_a.strip(), "feat/OMNIFY-238-custom-a")

        wt_b = os.path.join(dest_parent, "repo-b")
        _, branch_b, _ = run_cmd(["git", "-C", wt_b, "branch", "--show-current"])
        self.assertEqual(branch_b.strip(), "feat/OMNIFY-238-shared-desc")

    def test_custom_type_and_base(self):
        code, out, err = self.run_script([
            "add", "OPS-44", "hotfix-queue",
            self.repo_a,
            "--type", "fix",
            "--base", "staging",
            "--dir", self.wt_dir
        ])
        self.assertEqual(code, 0, f"Error: {err}")
        wt_a = os.path.join(self.wt_dir, "OPS-44-hotfix-queue", "repo-a")
        _, branch_a, _ = run_cmd(["git", "-C", wt_a, "branch", "--show-current"])
        self.assertEqual(branch_a.strip(), "fix/OPS-44-hotfix-queue")

    def test_idempotency(self):
        args = ["add", "OMNIFY-238", "operator-recovery", self.repo_a, "--dir", self.wt_dir]
        code1, _, _ = self.run_script(args)
        self.assertEqual(code1, 0)

        # Segunda ejecución debe ser exitosa y no mutar
        code2, out2, _ = self.run_script(args)
        self.assertEqual(code2, 0)
        self.assertIn("ya existe", out2)

    def test_attach_existing_free_branch(self):
        branch = "feat/OMNIFY-99-existing-branch"
        run_cmd(["git", "-C", self.repo_a, "branch", branch, "origin/dev"])

        code, out, err = self.run_script([
            "add", "OMNIFY-99", "existing-branch",
            self.repo_a,
            "--dir", self.wt_dir
        ])
        self.assertEqual(code, 0, f"Error: {err}")
        self.assertIn("conectado a rama existente", out)
        wt_a = os.path.join(self.wt_dir, "OMNIFY-99-existing-branch", "repo-a")
        _, current, _ = run_cmd(["git", "-C", wt_a, "branch", "--show-current"])
        self.assertEqual(current.strip(), branch)

    def test_error_branch_checked_out_elsewhere(self):
        # Crear un worktree en otra ruta para esa rama
        branch = "feat/OMNIFY-50-busy-branch"
        other_path = os.path.join(self.root, "other-worktree")
        run_cmd(["git", "-C", self.repo_a, "worktree", "add", "-b", branch, other_path, "origin/dev"])

        code, out, err = self.run_script([
            "add", "OMNIFY-50", "busy-branch",
            self.repo_a,
            "--dir", self.wt_dir
        ])
        self.assertEqual(code, 1)
        self.assertIn("ya está activa en otro worktree", err)
        self.assertIn(other_path, err)

    def test_error_origin_base_missing(self):
        code, out, err = self.run_script([
            "add", "OMNIFY-10", "no-such-base",
            self.repo_a,
            "--base", "nonexistent-branch",
            "--dir", self.wt_dir
        ])
        self.assertEqual(code, 1)
        self.assertIn("la rama remota 'origin/nonexistent-branch' no existe", err)
        self.assertIn("Ramas remotas disponibles", err)

    def test_error_dir_collision_not_worktree(self):
        # Crear carpeta en dest que contenga un archivo pero no sea worktree
        dest_parent = os.path.join(self.wt_dir, "OMNIFY-20-collision")
        dest_repo_a = os.path.join(dest_parent, "repo-a")
        os.makedirs(dest_repo_a, exist_ok=True)
        with open(os.path.join(dest_repo_a, "file.txt"), "w") as f:
            f.write("conflicto\n")

        code, out, err = self.run_script([
            "add", "OMNIFY-20", "collision",
            self.repo_a,
            "--dir", self.wt_dir
        ])
        self.assertEqual(code, 1)
        self.assertIn("ya existe, no está vacío y no es un worktree", err)

    def test_repo_resolution_sibling(self):
        # Ejecutar desde una subcarpeta hermana de repo-a
        work_sub = os.path.join(self.root, "subworkspace")
        os.makedirs(work_sub, exist_ok=True)

        code, out, err = self.run_script([
            "add", "OMNIFY-30-sibling", "test-sibling",
            "repo-a",
            "--dir", self.wt_dir
        ], cwd=work_sub)
        self.assertEqual(code, 0, f"Error: {err}")
        wt_a = os.path.join(self.wt_dir, "OMNIFY-30-SIBLING-test-sibling", "repo-a")
        self.assertTrue(os.path.isdir(wt_a))

    def test_no_fetch_flag(self):
        # Sin conexión remota o con remoto inválido pero con --no-fetch
        run_cmd(["git", "-C", self.repo_a, "remote", "set-url", "origin", "file:///invalid/path"])
        code, out, err = self.run_script([
            "add", "OMNIFY-40", "offline-test",
            self.repo_a,
            "--no-fetch",
            "--dir", self.wt_dir
        ])
        self.assertEqual(code, 0, f"Error: {err}")

    def test_error_base_dir_not_found(self):
        non_existent = os.path.join(self.root, "no-such-worktrees")
        code, out, err = self.run_script([
            "add", "OMNIFY-51", "dir-check",
            self.repo_a,
            "--dir", non_existent
        ])
        self.assertEqual(code, 1)
        self.assertIn("El contenedor base", err)
        self.assertIn("no existe", err)

    def test_base_dir_contextual_suggestion_sibling(self):
        # Ejecutar desde una subcarpeta dentro de root; .worktrees existe en ..
        sub = os.path.join(self.root, "child-dir")
        os.makedirs(sub, exist_ok=True)
        code, out, err = self.run_script([
            "add", "OMNIFY-52", "sibling-check",
            self.repo_a
        ], cwd=sub)
        self.assertEqual(code, 1)
        self.assertIn("Sugerencia: se detectó", err)
        self.assertIn(".worktrees", err)

    def test_error_base_dir_is_file(self):
        fake_file = os.path.join(self.root, "not-a-dir.txt")
        with open(fake_file, "w") as f:
            f.write("archivo\n")
        code, out, err = self.run_script([
            "add", "OMNIFY-53", "file-check",
            self.repo_a,
            "--dir", fake_file
        ])
        self.assertEqual(code, 1)
        self.assertIn("existe pero no es un directorio", err)

    def test_diverged_branch_ahead_fails_without_flag(self):
        branch = "feat/OMNIFY-60-diverged-ahead"
        run_cmd(["git", "-C", self.repo_a, "branch", branch, "origin/dev"])
        # Avanzar la rama con un commit local
        run_cmd(["git", "-C", self.repo_a, "checkout", branch])
        with open(os.path.join(self.repo_a, "nuevo.txt"), "w") as f:
            f.write("cambio local\n")
        run_cmd(["git", "-C", self.repo_a, "add", "nuevo.txt"])
        run_cmd(["git", "-C", self.repo_a, "commit", "-m", "commit local"])
        run_cmd(["git", "-C", self.repo_a, "checkout", "dev"])

        code, out, err = self.run_script([
            "add", "OMNIFY-60", "diverged-ahead",
            self.repo_a,
            "--dir", self.wt_dir
        ])
        self.assertEqual(code, 1)
        self.assertIn("diverge de 'origin/dev'", err)
        self.assertIn("1 commit(s) adelante", err)
        self.assertIn("--reuse-branch", err)
        # Atomicidad: el directorio del ticket no debió crearse
        target_dir = os.path.join(self.wt_dir, "OMNIFY-60-diverged-ahead")
        self.assertFalse(os.path.exists(target_dir))

    def test_diverged_branch_behind_fails_without_flag(self):
        branch = "feat/OMNIFY-61-diverged-behind"
        run_cmd(["git", "-C", self.repo_a, "branch", branch, "origin/dev"])
        # Avanzar origin/dev en el remoto con un nuevo commit
        seed = os.path.join(self.root, "seed")
        run_cmd(["git", "-C", seed, "checkout", "dev"])
        with open(os.path.join(seed, "remoto.txt"), "w") as f:
            f.write("remoto\n")
        run_cmd(["git", "-C", seed, "add", "remoto.txt"])
        run_cmd(["git", "-C", seed, "commit", "-m", "commit remoto"])
        run_cmd(["git", "-C", seed, "push", "origin", "dev"])

        code, out, err = self.run_script([
            "add", "OMNIFY-61", "diverged-behind",
            self.repo_a,
            "--dir", self.wt_dir
        ])
        self.assertEqual(code, 1)
        self.assertIn("diverge de 'origin/dev'", err)
        self.assertIn("1 commit(s) atrás", err)

    def test_diverged_branch_succeeds_with_reuse_flag(self):
        branch = "feat/OMNIFY-62-reuse-ok"
        run_cmd(["git", "-C", self.repo_a, "branch", branch, "origin/dev"])
        run_cmd(["git", "-C", self.repo_a, "checkout", branch])
        with open(os.path.join(self.repo_a, "reuse.txt"), "w") as f:
            f.write("cambio\n")
        run_cmd(["git", "-C", self.repo_a, "add", "reuse.txt"])
        run_cmd(["git", "-C", self.repo_a, "commit", "-m", "commit para reusar"])
        run_cmd(["git", "-C", self.repo_a, "checkout", "dev"])

        code, out, err = self.run_script([
            "add", "OMNIFY-62", "reuse-ok",
            self.repo_a,
            "--reuse-branch",
            "--dir", self.wt_dir
        ])
        self.assertEqual(code, 0, f"Error: {err}")
        self.assertIn("reutilizando rama", err)
        wt_a = os.path.join(self.wt_dir, "OMNIFY-62-reuse-ok", "repo-a")
        self.assertTrue(os.path.isdir(wt_a))

    def test_multi_repo_atomic_abort_on_divergence(self):
        # repo-a diverge sin flag, repo-b limpio
        branch_a = "feat/OMNIFY-70-atomic-test"
        run_cmd(["git", "-C", self.repo_a, "branch", branch_a, "origin/dev"])
        run_cmd(["git", "-C", self.repo_a, "checkout", branch_a])
        with open(os.path.join(self.repo_a, "mod.txt"), "w") as f:
            f.write("divergente\n")
        run_cmd(["git", "-C", self.repo_a, "add", "mod.txt"])
        run_cmd(["git", "-C", self.repo_a, "commit", "-m", "mod"])
        run_cmd(["git", "-C", self.repo_a, "checkout", "dev"])

        code, out, err = self.run_script([
            "add", "OMNIFY-70", "atomic-test",
            self.repo_a, self.repo_b,
            "--dir", self.wt_dir
        ])
        self.assertEqual(code, 1)
        # Assert atomicidad: absolutamente nada creado en .worktrees para OMNIFY-70
        target_dir = os.path.join(self.wt_dir, "OMNIFY-70-atomic-test")
        self.assertFalse(os.path.exists(target_dir))

    def test_duplicate_repo_fails_in_preflight(self):
        code, out, err = self.run_script([
            "add", "OMNIFY-80", "dup-test",
            self.repo_a, self.repo_a,
            "--dir", self.wt_dir
        ])
        self.assertEqual(code, 1)
        self.assertIn("repositorio o destino duplicado", err)
        target_dir = os.path.join(self.wt_dir, "OMNIFY-80-dup-test")
        self.assertFalse(os.path.exists(target_dir))

    def test_list_nonexistent_and_empty_dir(self):
        non_dir = os.path.join(self.root, "no-such-dir")
        code, out, err = self.run_script(["list", "--dir", non_dir])
        self.assertEqual(code, 0)
        self.assertIn("no existe", out)

        code, out, err = self.run_script(["list", "--dir", non_dir, "--json"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out), [])

        empty_dir = os.path.join(self.root, "empty-wt")
        os.makedirs(empty_dir)
        code, out, err = self.run_script(["list", "--dir", empty_dir])
        self.assertEqual(code, 0)
        self.assertIn("Sin worktrees activos", out)

        code, out, err = self.run_script(["list", "--dir", empty_dir, "--json"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out), [])

    def test_list_with_active_worktrees_and_dirty_status(self):
        # 1. Crear un contenedor multi-repo
        code, out, err = self.run_script([
            "add", "OMNIFY-90", "list-demo",
            self.repo_a, self.repo_b,
            "--dir", self.wt_dir
        ])
        self.assertEqual(code, 0)

        # 2. Listar en formato texto
        code, out, err = self.run_script(["list", "--dir", self.wt_dir])
        self.assertEqual(code, 0)
        self.assertIn("OMNIFY-90-list-demo", out)
        self.assertIn("repo-a", out)
        self.assertIn("repo-b", out)
        self.assertIn("(clean)", out)

        # 3. Ensuciar repo-a
        dirty_file = os.path.join(self.wt_dir, "OMNIFY-90-list-demo", "repo-a", "untracked.txt")
        with open(dirty_file, "w") as f:
            f.write("modificado\n")

        # 4. Listar en formato JSON y validar estructura
        code, out, err = self.run_script(["ls", "--dir", self.wt_dir, "--json"])
        self.assertEqual(code, 0)
        data = json.loads(out)
        self.assertEqual(len(data), 1)
        container = data[0]
        self.assertEqual(container["container"], "OMNIFY-90-list-demo")
        self.assertTrue(container["multi_repo"])
        self.assertEqual(len(container["repos"]), 2)

        repo_a_data = next(r for r in container["repos"] if r["name"] == "repo-a")
        repo_b_data = next(r for r in container["repos"] if r["name"] == "repo-b")
        self.assertTrue(repo_a_data["dirty"])
        self.assertEqual(repo_a_data["dirty_count"], 1)
        self.assertFalse(repo_b_data["dirty"])

    def test_audit_and_prune_safe_worktree(self):
        # 1. Crear worktree
        code, out, err = self.run_script([
            "add", "OMNIFY-101", "prune-safe",
            self.repo_a,
            "--dir", self.wt_dir
        ])
        self.assertEqual(code, 0)
        branch = "feat/OMNIFY-101-prune-safe"
        wt_path = os.path.join(self.wt_dir, "OMNIFY-101-prune-safe", "repo-a")

        # 2. Hacer commit y mergearlo en origin/dev
        with open(os.path.join(wt_path, "feat.txt"), "w") as f:
            f.write("feature done\n")
        run_cmd(["git", "-C", wt_path, "add", "feat.txt"])
        run_cmd(["git", "-C", wt_path, "commit", "-m", "feat: done"])
        run_cmd(["git", "-C", self.repo_a, "checkout", "dev"])
        run_cmd(["git", "-C", self.repo_a, "merge", branch])
        run_cmd(["git", "-C", self.repo_a, "push", "origin", "dev"])

        # 3. Auditar -> debe ser SEGURO_PARA_PODAR
        code, out, err = self.run_script(["audit", "--dir", self.wt_dir, "--json"])
        self.assertEqual(code, 0)
        data = json.loads(out)
        self.assertEqual(data[0]["category"], "SEGURO_PARA_PODAR")

        # 4. Prune en seco (dry-run) -> no debe borrar nada
        code, out, err = self.run_script(["prune", "--dir", self.wt_dir])
        self.assertEqual(code, 0)
        self.assertTrue(os.path.exists(wt_path))

        # 5. Prune --execute -> debe eliminar worktree, rama y contenedor
        code, out, err = self.run_script(["prune", "--execute", "--dir", self.wt_dir])
        self.assertEqual(code, 0)
        self.assertFalse(os.path.exists(wt_path))
        self.assertFalse(os.path.exists(os.path.join(self.wt_dir, "OMNIFY-101-prune-safe")))

        # Comprobar que la rama local fue eliminada
        code_b, _, _ = run_cmd(["git", "-C", self.repo_a, "rev-parse", "--verify", "--quiet", f"refs/heads/{branch}"])
        self.assertNotEqual(code_b, 0)

    def test_prune_stale_requires_include_stale_and_creates_backup(self):
        # 1. Crear worktree
        code, out, err = self.run_script([
            "add", "OMNIFY-102", "stale-backup",
            self.repo_a,
            "--dir", self.wt_dir
        ])
        self.assertEqual(code, 0)
        wt_path = os.path.join(self.wt_dir, "OMNIFY-102-stale-backup", "repo-a")

        # 2. Ensuciar el repositorio con cambios no commiteados
        with open(os.path.join(wt_path, "uncommitted.txt"), "w") as f:
            f.write("important notes\n")

        # 3. Prune sin --include-stale no debe borrar nada
        code, out, err = self.run_script(["prune", "--execute", "--dir", self.wt_dir])
        self.assertEqual(code, 0)
        self.assertTrue(os.path.exists(wt_path))

        # 4. Prune con --include-stale y directorio de backup explícito
        backup_dir = os.path.join(self.root, "backups")
        code, out, err = self.run_script([
            "prune", "OMNIFY-102-stale-backup",
            "--execute", "--include-stale",
            "--backup-dir", backup_dir,
            "--dir", self.wt_dir
        ])
        self.assertEqual(code, 0)
        self.assertFalse(os.path.exists(wt_path))

        # Verificar que se creó el archivo .tar.gz de respaldo y contiene los archivos
        self.assertTrue(os.path.isdir(backup_dir))
        tar_files = [f for f in os.listdir(backup_dir) if f.endswith(".tar.gz")]
        self.assertEqual(len(tar_files), 1)
        tar_path = os.path.join(backup_dir, tar_files[0])
        self.assertGreater(os.path.getsize(tar_path), 0)

        import tarfile
        with tarfile.open(tar_path, "r:gz") as tar:
            names = tar.getnames()
            self.assertTrue(any("uncommitted.txt" in n for n in names))

    def test_audit_implicit_fetch_vs_no_fetch(self):
        # 1. Crear worktree para OMNIFY-103
        code, out, err = self.run_script([
            "add", "OMNIFY-103", "fetch-test",
            self.repo_a,
            "--dir", self.wt_dir
        ])
        self.assertEqual(code, 0)
        branch = "feat/OMNIFY-103-fetch-test"
        wt_path = os.path.join(self.wt_dir, "OMNIFY-103-fetch-test", "repo-a")

        # 2. Hacer commit en el worktree y push a origin
        with open(os.path.join(wt_path, "feature.txt"), "w") as f:
            f.write("fetch feature\n")
        run_cmd(["git", "-C", wt_path, "add", "feature.txt"])
        run_cmd(["git", "-C", wt_path, "commit", "-m", "feat: remote test"])
        run_cmd(["git", "-C", wt_path, "push", "origin", branch])

        # 3. Simular merge en remoto origin/dev (desde seed) sin que repo_a haya hecho fetch aún
        seed_dir = os.path.join(self.root, "seed")
        run_cmd(["git", "-C", seed_dir, "fetch", "origin"])
        run_cmd(["git", "-C", seed_dir, "checkout", "dev"])
        run_cmd(["git", "-C", seed_dir, "merge", f"origin/{branch}"])
        run_cmd(["git", "-C", seed_dir, "push", "origin", "dev"])

        # 4. Con --no-fetch: repo_a usa caché local desactualizada -> EN_CURSO
        code, out, err = self.run_script(["audit", "OMNIFY-103-fetch-test", "--no-fetch", "--dir", self.wt_dir, "--json"])
        self.assertEqual(code, 0)
        data = json.loads(out)
        self.assertEqual(data[0]["category"], "EN_CURSO")

        # 5. Sin flag (fetch implícito por defecto): sincroniza origin y detecta el merge
        code, out, err = self.run_script(["audit", "OMNIFY-103-fetch-test", "--dir", self.wt_dir, "--json"])
        self.assertEqual(code, 0)
        data = json.loads(out)
        self.assertEqual(data[0]["category"], "SEGURO_PARA_PODAR")


if __name__ == "__main__":
    unittest.main()
