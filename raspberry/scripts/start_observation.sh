#!/usr/bin/env bash
set -e

cd "$(dirname "$0")/../app"
source ../venv/bin/activate
python oakd_observation_test.py \
  --model ../models/yolo11_openvino_model
