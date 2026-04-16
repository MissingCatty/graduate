#!/usr/bin/env bash
# Source this script to enter the project conda environment:
#   source scripts/activate_env.sh
#
# Convenience wrapper around bootstrap_env.sh.
if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  echo "Use 'source scripts/activate_env.sh' so the conda environment stays active." >&2
fi

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/bootstrap_env.sh"
