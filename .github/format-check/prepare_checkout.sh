#!/usr/bin/env bash
# Print trusted base SHA. Fail before running any code from a contribution.
set -euo pipefail

event=$1
expected_head=$2
pr_number=$3

if [[ ! $expected_head =~ ^[0-9a-f]{40}$ || ! $pr_number =~ ^[0-9]{1,9}$ ]]; then
  echo 'Invalid pull request identity' >&2
  exit 1
fi

if [[ $event != workflow_dispatch && $event != pull_request_target ]]; then
  echo 'Unsupported workflow event' >&2
  exit 1
fi

# Both events start on trusted main, not on the contribution's branch.
base=$(git rev-parse HEAD)
if [[ $base != $(git rev-parse refs/remotes/origin/main) ]]; then
  echo 'Checkout is not current main' >&2
  exit 1
fi
actual_head=$(git rev-parse "refs/pull/$pr_number/head")
if [[ $actual_head != "$expected_head" ]]; then
  echo 'Pull request head changed before checkout' >&2
  exit 1
fi
git -c user.name='github-actions[bot]' -c user.email='41898282+github-actions[bot]@users.noreply.github.com' \
  merge --no-ff --no-edit -m 'Format-check temporary merge' "$actual_head" >/dev/null || {
  echo 'Cannot merge pull request into main' >&2
  exit 1
}

# Never run contributor versions of workflows, dependencies, or checker code.
# HEAD stays the candidate merge for the checker diff; the worktree runs main's
# automation even when a maintainer contributes an update to that automation.
git restore --source="$base" --staged --worktree -- .github
git clean -fd -- .github >/dev/null

echo "$base"
