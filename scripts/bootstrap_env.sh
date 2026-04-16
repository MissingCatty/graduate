#!/usr/bin/env bash

# Source this script to enter the project conda environment:
#   source scripts/bootstrap_env.sh

if [[ -z "${BASH_VERSION:-}" ]]; then
  echo "bootstrap_env.sh requires bash." >&2
  return 1 2>/dev/null || exit 1
fi

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  echo "Use 'source scripts/bootstrap_env.sh' so the conda environment stays active." >&2
fi

set -euo pipefail

ENV_NAME="${OPENING_PREEXP_ENV_NAME:-opening_preexp}"
DEFAULT_CONDA_BASE="/home/zyc/miniconda3"

if [[ -n "${CONDA_EXE:-}" ]]; then
  CONDA_BASE="$(dirname "$(dirname "$CONDA_EXE")")"
elif command -v conda >/dev/null 2>&1; then
  CONDA_BASE="$(conda info --base)"
else
  CONDA_BASE="$DEFAULT_CONDA_BASE"
fi

if [[ ! -f "$CONDA_BASE/etc/profile.d/conda.sh" ]]; then
  echo "conda.sh not found under $CONDA_BASE" >&2
  return 1 2>/dev/null || exit 1
fi

# shellcheck source=/dev/null
source "$CONDA_BASE/etc/profile.d/conda.sh"
conda activate "$ENV_NAME"

echo "Activated conda environment: $CONDA_DEFAULT_ENV"
echo "Python: $(python --version 2>&1)"
echo "Interpreter: $(command -v python)"
