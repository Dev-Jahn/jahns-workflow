#!/usr/bin/env bash
# release-to-main.sh — sync dev's shipping subset onto main without touching the caller's tree.
#
# Branch model (see README): dev = integration branch (the test suite and this tooling live
# here); main = release branch carrying the plugin runtime only. The marketplace pins main.
# The positive manifest below is the complete shipping surface; unlisted paths stay dev-only.
#
# Usage:  ./release-to-main.sh
#   Runs the dev test gate, then commits the projected tree onto main. Does NOT push — review the
#   commit, then `git push origin main` and bump the marketplace sha to it.
set -euo pipefail

SHIP_PATHS=(
  .claude-plugin
  .codex-plugin
  .github
  .gitignore
  LICENSE
  README.md
  assets
  bin
  hooks
  references
  scripts/cclog.py
  scripts/codexlog.py
  scripts/common.py
  scripts/dashboard.py
  scripts/delegate.py
  scripts/improve.py
  scripts/lanes.py
  scripts/merge.py
  scripts/overlay.py
  scripts/remote.py
  scripts/resume.py
  scripts/review.py
  scripts/roadmap.py
  scripts/round.py
  scripts/ssot.py
  scripts/tasks.py
  scripts/validate.py
  scripts/waystone.py
  skills
  templates
)

cd "$(git rev-parse --show-toplevel)"

worktree_list=$(git worktree list --porcelain)
main_worktree=""
worktree_path=""
while IFS= read -r line; do
  case "$line" in
    "worktree "*) worktree_path=${line#worktree } ;;
    "branch refs/heads/main") main_worktree=$worktree_path; break ;;
  esac
done <<< "$worktree_list"
if [ -n "$main_worktree" ]; then
  echo "release: refs/heads/main is checked out at $main_worktree — aborting." >&2
  exit 1
fi

if [ -n "$(git status --porcelain)" ]; then
  echo "release: working tree not clean — commit or stash first." >&2
  exit 1
fi

dev_oid=$(git rev-parse --verify 'dev^{commit}')
dev_sha=$(git rev-parse --short "$dev_oid")
main_oid=$(git rev-parse --verify 'refs/heads/main^{commit}')
tmpdir=$(mktemp -d "${TMPDIR:-/tmp}/waystone-release.XXXXXX")
test_worktree="$tmpdir/dev"
release_index="$tmpdir/index"

cleanup() {
  local status=$?
  local cleanup_status=0
  trap - EXIT HUP INT TERM
  set +e
  if [ -e "$test_worktree/.git" ]; then
    if ! git worktree remove --force "$test_worktree"; then
      echo "release: failed to remove temporary worktree; state kept at $tmpdir." >&2
      cleanup_status=1
    fi
  fi
  if [ "$cleanup_status" -eq 0 ] && ! rm -rf -- "$tmpdir"; then
    echo "release: failed to remove temporary state at $tmpdir." >&2
    cleanup_status=1
  fi
  if [ "$status" -eq 0 ]; then
    status=$cleanup_status
  fi
  exit "$status"
}
trap cleanup EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM

# Run the gate against the exact dev commit being projected, in an isolated worktree.
git worktree add --detach -q "$test_worktree" "$dev_oid"
echo "release: running the test suite on dev…"
if ! (cd "$test_worktree" && uv run scripts/tests/run_tests.py); then
  echo "release: tests failed on dev — aborting." >&2
  exit 1
fi

# Build the release tree in a temporary index from positive-manifest paths only.
GIT_INDEX_FILE="$release_index" git read-tree --empty
git ls-tree -r -z "$dev_oid" -- "${SHIP_PATHS[@]}" |
  GIT_INDEX_FILE="$release_index" git update-index -z --index-info
release_tree=$(GIT_INDEX_FILE="$release_index" git write-tree)
main_tree=$(git rev-parse "$main_oid^{tree}")

if [ "$release_tree" = "$main_tree" ]; then
  echo "release: main already in sync with dev@${dev_sha} — nothing to release."
  exit 0
fi

commit_args=(commit-tree "$release_tree" -p "$main_oid" -m "release: sync from dev@${dev_sha}")
if git config --get-regexp '^commit\.gpgsign$' >/dev/null; then
  commit_gpgsign=$(git config --bool --get commit.gpgsign)
  if [ "$commit_gpgsign" = "true" ]; then
    commit_args+=(-S)
  fi
fi
release_commit=$(git "${commit_args[@]}")
git update-ref -m "release: sync from dev@${dev_sha}" \
  refs/heads/main "$release_commit" "$main_oid"

echo "release: main @ $(git rev-parse --short "$release_commit") built from dev@${dev_sha}."
echo "next:    git push origin main   then bump the marketplace sha to this commit."
