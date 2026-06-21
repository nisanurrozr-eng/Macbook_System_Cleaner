import os, json, subprocess
from pathlib import Path
REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "clean_mac.sh"

def _ops(home):
    env = dict(os.environ, HOME=str(home), APPLE_CLEANUP_LANG="en")
    out = subprocess.run(["bash", str(SCRIPT), "--ops-json"], env=env,
                         capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)

def _write_log(home, lines):
    log = home / ".cache/apple-cleanup/operations.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text("\n".join(lines) + "\n")

def test_recoverable_flag(tmp_path):
    home = tmp_path; trash = home / ".Trash"; trash.mkdir()
    dest = trash / "junk.txt"; dest.write_text("x")
    _write_log(home, [
        # recoverable: trash + existing dest
        f"1000\tsessA\ttrash\t10\t{home}/junk.txt\t{dest}\ttest",
        # not recoverable: permanent delete
        f"1001\tsessA\tdelete\t20\t{home}/gone\t\ttest",
        # not recoverable: legacy 5-col line
        "999\tdelete\t5\t/some/path\tlegacy",
    ])
    data = _ops(home)
    assert data["success"] is True
    sess = {s["session_id"]: s for s in data["sessions"]}
    assert "sessA" in sess
    items = {i["id"]: i for i in sess["sessA"]["items"]}
    rec = [i for i in items.values() if i["source"].endswith("junk.txt")][0]
    assert rec["recoverable"] is True
    perm = [i for i in items.values() if i["action"] == "delete" and i["trash_dest"] == ""][0]
    assert perm["recoverable"] is False
    assert sess["sessA"]["recoverable_count"] == 1
