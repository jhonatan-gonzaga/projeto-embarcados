#!/usr/bin/env bash

set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RASPBERRY_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
APP_DIR="$RASPBERRY_DIR/app"
RUNTIME_DIR="$RASPBERRY_DIR/.runtime"
MODEL_FILE="$RUNTIME_DIR/model_path"
DEFAULT_MODEL_REL="../models/yolo11_openvino_model"
SERVER_PORT="${SERVER_PORT:-5000}"
SERVER_URL="${SERVER_URL:-http://127.0.0.1:${SERVER_PORT}}"

mkdir -p "$RUNTIME_DIR"

platform_name="${PLATFORM_NAME:-Sistema}"
camera_display_default="${CAMERA_DISPLAY_DEFAULT:-1}"

pause_menu() {
  echo
  read -r -p "Pressione Enter para voltar ao menu..."
}

python_bin() {
  if [[ -x "$RASPBERRY_DIR/venv/bin/python" ]]; then
    printf '%s\n' "$RASPBERRY_DIR/venv/bin/python"
    return
  fi

  if command -v python3 >/dev/null 2>&1; then
    command -v python3
    return
  fi

  command -v python
}

selected_model() {
  if [[ -s "$MODEL_FILE" ]]; then
    cat "$MODEL_FILE"
  else
    printf '%s\n' "$DEFAULT_MODEL_REL"
  fi
}

