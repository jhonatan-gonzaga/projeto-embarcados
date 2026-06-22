#!/usr/bin/env bash

set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RASPBERRY_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
APP_DIR="$RASPBERRY_DIR/app"
RUNTIME_DIR="$RASPBERRY_DIR/.runtime"
MODEL_FILE="$RUNTIME_DIR/model_path"
TELEGRAM_FILE="$RUNTIME_DIR/telegram_env"
DEFAULT_MODEL_REL="../models/yolo11_openvino_model"
DEFAULT_TELEGRAM_BOT_TOKEN="8603600730:AAGuxOCxPqUJdS5fAted2WJHH-rjWPFNT10"
DEFAULT_TELEGRAM_CHAT_ID="6728036525"
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

load_telegram_env() {
  if [[ -s "$TELEGRAM_FILE" ]]; then
    # shellcheck disable=SC1090
    source "$TELEGRAM_FILE"
    export TELEGRAM_BOT_TOKEN TELEGRAM_CHAT_ID
  fi
}

telegram_configured() {
  load_telegram_env
  if [[ -z "${TELEGRAM_BOT_TOKEN:-}" ]]; then
    export TELEGRAM_BOT_TOKEN="$DEFAULT_TELEGRAM_BOT_TOKEN"
  fi
  if [[ -z "${TELEGRAM_CHAT_ID:-}" ]]; then
    export TELEGRAM_CHAT_ID="$DEFAULT_TELEGRAM_CHAT_ID"
  fi
  [[ -n "${TELEGRAM_BOT_TOKEN:-}" && -n "${TELEGRAM_CHAT_ID:-}" ]]
}

configure_telegram() {
  local bot_token chat_id current_token current_chat
  load_telegram_env
  current_token="${TELEGRAM_BOT_TOKEN:-}"
  current_chat="${TELEGRAM_CHAT_ID:-}"

  echo "Configuracao Telegram"
  if [[ -n "$current_token" ]]; then
    echo "Token atual: configurado"
  else
    echo "Token atual: usando padrao do codigo"
  fi
  if [[ -n "$current_chat" ]]; then
    echo "Chat ID atual: $current_chat"
  else
    echo "Chat ID atual: usando padrao do codigo"
  fi
  echo

  read -r -p "Token do Bot Telegram [manter atual]: " bot_token
  read -r -p "Chat ID Telegram [manter atual]: " chat_id

  bot_token="${bot_token:-$current_token}"
  chat_id="${chat_id:-$current_chat}"

  if [[ -z "$bot_token" || -z "$chat_id" ]]; then
    echo "Token e Chat ID sao obrigatorios."
    return 1
  fi

  umask 077
  {
    printf 'TELEGRAM_BOT_TOKEN=%q\n' "$bot_token"
    printf 'TELEGRAM_CHAT_ID=%q\n' "$chat_id"
  } > "$TELEGRAM_FILE"

  export TELEGRAM_BOT_TOKEN="$bot_token"
  export TELEGRAM_CHAT_ID="$chat_id"
  echo "Telegram configurado em $TELEGRAM_FILE"
  echo "Se o servidor ja estiver ligado, reinicie para ele carregar a nova configuracao."
}

ensure_telegram_config() {
  if telegram_configured; then
    return 0
  fi

  echo "Telegram ainda nao configurado."
  echo "A opcao precisa de TELEGRAM_BOT_TOKEN e TELEGRAM_CHAT_ID."
  configure_telegram
}

ensure_deps_hint() {
  local py
  py="$(python_bin)"
  if "$py" - <<'PY' >/dev/null 2>&1
import depthai, cv2, ultralytics, openvino, flask, requests
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

ensure_telegram_deps_hint() {
  local py
  py="$(python_bin)"
  if "$py" - <<'PY' >/dev/null 2>&1
import requests
PY
  then
    return 0
  fi

  echo "Dependencia Python 'requests' nao encontrada no ambiente atual."
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
  load_telegram_env

  echo "Servidor Flask em: http://0.0.0.0:${SERVER_PORT}"
  echo "Modelo padrao: $model"
  if telegram_configured; then
    echo "Telegram: configurado"
  else
    echo "Telegram: nao configurado"
  fi
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

normal_lora_flow() {
  echo "Fluxo normal: LoRa/Heltec -> Raspberry -> OAK-D/YOLO -> Telegram."
  echo "A Raspberry ficara com o servidor ligado aguardando POST /lora_event"
  echo "com JSON: {\"temperatura\": 32.5, \"umidade\": 60.0}"
  echo
  load_telegram_env
  if ! telegram_configured; then
    echo "Aviso: TELEGRAM_BOT_TOKEN e/ou TELEGRAM_CHAT_ID nao estao configurados."
    echo "Sem essas variaveis, o alerta sera detectado, mas telegram_sent ficara false."
    echo
    read -r -p "Configurar Telegram agora? [S/n] " answer
    case "$answer" in
      n|N|nao|NAO) ;;
      *) configure_telegram || return ;;
    esac
  fi
  run_server
}

