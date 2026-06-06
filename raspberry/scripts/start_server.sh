#!/usr/bin/env bash
set -e

cd "$(dirname "$0")/../app"
source ../venv/bin/activate
python server.py
