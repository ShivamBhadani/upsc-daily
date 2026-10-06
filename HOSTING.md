# Putting UPSC Daily online

The site is plain static files — HTML, CSS, one JavaScript file and a JSON file per
day. There is no server, no database and no API key on the hosting side, so it can
be served free and indefinitely, and it cannot go down under load or cold-start.

Everything a visitor does — answering, timed tests, accuracy — happens in their own
browser and stays there.

---

## One-time setup (about five minutes)

### 1. Make a repository

On github.com, create a **new repository** named `upsc-daily`. Make it **public** —
GitHub Pages is free for public repositories. Do not add a README, .gitignore or
licence from the form; this folder already has what it needs.

### 2. Push this folder to it

From inside `upsc-daily/`:

```bash
git init -b main
git add .
git commit -m "UPSC Daily — current affairs to UPSC-style questions"
git remote add origin https://github.com/<your-username>/upsc-daily.git
git push -u origin main
```

### 3. Switch on GitHub Pages

In the repository: **Settings → Pages**.

* Source: **Deploy from a branch**
* Branch: **main**, folder: **/docs**
* Save.

A minute later the site is live at:

```
https://<your-username>.github.io/upsc-daily/
```

That link is what you share. Anyone can open it — no account, no sign-in, nothing to
install.

---

## Publishing a day's paper

One command does the whole round: collect the news, set the questions, rebuild the
site, commit and push.

```bash
python publish.py
```

Useful variations:

| Command | What it does |
|---|---|
| `python publish.py --no-push` | everything except the commit and push |
| `python publish.py --rebuild-only` | re-render the site from papers already stored |
| `python publish.py --regenerate` | set today's questions again, replacing them |
| `python publish.py --date 2026-09-05 --no-fetch --regenerate` | redo one past day |
| `python publish.py --prelims 30` | a longer paper |
| `python publish.py --allow-offline` | publish template drafts when no model is reachable |

If no model backend can be reached, the publisher sets **nothing** and exits with a
non-zero status rather than putting template drafts on a public site — so a scheduled
run shows up as failed instead of quietly publishing weak questions. Pass
`--allow-offline` if you do want the drafts; they stay badged as drafts on the site.

The desktop app's **Publish site** button does the build step alone, so you can look
the paper over in the app first and then push with `python publish.py --no-fetch
--no-generate`.

### The question-setting backend

Questions are set locally through the `claude` CLI, using your own Claude
subscription — nothing is spent on the hosting side, and no key ever reaches the
repository.

If the CLI has been signed out you will see *"claude CLI is signed out"*. Run
`claude` once in a terminal to sign in again, then re-run the publish.

If you would rather have it run unattended later, set `ANTHROPIC_API_KEY` in your
environment and the publisher will use the API instead, without any other change.

### Running it every morning by itself

A Task Scheduler entry named **UPSC Daily publish** runs the whole round at 07:00
every day — collect, set, build, commit, push. It is already registered on this
machine. It runs `tools/daily_run.py` through `pythonw.exe`, so no console window
appears.

What the task is set to do:

| Setting | Why |
|---|---|
| Start when available | If the laptop was off at 07:00, it runs as soon as it is on again |
| Run only if network available | No point fetching feeds without one |
| Battery restrictions off | A laptop is usually unplugged in the morning |
| Restart on failure, 3 × 20 min | Rides out a flaky connection |
| One hour time limit | A full run takes about 7 minutes |
| Only while signed in | The `claude` CLI and the git credential both live in your user session |

Run it by hand any time:

```bash
.\daily.cmd
```

Manage it:

```powershell
Get-ScheduledTaskInfo -TaskName "UPSC Daily publish"     # last run and result
Start-ScheduledTask   -TaskName "UPSC Daily publish"     # run it now
Disable-ScheduledTask -TaskName "UPSC Daily publish"     # pause it
Unregister-ScheduledTask -TaskName "UPSC Daily publish"  # remove it
```

The definition is kept in `tools/upsc-daily-task.xml` if you ever need to recreate
it, with `Register-ScheduledTask -TaskName "UPSC Daily publish" -Xml (Get-Content
tools\upsc-daily-task.xml -Raw)`.

### When a morning fails

`logs/last-status.txt` holds one line — `OK` or `FAILED`, with the exit code and
the tail of the failing run. Full output per day is in `logs/publish-<date>.log`,
pruned after 30 days. A failed run also raises a desktop notification, because a
job that quietly stops publishing is worse than one that breaks loudly.

The usual cause is the **`claude` CLI being signed out** — its OAuth session
expires every so often. The run then sets nothing, publishes nothing, and exits
non-zero. Fix it by running `claude` once in a terminal to sign in, then either
wait for tomorrow or run `.\daily.cmd` by hand.

The site itself is the other tell: every page footer carries the build time, so a
date that stops moving means the job stopped running.

---

## What is in the repository

```
upsc_daily/          the application and the publisher
run_upsc_daily.py    desktop app
publish.py           collect → set questions → build → push
docs/                the built site — this is what GitHub Pages serves
  index.html         the app shell
  assets/            one stylesheet, one script
  data/              index.json, style.json, and one file per day
  papers/            a printable copy of each day's paper
  latest.html        printable copy of the newest paper
README.md            what the project is
HOSTING.md           this file
```

The question database lives outside the repository, in `%LOCALAPPDATA%\UPSCDaily`,
so your local notes and history are never published. Only `docs/` is.

---

## Serving it somewhere else instead

`docs/` is an ordinary folder of static files. Any of these work with no change:

```bash
# Netlify / Cloudflare Pages / Vercel — point the project at docs/ as the publish directory
# Amazon S3 or any object store
aws s3 sync docs/ s3://your-bucket/ --delete
# your own server
rsync -av docs/ user@host:/var/www/upsc-daily/
# a quick look locally
python -m http.server 8000 -d docs
```

Build into a different folder with `python publish.py --out /path/to/wherever`.

---

## A note for whoever reads the site

The paper is practice material generated by a language model from that day's news,
against a model of previous-year Prelims patterns. Every question carries a link to
the article it came from. It is good practice, not an official paper — anything
surprising is worth checking against the source, and a question badged
**OFFLINE DRAFT** came from the fallback template engine and deserves more
scepticism than the rest.
