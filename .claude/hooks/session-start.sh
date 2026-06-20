#!/bin/bash
# SessionStart hook: report the current project version and whether the local
# checkout is up to date with the remote branch. Never fails the session.
set -uo pipefail

BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "unknown")
LOCAL_HASH=$(git rev-parse --short HEAD 2>/dev/null || echo "unknown")

# Version is tracked via commit messages like "v0.1.7: ...". Scan recent
# commits so we still find it even if the very latest commit has no tag.
VERSION=$(git log -20 --format='%s' 2>/dev/null \
  | grep -oE 'v[0-9]+\.[0-9]+\.[0-9]+' | head -1)
[ -z "$VERSION" ] && VERSION="(no version tag found)"

REMOTE_STATUS="could not reach remote, comparison skipped"
if git fetch origin "$BRANCH" --quiet 2>/dev/null; then
  REMOTE_HASH=$(git rev-parse --short "origin/$BRANCH" 2>/dev/null || echo "")
  if [ -n "$REMOTE_HASH" ]; then
    if [ "$LOCAL_HASH" = "$REMOTE_HASH" ]; then
      REMOTE_STATUS="up to date with origin/$BRANCH"
    else
      BEHIND=$(git rev-list --count "HEAD..origin/$BRANCH" 2>/dev/null || echo "?")
      AHEAD=$(git rev-list --count "origin/$BRANCH..HEAD" 2>/dev/null || echo "?")
      REMOTE_STATUS="differs from origin/$BRANCH (behind $BEHIND, ahead $AHEAD; remote is $REMOTE_HASH)"
    fi
  fi
fi

MSG="Version check -> $VERSION ($LOCAL_HASH) on branch $BRANCH; $REMOTE_STATUS"

# Emit as SessionStart additionalContext so the assistant surfaces it at the
# start of every conversation.
printf '{"hookSpecificOutput":{"hookEventName":"SessionStart","additionalContext":%s}}\n' \
  "$(printf '%s' "$MSG" | python3 -c 'import json,sys; print(json.dumps(sys.stdin.read()))')"
