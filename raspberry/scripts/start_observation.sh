#!/usr/bin/env bash
set -e

cd "$(dirname "$0")/../app"
source ../venv/bin/activate

MODEL_FILE="../.runtime/model_path"
MODEL_PATH="../models/yolo11_openvino_model"
if [[ -s "$MODEL_FILE" ]]; then
  MODEL_PATH="$(cat "$MODEL_FILE")"
fi

python oakd_observation_test.py \
  --model "$MODEL_PATH"
