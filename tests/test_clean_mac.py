# tests/test_clean_mac.py
import json
import os
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "clean_mac.sh"


def run_scan(home: Path) -> dict:
    """clean_mac.sh --scan-json'u izole bir HOME ile çalıştır, JSON döndür."""
    env = dict(os.environ, HOME=str(home))
    out = subprocess.run(
        ["bash", str(SCRIPT), "--scan-json"],
        env=env, capture_output=True, text=True, timeout=60,
    )
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def make_dir_with_bytes(path: Path, kb: int) -> None:
    """path altında ~kb kilobayt veri oluştur."""
    path.mkdir(parents=True, exist_ok=True)
    (path / "blob.bin").write_bytes(b"x" * (kb * 1024))


def test_scan_json_has_required_keys(tmp_path):
    data = run_scan(tmp_path)
    assert data["success"] is True
    assert "scan" in data
    assert "total_bytes" in data
    # Her kategori size_bytes alanı taşımalı
    for cat_id, info in data["scan"].items():
        assert "size_bytes" in info, cat_id
