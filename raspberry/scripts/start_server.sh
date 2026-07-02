#!/usr/bin/env bash
set -e

cd "$(dirname "$0")/../app"
source ../venv/bin/activate

MODEL_FILE="../.runtime/model_path"
TELEGRAM_FILE="../.runtime/telegram_env"
if [[ -s "$MODEL_FILE" ]]; then
  MODEL_PATH="$(cat "$MODEL_FILE")"
  if [[ "$MODEL_PATH" != /* ]]; then
    MODEL_PATH="$(realpath -m "$MODEL_PATH")"
  fi
  export DEFAULT_MODEL="$MODEL_PATH"
fi

if [[ -s "$TELEGRAM_FILE" ]]; then
  # shellcheck disable=SC1090
  source "$TELEGRAM_FILE"
  export TELEGRAM_BOT_TOKEN TELEGRAM_CHAT_ID
fi

python server.py
