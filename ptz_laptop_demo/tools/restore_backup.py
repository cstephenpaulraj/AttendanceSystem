"""RESTORE THE EDGE AI FACE DATABASE FROM AN ENCRYPTED BACKUP

The Edge AI service (app 3) writes an encrypted copy of its whole database (students, face
templates, database images, sessions, attendance, audit log) to the backup folder(s) within
30 seconds of every change, and at every start. This tool lists, verifies and restores them,
so a damaged disk or a corrupted database never means enrolling all students again.

    python tools\\restore_backup.py --list                 list the backups and check each one
    python tools\\restore_backup.py --restore latest       restore the newest backup that passes all checks
    python tools\\restore_backup.py --restore edge_ai_20261126_101500_ab12.db.enc

Close APP 3 before restoring. The current (damaged) database is kept as edge_ai.db.damaged-<time>.
"""
import argparse
import datetime as dt
import hashlib
import json
import socket
import sqlite3
import sys
import tempfile
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import config  # noqa: E402

DB_PATH = config.DATA_DIR / "edge_ai" / "edge_ai.db"


def folders():
    return [config.BACKUP_DIR] + ([Path(config.BACKUP_DIR2)] if config.BACKUP_DIR2 else [])


def all_backups():
    out = []
    for d in folders():
        man = d / "manifest.json"
        for e in (json.loads(man.read_text()) if man.exists() else []):
            out.append((d, e))
    return sorted(out, key=lambda de: de[1]["file"], reverse=True)


def check(folder, entry, key):
    """Return (plain_bytes, None) if the backup is good, else (None, problem)."""
    path = folder / entry["file"]
    if not path.exists():
        return None, "file missing"
    token = path.read_bytes()
    if hashlib.sha256(token).hexdigest() != entry["sha256_encrypted"]:
        return None, "checksum wrong (file damaged or changed)"
    try:
        plain = key.decrypt(token)
    except InvalidToken:
        return None, "cannot decrypt (wrong key or file changed)"
    if hashlib.sha256(plain).hexdigest() != entry["sha256_plain"]:
        return None, "content checksum wrong"
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "check.db"
        p.write_bytes(plain)
        con = sqlite3.connect(str(p))
        ok = con.execute("PRAGMA integrity_check").fetchone()[0]
        con.close()
    return (plain, None) if ok == "ok" else (None, f"database check failed: {ok}")


def edge_running():
    with socket.socket() as s:
        s.settimeout(0.5)
        return s.connect_ex((config.EDGE_HOST, config.EDGE_PORT)) == 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--restore", metavar="FILE|latest")
    args = ap.parse_args()
    if not config.BACKUP_KEY_FILE.exists():
        sys.exit(f"Backup key not found: {config.BACKUP_KEY_FILE}. Without the key the backups cannot be opened.")
    key = Fernet(config.BACKUP_KEY_FILE.read_bytes().strip())
    backups = all_backups()
    if not backups:
        sys.exit("No backups found in " + ", ".join(str(d) for d in folders()))
    if args.list or not args.restore:
        print(f"{'Backup file':<40} {'Taken':<20} {'Students':>8} {'Faces':>6}  Folder / check")
        for d, e in backups:
            _, problem = check(d, e, key)
            print(f"{e['file']:<40} {e['at']:<20} {e['students']:>8} {e['templates']:>6}  {d}  "
                  f"{'OK' if not problem else 'BAD: ' + problem}")
        return
    if edge_running():
        sys.exit("APP 3 (Edge AI service) is running. Close it first, then restore.")
    chosen = None
    for d, e in backups:
        if args.restore in ("latest", e["file"]):
            plain, problem = check(d, e, key)
            if problem:
                print(f"skip {e['file']} in {d}: {problem}")
                continue
            chosen = (d, e, plain)
            break
    if not chosen:
        sys.exit("No good backup found to restore.")
    d, e, plain = chosen
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    for suffix in ("", "-wal", "-shm"):
        p = Path(str(DB_PATH) + suffix)
        if p.exists():
            p.rename(Path(str(DB_PATH) + suffix + f".damaged-{stamp}"))
    DB_PATH.write_bytes(plain)
    print(f"Restored {e['file']} (taken {e['at']}, {e['students']} students, {e['templates']} face templates)\n"
          f"from {d}. The previous database was kept as {DB_PATH.name}.damaged-{stamp}. Start APP 3 again.")


if __name__ == "__main__":
    main()
