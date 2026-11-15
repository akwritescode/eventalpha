#!/bin/sh
# Validates commit messages against Conventional Commits (https://www.conventionalcommits.org).
#
#   scripts/check-commit-msg.sh <file>          check one message (the commit-msg hook)
#   scripts/check-commit-msg.sh --range A..B    check every commit in a range (pre-push, CI)
#
# Header: <type>(<optional scope>)<optional !>: <description>
#   type        feat fix docs style refactor perf test build ci chore revert
#   scope       lowercase letters, digits, hyphens: feat(web), fix(alerts)
#   description starts lowercase, no trailing period; header at most 100 characters
#   (the commitlint default; aim for 72 so it reads well in git log)
# Body (optional) is separated from the header by one blank line.
set -eu

TYPES='feat|fix|docs|style|refactor|perf|test|build|ci|chore|revert'
HEADER_RE="^($TYPES)(\([a-z0-9][a-z0-9-]*\))?!?: [^A-Z ].*[^. ]$"
MAX=100

check() {  # $1 = full message, $2 = label for errors
  msg=$(printf '%s\n' "$1" | grep -v '^#' || true)
  header=$(printf '%s\n' "$msg" | sed -n 1p)
  case "$header" in Merge\ *) return 0 ;; esac  # merge commits made by git or GitHub
  err=""
  printf '%s' "$header" | grep -Eq "$HEADER_RE" || err="header must be '<type>(<scope>): <description>' with type one of ${TYPES}, description starting lowercase and not ending with a period"
  [ ${#header} -le $MAX ] || err="${err:+$err; }header is ${#header} characters (max $MAX)"
  second=$(printf '%s\n' "$msg" | sed -n 2p)
  [ -z "$second" ] || err="${err:+$err; }leave a blank line between the header and the body"
  if [ -n "$err" ]; then
    printf 'Not a Conventional Commit (%s):\n  %s\n  -> %s\n' "$2" "$header" "$err" >&2
    return 1
  fi
}

if [ "${1:-}" = "--range" ]; then
  status=0
  for c in $(git rev-list --no-merges "$2"); do
    check "$(git log -1 --format=%B "$c")" "$(git log -1 --format=%h "$c")" || status=1
  done
  exit $status
fi
check "$(cat "$1")" "commit message"
