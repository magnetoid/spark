#!/bin/sh
# Keeps the Janus gateway running inside Spark's compose stack. Whenever the gateway exits
# (a config change Spark pushed asks for a restart, exit code 75; a crash; "Update now"), it
# comes back up, and at most once an hour it first pulls the latest Janus from the repository.
set -u
HOME_DIR="${JANUS_HOME:-/data/janus}"
STAMP="$HOME_DIR/.last-update-check"
mkdir -p "$HOME_DIR"

update_if_due() {
  [ "${JANUS_AUTO_UPDATE:-true}" = "true" ] || return 0
  if [ -f "$STAMP" ] && [ -z "$(find "$STAMP" -mmin +60 2>/dev/null)" ]; then
    return 0
  fi
  echo "[janus-run] checking ${JANUS_REPO:-https://github.com/magnetoid/Janus-Agent.git}@${JANUS_REF:-main} for updates"
  if uv pip install --python /opt/janus/bin/python -q -U \
      "janus-agent[messaging,mcp,anthropic] @ git+${JANUS_REPO:-https://github.com/magnetoid/Janus-Agent.git}@${JANUS_REF:-main}"; then
    echo "[janus-run] janus $(/opt/janus/bin/janus --version 2>/dev/null | tail -1)"
  else
    echo "[janus-run] update failed; keeping the installed version"
  fi
  touch "$STAMP"
}

first=1
while true; do
  if [ "$first" = 1 ]; then first=0; else update_if_due; fi
  /opt/janus/bin/janus gateway run
  code=$?
  echo "[janus-run] gateway exited with $code; restarting in 3s"
  sleep 3
done
