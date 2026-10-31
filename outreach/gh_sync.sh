#!/usr/bin/env bash
set -euo pipefail

SRC="$HOME/mulhim-bot/outreach"
REPO="$HOME/mulhim-gh-outreach"

git -C "$REPO" pull --ff-only -q origin main
echo "pulled: $(git -C "$REPO" log --oneline -1)"

python3 "$SRC/merge_csv.py" "$SRC" "$REPO/outreach"

rsync -a \
  --include='*.py' \
  --include='*.txt' \
  --include='*.html' \
  --include='*.csv' \
  --exclude='*' \
  "$SRC/" "$REPO/outreach/"

cd "$REPO"
if git status --porcelain | grep -q .; then
  git add -A outreach
  git -c user.name="outreach-bot" -c user.email="outreach@localhost" commit -qm "sync: $(date -u +%F-%H%M)"
  git push -q origin main
  echo "pushed: $(git log --oneline -1)"
else
  echo "no code changes"
fi
