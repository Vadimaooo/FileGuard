"""Шляхи переносного застосунку незалежно від поточної робочої папки."""

import sys
from pathlib import Path


def application_directory() -> Path:
    # У збірці __file__ веде до тимчасових ресурсів, а дані мають пережити перезапуск.
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]
