import os
import subprocess
import time
from pathlib import Path

BOT_DIR = Path.home() / "mulhim-bot"
REPO_DIR = Path.home() / "mulhim-bot-offsite"
REPO_REMOTE = "https://github.com/sfyanbd36-svg/mulhim-bot-offsite.git"
KEEP = 14
FILES = [
    "mulhim.db",
    "companies.csv",
    "company_jobs.csv",
    "applicants.csv",
    "users.csv",
    "referrals.csv",
    "seeker_prefs.csv",
    ".env",
    "bot_data.pickle",
    "userbot/mulhim.session",
    "outreach/companies.csv",
    "outreach/companies_baghdad.csv",
    "outreach/companies_web.csv",
    "outreach/sent.csv",
    "outreach/osm_web_done.json",
    "outreach/osm_pois.json",
]
DIRS = ["cvs"]


def _git(*args, cwd):
    return subprocess.run(
        ["git", *args], cwd=str(cwd), capture_output=True, text=True, timeout=120
    )


def _stamp():
    return time.strftime("%Y%m%d_%H%M%S")


def ensure_repo():
    if not (REPO_DIR / ".git").exists():
        r = _git("clone", REPO_REMOTE, str(REPO_DIR), cwd=REPO_DIR.parent)
        if r.returncode != 0:
            return False, r.stderr.strip()
    return True, ""


def make_archive(dest):
    import zipfile

    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as zf:
        for name in FILES:
            path = BOT_DIR / name
            if path.is_file():
                zf.write(path, name)
        for folder in DIRS:
            root = BOT_DIR / folder
            if root.is_dir():
                for path in sorted(root.rglob("*")):
                    if path.is_file():
                        zf.write(path, str(path.relative_to(BOT_DIR)))
    return dest.exists()


def prune():
    archives = sorted(REPO_DIR.glob("backup_*.zip"))
    for old in archives[:-KEEP]:
        old.unlink()
        _git("rm", "-f", "--cached", old.name, cwd=REPO_DIR)


def run():
    ok, err = ensure_repo()
    if not ok:
        return "clone failed: " + err
    archive = REPO_DIR / ("backup_" + _stamp() + ".zip")
    if not make_archive(archive):
        return "archive failed"
    prune()
    _git("add", "-A", cwd=REPO_DIR)
    status = _git("status", "--porcelain", cwd=REPO_DIR)
    if not status.stdout.strip():
        return "no changes"
    _git(
        "-c", "user.name=mulhim-bot", "-c", "user.email=sfyanbd36@gmail.com",
        "commit", "-m", "Backup " + archive.stem,
        cwd=REPO_DIR,
    )
    push = _git("push", "origin", "HEAD", cwd=REPO_DIR)
    if push.returncode != 0:
        return "push failed: " + push.stderr.strip()
    return "pushed " + archive.name


if __name__ == "__main__":
    os.chdir(BOT_DIR)
    print(run())
