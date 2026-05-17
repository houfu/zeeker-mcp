#!/bin/bash
# Enforces the 30-day log retention claim in docs/privacy.md §2.
#
# docker-compose.yml caps log size via the json-file driver (10MB × 30 files);
# this script enforces the *time* dimension by deleting rotated segments whose
# mtime is older than 30 days. The active segment (<id>-json.log) is left
# alone — its mtime updates on every write, so -mtime +30 never fires while
# the container is active.
#
# Install (run once, as root):
#   sudo install -m 0755 scripts/log-prune-30d.sh \
#        /etc/cron.daily/zeeker-mcp-log-prune
#
# Cron.daily entries run as root, which is required to read /var/lib/docker.
set -euo pipefail

CONTAINER=zeeker-mcp
CID=$(docker inspect --format='{{.Id}}' "$CONTAINER" 2>/dev/null) || exit 0
LOGDIR="/var/lib/docker/containers/$CID"
[ -d "$LOGDIR" ] || exit 0

find "$LOGDIR" -maxdepth 1 -type f \
    -name "${CID}-json.log.*" -mtime +30 -delete