selected_model_abs() {
  local model
  model="$(selected_model)"
  if [[ "$model" = /* ]]; then
    printf '%s\n' "$model"
  else
    (cd "$APP_DIR" && realpath -m "$model")
  fi
}

selected_model_for_app() {
  local model
  model="$(selected_model)"
  if [[ "$model" = /* ]]; then
    printf '%s\n' "$model"
  else
    printf '%s\n' "$model"
  fi
}

ensure_deps_hint() {
  local py
  py="$(python_bin)"
  if "$py" - <<'PY' >/dev/null 2>&1
import depthai, cv2, ultralytics, openvino, flask
PY
  then
    return 0
  fi

  echo "Dependencias Python nao encontradas no ambiente atual."
  echo "Execute primeiro:"
  echo "  cd raspberry"
  echo "  ./scripts/install.sh"
  return 1
}

server_is_up() {
  curl -fsS "$SERVER_URL/health" >/dev/null 2>&1
}

run_server() {
  if ! ensure_deps_hint; then
    return
  fi

  local py model
  py="$(python_bin)"
  model="$(selected_model_abs)"

  echo "Servidor Flask em: http://0.0.0.0:${SERVER_PORT}"
  echo "Modelo padrao: $model"
  echo "Use Ctrl+C para encerrar."
  (
    cd "$APP_DIR" || exit 1
    DEFAULT_MODEL="$model" "$py" main.py
  )
}

check_oakd() {
  if ! ensure_deps_hint; then
    return
  fi

  (cd "$APP_DIR" && "$(python_bin)" oakd_check.py)
}

check_lora() {
  echo "Verificando servidor em $SERVER_URL..."
  if ! server_is_up; then
    echo "Servidor nao respondeu. Use a opcao 0 ou 5 para ligar o servidor."
    return
  fi

  echo "Servidor OK."
  echo "Ultimo pacote de sensores recebido da Heltec/LoRa:"
  if ! curl -fsS "$SERVER_URL/latest_sensor_data"; then
    echo
    echo "Nenhum pacote ainda. Envie dados pela Heltec ou rode o teste_sensor_data."
  fi

  echo
  read -r -p "Aguardar pacote novo por 60s? [s/N] " answer
  case "$answer" in
    s|S|sim|SIM)
      local i
      for i in $(seq 1 60); do
        if curl -fsS "$SERVER_URL/latest_sensor_data"; then
          echo
          echo "LoRa/sensor respondeu."
          return
        fi
        sleep 1
      done
      echo "Tempo esgotado sem novo pacote."
      ;;
  esac
}

test_camera_30s() {
  if ! ensure_deps_hint; then
    return
  fi

  local display_flag=()
  if [[ "$camera_display_default" != "1" ]]; then
    display_flag=(--no-display)
  fi

  (cd "$APP_DIR" && "$(python_bin)" oakd_camera_test.py --duration 30 "${display_flag[@]}")
}

switch_model() {
  echo "Modelos encontrados em raspberry/models:"
  mapfile -t models < <(find "$RASPBERRY_DIR/models" -maxdepth 1 -mindepth 1 -type d | sort)
  local i
  for i in "${!models[@]}"; do
    printf "%d - %s\n" "$((i + 1))" "${models[$i]#$RASPBERRY_DIR/}"
  done
  echo "0 - Digitar caminho manual"
  echo
  read -r -p "Escolha o modelo: " choice

  local model=""
  if [[ "$choice" == "0" ]]; then
    read -r -p "Caminho do modelo (.pt ou pasta OpenVINO): " model
  elif [[ "$choice" =~ ^[0-9]+$ ]] && (( choice >= 1 && choice <= ${#models[@]} )); then
    model="${models[$((choice - 1))]}"
  else
    echo "Opcao invalida."
    return
  fi

  if [[ -z "$model" ]]; then
    echo "Modelo vazio."
    return
  fi

  if [[ ! -e "$model" ]]; then
    echo "Modelo nao encontrado: $model"
    return
  fi

  if [[ "$model" = "$APP_DIR"/* ]]; then
    model="$(realpath --relative-to="$APP_DIR" "$model")"
  elif [[ "$model" = "$RASPBERRY_DIR"/* ]]; then
    model="../$(realpath --relative-to="$RASPBERRY_DIR" "$model")"
  fi

  printf '%s\n' "$model" > "$MODEL_FILE"
  echo "Modelo selecionado: $model"
  echo "Reinicie o servidor para usar esse modelo como padrao da LoRa."
}

default_mode() {
  echo "Modo padrao: servidor ligado aguardando a LoRa chamar /check_car."
  run_server
}

view_results_image() {
  local image="$RASPBERRY_DIR/results/images/last_child_alert.jpg"
  if [[ ! -f "$image" ]]; then
    echo "Imagem nao encontrada: $image"
    return
  fi

  echo "Imagem: $image"
  if command -v xdg-open >/dev/null 2>&1; then
    xdg-open "$image" >/dev/null 2>&1 &
  elif command -v feh >/dev/null 2>&1; then
    feh "$image" >/dev/null 2>&1 &
  elif command -v display >/dev/null 2>&1; then
    display "$image" >/dev/null 2>&1 &
  else
    echo "Nao encontrei xdg-open/feh/display. Abra manualmente o arquivo acima."
  fi
}

run_quick_observation() {
  if ! ensure_deps_hint; then
    return
  fi

  local duration sample conf model
  read -r -p "Duracao em segundos [10]: " duration
  read -r -p "Intervalo entre amostras [1.0]: " sample
  read -r -p "Confianca bruta YOLO [0.25]: " conf
  duration="${duration:-10}"
  sample="${sample:-1.0}"
  conf="${conf:-0.25}"
  model="$(selected_model_for_app)"

  (
    cd "$APP_DIR" || exit 1
    "$(python_bin)" oakd_observation_test.py \
      --model "$model" \
      --duration "$duration" \
      --sample-interval "$sample" \
      --no-display \
      --yolo-conf "$conf" \
      --save-best-frame \
      --debug-detections
  )
}

show_status() {
  if server_is_up; then
    echo "Servidor: OK"
    echo "Status:"
    curl -fsS "$SERVER_URL/status" || true
    echo
    echo "Ultimo resultado:"
    curl -fsS "$SERVER_URL/last_result" || true
    echo
  else
    echo "Servidor: desligado ou inacessivel em $SERVER_URL"
  fi
  echo "Modelo selecionado: $(selected_model)"
}

show_menu() {
  clear 2>/dev/null || true
  echo "===== Menu $platform_name - OAK-D / YOLO / LoRa ====="
  echo "Modelo selecionado: $(selected_model)"
  echo
  echo "0 - Ligar servidor"
  echo "1 - Verificar conexao com OAK-D"
  echo "2 - Verificar conexao com LoRa/sensores"
  echo "3 - Testar somente a camera por 30 segundos"
  echo "4 - Trocar modelo YOLO"
  echo "5 - Modo padrao: aguardar LoRa enviar sinal"
  echo "6 - Ver imagem do results"
  echo "7 - Sair"
  echo "8 - Rodar observacao rapida manual"
  echo "9 - Ver status do servidor/ultimo resultado"
  echo
}

main_menu() {
  while true; do
    show_menu
    read -r -p "Escolha uma opcao: " option
    echo
    case "$option" in
      0) run_server ;;
      1) check_oakd ;;
      2) check_lora ;;
      3) test_camera_30s ;;
      4) switch_model ;;
      5) default_mode ;;
      6) view_results_image ;;
      7) echo "Saindo."; exit 0 ;;
      8) run_quick_observation ;;
      9) show_status ;;
      *) echo "Opcao invalida." ;;
    esac
    pause_menu
  done
}
