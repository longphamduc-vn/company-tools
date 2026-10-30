#!/usr/bin/env bash
set -e

# Change directory to project root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Conda environment check
if command -v conda &> /dev/null; then
    eval "$(conda shell.bash hook)"
    if conda info --envs | grep -q "company-env"; then
        echo "Activating conda environment 'company-env'..."
        conda activate company-env
    fi
fi

# Run application
python main.py "$@"
