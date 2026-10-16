"""Відтворювана переносна Windows-збірка без включення особистих даних."""

import argparse
import hashlib
import os
import shutil
import subprocess
import sys
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

PROJECT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description="Збірка FileGuard для Windows")
    parser.add_argument("--work-dir", type=Path, default=PROJECT / "build")
    parser.add_argument("--output-dir", type=Path, default=PROJECT / "dist")
    args = parser.parse_args()
    if sys.platform != "win32":
        parser.error("Windows-збірку потрібно створювати у Windows.")
    import PyInstaller
    if PyInstaller.__version__ != "6.12.0":
        parser.error("Установіть версію з requirements-build.txt.")
    work = args.work_dir.resolve()
    package = args.output_dir.resolve() / "FileGuard"
    for directory in (work, package, work / "temp", work / "spec", package / "data", package / "reports"):
        directory.mkdir(parents=True, exist_ok=True)
    # Кеш і тимчасові файли можна перенести на диск із достатнім вільним місцем.
    environment = dict(os.environ, PYINSTALLER_CONFIG_DIR=str(work / "cache"),
                       TEMP=str(work / "temp"), TMP=str(work / "temp"))
    subprocess.run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--onefile", "--windowed",
                    "--noupx", "--name", "FileGuard", "--distpath", str(package),
                    "--workpath", str(work / "analysis"), "--specpath", str(work / "spec"),
                    str(PROJECT / "main.py")], cwd=PROJECT, env=environment, check=True)
    shutil.copyfile(PROJECT / "docs" / "USER_GUIDE.md", package / "Інструкція.txt")
    # До архіву потрапляє лише явний список, без settings.json, історії та еталонів.
    files = [package / "FileGuard.exe", package / "Інструкція.txt"]
    for source in sorted((PROJECT / "demo_files").rglob("*")):
        if source.is_file():
            target = package / "demo_files" / source.relative_to(PROJECT / "demo_files")
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
            files.append(target)
    checksums = package / "SHA256SUMS.txt"
    checksums.write_text("".join(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  "
                                 f"{path.relative_to(package).as_posix()}\n" for path in files), encoding="utf-8")
    archive = package.parent / "FileGuard-Windows.zip"
    with ZipFile(archive, "w", ZIP_DEFLATED) as output:
        for path in files + [checksums]:
            output.write(path, f"FileGuard/{path.relative_to(package).as_posix()}")
        for directory in ("data", "reports"):
            output.writestr(f"FileGuard/{directory}/", "")
    with ZipFile(archive) as output:
        if output.testzip() is not None:
            raise RuntimeError("Помилка цілісності архіву збірки.")
    print(f"EXE: {package / 'FileGuard.exe'}")
    print(f"ZIP: {archive}")
    print(f"SHA-256 ZIP: {hashlib.sha256(archive.read_bytes()).hexdigest()}")


if __name__ == "__main__":
    main()
