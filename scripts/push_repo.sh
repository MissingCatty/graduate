#!/usr/bin/env bash

set -euo pipefail

REMOTE_NAME="origin"
REMOTE_URL=""
TARGET_BRANCH=""
COMMIT_MESSAGE=""
SKIP_COMMIT=0
DRY_RUN=0

usage() {
  cat <<'EOF'
Usage:
  bash scripts/push_repo.sh [options]

Options:
  --remote-url URL     Add/update the remote URL for origin on first use.
  --branch NAME        Push the specified branch. Defaults to the current branch.
  --message TEXT       Commit message to use when there are local changes.
  --skip-commit        Do not auto-stage/commit. Only push existing commits.
  --dry-run            Print the git commands without changing repo state.
  -h, --help           Show this help message.

Examples:
  bash scripts/push_repo.sh --remote-url git@github.com:you/repo.git
  bash scripts/push_repo.sh
  bash scripts/push_repo.sh --message "chore: sync latest progress"
  bash scripts/push_repo.sh --skip-commit

Behavior:
  1. If origin is not configured, pass --remote-url once to create it.
  2. By default, the script stages all non-ignored changes, creates a commit if needed,
     and pushes the current branch to origin.
  3. Once origin is configured, later runs can usually be a single command:
     bash scripts/push_repo.sh
EOF
}

die() {
  echo "Error: $*" >&2
  exit 1
}

run_cmd() {
  if [[ "${DRY_RUN}" -eq 1 ]]; then
    printf '[dry-run] '
    printf '%q ' "$@"
    printf '\n'
    return 0
  fi
  "$@"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --remote-url)
      [[ $# -ge 2 ]] || die "--remote-url requires a value"
      REMOTE_URL="$2"
      shift 2
      ;;
    --branch)
      [[ $# -ge 2 ]] || die "--branch requires a value"
      TARGET_BRANCH="$2"
      shift 2
      ;;
    --message)
      [[ $# -ge 2 ]] || die "--message requires a value"
      COMMIT_MESSAGE="$2"
      shift 2
      ;;
    --skip-commit)
      SKIP_COMMIT=1
      shift
      ;;
    --dry-run)
      DRY_RUN=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      die "Unknown option: $1"
      ;;
  esac
done

git rev-parse --is-inside-work-tree >/dev/null 2>&1 || die "Current directory is not a git repository"

if [[ -z "${TARGET_BRANCH}" ]]; then
  TARGET_BRANCH="$(git branch --show-current)"
fi
[[ -n "${TARGET_BRANCH}" ]] || die "Could not determine the current branch"

if git remote get-url "${REMOTE_NAME}" >/dev/null 2>&1; then
  CURRENT_REMOTE_URL="$(git remote get-url "${REMOTE_NAME}")"
  if [[ -n "${REMOTE_URL}" && "${REMOTE_URL}" != "${CURRENT_REMOTE_URL}" ]]; then
    echo "Updating ${REMOTE_NAME} from ${CURRENT_REMOTE_URL} to ${REMOTE_URL}"
    run_cmd git remote set-url "${REMOTE_NAME}" "${REMOTE_URL}"
  fi
else
  [[ -n "${REMOTE_URL}" ]] || die "Remote '${REMOTE_NAME}' is not configured. Re-run with --remote-url <url>."
  echo "Adding ${REMOTE_NAME}: ${REMOTE_URL}"
  run_cmd git remote add "${REMOTE_NAME}" "${REMOTE_URL}"
fi

if [[ "${SKIP_COMMIT}" -eq 0 ]]; then
  if ! git config --get user.name >/dev/null 2>&1; then
    die "git user.name is not set. Run: git config user.name \"Your Name\""
  fi
  if ! git config --get user.email >/dev/null 2>&1; then
    die "git user.email is not set. Run: git config user.email \"you@example.com\""
  fi

  run_cmd git add -A

  if git diff --cached --quiet; then
    echo "No local changes to commit."
  else
    if [[ -z "${COMMIT_MESSAGE}" ]]; then
      COMMIT_MESSAGE="chore: sync repo $(date '+%Y-%m-%d %H:%M:%S')"
    fi
    echo "Creating commit: ${COMMIT_MESSAGE}"
    run_cmd git commit -m "${COMMIT_MESSAGE}"
  fi
else
  echo "Skipping auto-commit. Only pushing existing commits."
fi

echo "Pushing branch '${TARGET_BRANCH}' to '${REMOTE_NAME}'"
run_cmd git push -u "${REMOTE_NAME}" "${TARGET_BRANCH}"

echo "Done."
