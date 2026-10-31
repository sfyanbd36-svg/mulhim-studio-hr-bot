#!/bin/bash
# Long-running chunk for the CI runner: bot in background + outreach every 2h.
set -uo pipefail

cd "$(dirname "$0")"

LOG=bot.log
: >> "$LOG"
python bot.py >> "$LOG" 2>&1 &
BOT=$!

DEADLINE=$((SECONDS + 21120))
NEXT_OUTREACH=$SECONDS

while kill -0 "$BOT" 2>/dev/null && [ "$SECONDS" -lt "$DEADLINE" ]; do
  if [ "$SECONDS" -ge "$NEXT_OUTREACH" ]; then
    TZ=Asia/Baghdad python outreach/auto.py >> outreach/auto.log 2>&1 || true
    NEXT_OUTREACH=$((NEXT_OUTREACH + 7200))
  fi
  sleep 30
done

kill -TERM "$BOT" 2>/dev/null || true
sleep 20
kill -KILL "$BOT" 2>/dev/null || true
wait "$BOT" 2>/dev/null || true

tail -n 60 "$LOG"
