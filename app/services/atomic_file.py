"""Атомарний запис текстового файла зі збереженням попередньої версії."""

import os
import tempfile
from contextlib import contextmanager
from pathlib import Path

from app.services.integrity_service import check_cancelled


@contextmanager
def atomic_text_file(destination: Path, cancel, encoding="utf-8", newline=""):
    check_cancelled(cancel)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding=encoding, newline=newline,
                                         dir=destination.parent, prefix=".fileguard-", suffix=".tmp",
                                         delete=False) as stream:
            temporary = Path(stream.name)
            yield stream
            stream.flush()
            os.fsync(stream.fileno())
        check_cancelled(cancel)
        os.replace(temporary, destination)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
