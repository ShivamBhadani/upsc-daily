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


def notify(title: str, message: str) -> None:
    """Put a failure on screen.

    A scheduled run that quietly stops publishing is worse than one that breaks
    loudly: the site simply goes stale and nobody notices for days. Best effort
    only — a desktop notification must never be able to fail the run.
    """
    # A lone apostrophe would end the PowerShell string and break the alert.
    title = title.replace("'", "''")
    message = message.replace("'", "''")
    script = (
        "[void][System.Reflection.Assembly]::LoadWithPartialName('System.Windows.Forms');"
        "$n = New-Object System.Windows.Forms.NotifyIcon;"
        "$n.Icon = [System.Drawing.SystemIcons]::Warning;"
        "$n.Visible = $true;"
        f"$n.ShowBalloonTip(20000, '{title}', '{message}', "
        "[System.Windows.Forms.ToolTipIcon]::Warning);"
        "Start-Sleep -Seconds 12; $n.Dispose()"
    )
    try:
        subprocess.Popen(
            ["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", script],
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except Exception:  # noqa: BLE001 - never let the alert break the run
        pass


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

    if proc.returncode != 0:
        notify("UPSC Daily: no paper published",
               "The morning run failed. See logs/last-status.txt — the usual cause "
               "is the claude CLI being signed out.")

    prune_old_logs()
    # Under pythonw (how the scheduled task runs it) there is no stdout at all.
    if sys.stdout is not None:
        print(summary.strip())
    return proc.returncode


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
