#!/usr/bin/env bash
set -e

cd "$(dirname "$0")/../app"
source ../venv/bin/activate

MODEL_FILE="../.runtime/model_path"
if [[ -s "$MODEL_FILE" ]]; then
  MODEL_PATH="$(cat "$MODEL_FILE")"
  if [[ "$MODEL_PATH" != /* ]]; then
    MODEL_PATH="$(realpath -m "$MODEL_PATH")"
  fi
  export DEFAULT_MODEL="$MODEL_PATH"
fi

python server.py
