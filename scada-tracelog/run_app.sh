#!/bin/bash
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

if [ -f "/home/longp/miniconda3/bin/activate" ]; then
    source /home/longp/miniconda3/bin/activate company-env
fi

python main.py
