#!/bin/bash
# Helper script to run the dialogue generation system with the virtual environment

cd "$(dirname "$0")"
.venv/bin/python main.py "$@"