wait_lora_alert_flow() {
  echo "Fluxo de alerta real:"
  echo "1. LoRa/Heltec envia o sinal de alerta com temperatura e umidade via POST /lora_event."
  echo "2. Raspberry verifica crianca sozinha com OAK-D/YOLO."
  echo "3. Se confirmar ALERT_CHILD_ALONE, envia Telegram com imagem e os dados DHT22 recebidos da LoRa."
  echo
  telegram_configured
  run_server
}

send_lora_event_test() {
  local temperature humidity url
  if ! ensure_telegram_config; then
    return
  fi
  if server_is_up; then
    echo "Servidor detectado em $SERVER_URL."
    echo "Confira se ele foi iniciado depois da configuracao Telegram."
  else
    echo "Servidor nao respondeu em $SERVER_URL."
    echo "Use a opcao 5 para ligar o fluxo normal antes de simular o evento."
    return
  fi

  read -r -p "Temperatura DHT22 [32.5]: " temperature
  read -r -p "Umidade DHT22 [60.0]: " humidity
  temperature="${temperature:-32.5}"
  humidity="${humidity:-60.0}"
  url="$SERVER_URL/lora_event?duration=10&sample_interval=1.0&yolo_conf=0.25&debug_detections=true"

  echo "Enviando evento LoRa simulado para $url"
  curl -fsS \
    -H "Content-Type: application/json" \
    -d "{\"temperatura\":$temperature,\"umidade\":$humidity}" \
    "$url"
  echo
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
  echo "Modo padrao: servidor ligado aguardando POST /lora_event da LoRa."
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

test_telegram_notification() {
  if ! ensure_telegram_deps_hint; then
    return
  fi

  local default_image image_path temperature humidity bot_token chat_id
  default_image="$RASPBERRY_DIR/results/images/last_child_alert.jpg"

  read -r -p "Caminho da imagem [$default_image]: " image_path
  read -r -p "Temperatura para teste [38.5]: " temperature
  read -r -p "Umidade para teste [72.5]: " humidity

  image_path="${image_path:-$default_image}"
  temperature="${temperature:-38.5}"
  humidity="${humidity:-72.5}"

  if ! ensure_telegram_config; then
    return
  fi
  bot_token="$TELEGRAM_BOT_TOKEN"
  chat_id="$TELEGRAM_CHAT_ID"

  if (
    cd "$APP_DIR" || exit 1
    IMAGE_PATH="$image_path" \
    TEMPERATURE="$temperature" \
    HUMIDITY="$humidity" \
    TELEGRAM_BOT_TOKEN="$bot_token" \
    TELEGRAM_CHAT_ID="$chat_id" \
    "$(python_bin)" - <<'PY'
import logging
import os

from telegram_notifier import send_telegram_alert

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

sent = send_telegram_alert(
    image_path=os.environ["IMAGE_PATH"],
    temperature=os.environ["TEMPERATURE"],
    humidity=os.environ["HUMIDITY"],
    bot_token=os.environ["TELEGRAM_BOT_TOKEN"],
    chat_id=os.environ["TELEGRAM_CHAT_ID"],
)

print(f"telegram_sent={str(sent).lower()}")
raise SystemExit(0 if sent else 1)
PY
  ); then
    echo "Teste Telegram concluido com sucesso."
  else
    echo "Teste Telegram falhou. Verifique internet, token, chat_id e logs acima."
  fi
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
  echo "10 - Testar notificacao Telegram"
  echo "11 - Fluxo real: LoRa envia DHT22 -> verificar -> Telegram"
  echo "12 - Configurar Telegram"
  echo "13 - Simular evento LoRa DHT22 -> Raspberry"
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
      5) normal_lora_flow ;;
      6) view_results_image ;;
      7) echo "Saindo."; exit 0 ;;
      8) run_quick_observation ;;
      9) show_status ;;
      10) test_telegram_notification ;;
      11) wait_lora_alert_flow ;;
      12) configure_telegram ;;
      13) send_lora_event_test ;;
      *) echo "Opcao invalida." ;;
    esac
    pause_menu
  done
}
