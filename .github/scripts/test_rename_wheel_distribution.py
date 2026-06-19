import importlib.util
import csv
import io
import tempfile
import unittest
import zipfile
from pathlib import Path


SCRIPT = Path(__file__).with_name("rename_wheel_distribution.py")
SPEC = importlib.util.spec_from_file_location("rename_wheel_distribution", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class AddRuntimeRequirementsTests(unittest.TestCase):
    def test_adds_runtime_requirement_even_if_dev_extra_exists(self):
        metadata = (
            b"Metadata-Version: 2.4\n"
            b"Name: pymol\n"
            b"Requires-Dist: numpy>=2.0\n"
            b'Requires-Dist: PySide6==6.8.1; extra == "dev"\n\n'
            b"Description\n"
        )

        result = MODULE.add_runtime_requirements(
            metadata, ["PySide6>=6.10.1", "biopython>=1.80", "msgpack>=1.0.8"]
        ).decode()

        self.assertIn("Requires-Dist: PySide6>=6.10.1\n", result)
        self.assertIn("Requires-Dist: biopython>=1.80\n", result)
        self.assertIn("Requires-Dist: msgpack>=1.0.8\n", result)
        self.assertIn('Requires-Dist: PySide6==6.8.1; extra == "dev"\n', result)
        self.assertTrue(result.endswith("\n\nDescription\n"))

    def test_does_not_duplicate_an_existing_runtime_requirement(self):
        metadata = b"Metadata-Version: 2.4\nRequires-Dist: msgpack>=1.0.8\n\n"

        result = MODULE.add_runtime_requirements(metadata, ["msgpack>=1.0.8"]).decode()

        self.assertEqual(result.count("Requires-Dist: msgpack>=1.0.8"), 1)


class RenameWheelTests(unittest.TestCase):
    def test_renamed_wheel_contains_requirements_and_valid_record(self):
        with tempfile.TemporaryDirectory() as directory:
            wheel = Path(directory) / "pymol-3.2.0-cp314-cp314-win_amd64.whl"
            with zipfile.ZipFile(wheel, "w") as archive:
                archive.writestr("pymol/__init__.py", b"")
                archive.writestr(
                    "pymol-3.2.0.dist-info/METADATA",
                    b"Metadata-Version: 2.4\nName: pymol\nRequires-Dist: numpy>=2.0\n\n",
                )
                archive.writestr("pymol-3.2.0.dist-info/RECORD", b"")

            renamed = MODULE.rename_wheel(
                wheel,
                "pymol-opensource-wl",
                True,
            )
            finalized = MODULE.rename_wheel(
                renamed,
                "pymol-opensource-wl",
                False,
                ["PySide6>=6.10.1", "biopython>=1.80", "msgpack>=1.0.8"],
            )

            self.assertFalse(wheel.exists())
            self.assertEqual(finalized, renamed)
            with zipfile.ZipFile(finalized) as archive:
                dist_info = "pymol_opensource_wl-3.2.0.dist-info"
                metadata = archive.read(f"{dist_info}/METADATA").decode()
                record = archive.read(f"{dist_info}/RECORD").decode()
                self.assertIn("Name: pymol-opensource-wl\n", metadata)
                self.assertIn("Requires-Dist: PySide6>=6.10.1\n", metadata)
                rows = {row[0]: row[1:] for row in csv.reader(io.StringIO(record))}
                self.assertEqual(rows[f"{dist_info}/RECORD"], ["", ""])
                for name in (f"{dist_info}/METADATA", "pymol/__init__.py"):
                    data = archive.read(name)
                    self.assertEqual(rows[name], [MODULE.wheel_hash(data), str(len(data))])


if __name__ == "__main__":
    unittest.main()
