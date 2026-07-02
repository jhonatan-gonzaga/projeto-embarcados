#!/usr/bin/env bash

set -euo pipefail

export PLATFORM_NAME="Manjaro"
export CAMERA_DISPLAY_DEFAULT="1"

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/scripts/menu_common.sh"

main_menu
