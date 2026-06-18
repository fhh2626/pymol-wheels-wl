#!/usr/bin/env python3

import argparse
import base64
import csv
import hashlib
import io
import re
import zipfile
from pathlib import Path


def normalize_distribution(name: str) -> str:
    return re.sub(r"[-_.]+", "_", name).lower()


def wheel_hash(data: bytes) -> str:
    digest = hashlib.sha256(data).digest()
    return "sha256=" + base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def parse_wheel_filename(path: Path) -> tuple[str, str, str]:
    stem = path.name.removesuffix(".whl")
    parts = stem.split("-")
    if len(parts) not in (5, 6):
        raise ValueError(f"Unexpected wheel filename format: {path.name}")
    distribution = parts[0]
    version = parts[1]
    tags = "-".join(parts[2:])
    return distribution, version, tags


def replace_metadata_name(content: bytes, new_name: str) -> bytes:
    text = content.decode("utf-8")
    if re.search(r"^Name: .*$", text, flags=re.MULTILINE):
        text = re.sub(r"^Name: .*$", f"Name: {new_name}", text, count=1, flags=re.MULTILINE)
    else:
        text = f"Name: {new_name}\n" + text
    return text.encode("utf-8")


def render_record(files: dict[str, bytes], record_path: str) -> bytes:
    out = io.StringIO(newline="")
    writer = csv.writer(out, lineterminator="\n")
    for name in sorted(files):
        if name == record_path:
            writer.writerow([name, "", ""])
        else:
            data = files[name]
            writer.writerow([name, wheel_hash(data), str(len(data))])
    return out.getvalue().encode("utf-8")


def rename_wheel(wheel_path: Path, new_name: str, delete_old: bool) -> Path:
    old_distribution, version, tags = parse_wheel_filename(wheel_path)
    old_dist = normalize_distribution(old_distribution)
    new_dist = normalize_distribution(new_name)
    old_dist_info = f"{old_dist}-{version}.dist-info"
    new_dist_info = f"{new_dist}-{version}.dist-info"
    new_wheel = wheel_path.with_name(f"{new_dist}-{version}-{tags}.whl")

    files: dict[str, bytes] = {}
    with zipfile.ZipFile(wheel_path, "r") as zin:
        names = zin.namelist()
        if not any(name.startswith(old_dist_info + "/") for name in names):
            candidates = sorted({name.split("/", 1)[0] for name in names if name.endswith(".dist-info/METADATA")})
            raise ValueError(f"Could not find {old_dist_info}/ in {wheel_path.name}; candidates: {candidates}")

        for name in names:
            data = zin.read(name)
            if name.startswith(old_dist_info + "/"):
                name = new_dist_info + name[len(old_dist_info):]
                if name == f"{new_dist_info}/METADATA":
                    data = replace_metadata_name(data, new_name)
            files[name] = data

    record_path = f"{new_dist_info}/RECORD"
    files[record_path] = render_record(files, record_path)

    tmp_wheel = new_wheel.with_suffix(new_wheel.suffix + ".tmp")
    with zipfile.ZipFile(tmp_wheel, "w", compression=zipfile.ZIP_DEFLATED) as zout:
        for name, data in files.items():
            zout.writestr(name, data)
    tmp_wheel.replace(new_wheel)

    if delete_old and wheel_path.resolve() != new_wheel.resolve():
        wheel_path.unlink()

    return new_wheel


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("wheel", type=Path)
    parser.add_argument("--name", required=True)
    parser.add_argument("--delete-old", action="store_true")
    args = parser.parse_args()

    renamed = rename_wheel(args.wheel, args.name, args.delete_old)
    print(renamed)


if __name__ == "__main__":
    main()
