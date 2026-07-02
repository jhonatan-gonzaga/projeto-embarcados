#!/usr/bin/env bash

set -euo pipefail

export PLATFORM_NAME="Raspberry Pi"
export CAMERA_DISPLAY_DEFAULT="${CAMERA_DISPLAY_DEFAULT:-0}"

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/scripts/menu_common.sh"

main_menu
