"""Wrapper around publish.py for the daily scheduled run.

Task Scheduler gives no console to read, so this keeps a dated log, records a
one-line status that is easy to glance at, and exits with publish.py's own code
so a failed morning shows up as a failed task rather than silence.

    python tools/daily_run.py [extra publish.py arguments...]
"""

from __future__ import annotations

import subprocess
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOGS = ROOT / "logs"
KEEP_DAYS = 30


def prune_old_logs() -> None:
    cutoff = date.today() - timedelta(days=KEEP_DAYS)
    for old in LOGS.glob("publish-*.log"):
        try:
            stamp = date.fromisoformat(old.stem.replace("publish-", ""))
        except ValueError:
            continue
        if stamp < cutoff:
            old.unlink(missing_ok=True)


def main(argv: list[str]) -> int:
    LOGS.mkdir(parents=True, exist_ok=True)
    started = datetime.now()
    log_path = LOGS / f"publish-{started.date().isoformat()}.log"

    header = f"\n===== {started.isoformat(timespec='seconds')} =====\n"
    with log_path.open("a", encoding="utf-8") as log:
        log.write(header)
        log.flush()
        proc = subprocess.run(
            [sys.executable, str(ROOT / "publish.py"), *argv],
            cwd=str(ROOT), stdout=log, stderr=subprocess.STDOUT, text=True,
        )

    took = (datetime.now() - started).total_seconds()
    status = "OK" if proc.returncode == 0 else "FAILED"
    summary = (f"{status}  {started.isoformat(timespec='seconds')}  "
               f"exit={proc.returncode}  {took:.0f}s  log={log_path.name}\n")
    (LOGS / "last-status.txt").write_text(summary, encoding="utf-8")

    # Repeat the tail of a failed run into the status file: whoever looks is
    # looking because something broke, and the reason should be right there.
    if proc.returncode != 0:
        tail = log_path.read_text(encoding="utf-8", errors="replace").splitlines()[-15:]
        with (LOGS / "last-status.txt").open("a", encoding="utf-8") as f:
            f.write("\n".join(tail) + "\n")

    prune_old_logs()
    # Under pythonw (how the scheduled task runs it) there is no stdout at all.
    if sys.stdout is not None:
        print(summary.strip())
    return proc.returncode


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
