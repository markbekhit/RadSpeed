"""Tests for the authenticated fracture workbench filesystem boundary."""

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from web.fracture_workbench import resolve_workbench_image


class FractureWorkbenchPathTests(unittest.TestCase):
    def test_resolves_supported_image_below_root(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            expected = (
                root / "images" / "distal_fracture" / "distal_1.jpg"
            ).resolve()
            self.assertEqual(
                resolve_workbench_image(
                    "distal_fracture/distal_1.jpg", root=root
                ),
                expected,
            )

    def test_rejects_parent_traversal(self):
        with TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                resolve_workbench_image("../users.db.jpg", root=Path(directory))

    def test_rejects_absolute_path(self):
        with self.assertRaises(ValueError):
            resolve_workbench_image("/etc/passwd.jpg", root=Path("/tmp/workbench"))

    def test_rejects_unsupported_file_type(self):
        with self.assertRaises(ValueError):
            resolve_workbench_image("../../users.db", root=Path("/tmp/workbench"))

    def test_rejects_symlink_escape(self):
        with TemporaryDirectory() as directory, TemporaryDirectory() as outside:
            root = Path(directory)
            image_root = root / "images"
            image_root.mkdir()
            (image_root / "escape").symlink_to(Path(outside), target_is_directory=True)
            with self.assertRaises(ValueError):
                resolve_workbench_image("escape/image.jpg", root=root)


if __name__ == "__main__":
    unittest.main()
