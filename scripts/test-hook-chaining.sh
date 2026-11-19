#!/bin/sh
# Exercise shared hooks in a disposable repository without changing local guard scripts.
set -eu
root=$(git rev-parse --show-toplevel)
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
mkdir -p "$tmp/bin"
printf '#!/bin/sh\nexit 0\n' > "$tmp/bin/uv"
chmod +x "$tmp/bin/uv"
git init -q "$tmp/repo"
cd "$tmp/repo"
git config core.hooksPath .githooks
mkdir -p .githooks scripts
cp "$root"/.githooks/* .githooks/
cp "$root/scripts/check-commit-msg.sh" scripts/
for hook in pre-commit commit-msg pre-push; do
  printf '#!/bin/sh\nexit 42\n' > ".git/hooks/$hook"
  chmod +x ".git/hooks/$hook"
done
printf 'fix: verify hook chaining\n' > message
for hook in pre-commit commit-msg pre-push; do
  status=0
  PATH="$tmp/bin:$PATH" ".githooks/$hook" message </dev/null || status=$?
  [ "$status" -eq 42 ] || { echo "$hook failed to chain: $status"; exit 1; }
done
echo 'All shared hooks propagate local guard rejection.'
