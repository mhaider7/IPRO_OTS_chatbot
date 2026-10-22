from pathlib import Path
import os
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
# Tests never depend on a built index or a running Ollama unless they opt in.
os.environ.setdefault("HAWK_SERVICE", "demo")


def pytest_configure(config):
    config.addinivalue_line("markers", "ollama: needs a running local Ollama server")
    config.addinivalue_line("markers", "index: needs the built ChromaDB knowledge base")
