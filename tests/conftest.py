import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("GEMINI_API_KEY", "test-key-fake-fake-fake-fake")
os.environ.setdefault("USAR_VERTEX", "false")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pytest


@pytest.fixture
def tmp_workdir(monkeypatch, tmp_path):
    from backend.modulos import herramientas
    monkeypatch.setattr(herramientas, "WORKDIR", tmp_path)
    return tmp_path


@pytest.fixture
def tmp_skills(monkeypatch, tmp_path):
    from backend.modulos import skills as skills_mod
    p = tmp_path / "skills.json"
    return skills_mod.Skills(path=p)


@pytest.fixture
def historial_tmp(tmp_path):
    from backend.modulos.memoria import HistorialPersistente
    return HistorialPersistente(path=str(tmp_path / "hist.json"))
