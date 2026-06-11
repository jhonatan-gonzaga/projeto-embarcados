"""
Aplicacao principal Flask do sistema Raspberry Pi 5 + OAK-D.

Responsabilidades:
- receber acionamento de observacao;
- executar observacao OAK-D/YOLO em background;
- receber dados simulados de sensores;
- expor ultimo resultado e ultima imagem;
- chamar mensagemTelegram(imagem, co2, temperatura, humidade) quando houver alerta.
"""

import logging
import os
import threading

from flask import Flask, jsonify, request, send_file

from modules.observation import (
    executar_observacao_background,
    get_last_result,
    get_status,
    montar_comando_observacao,
    set_running_if_idle,
)
from modules.sensors import obter_latest_sensor_data, salvar_sensor_data
from modules.storage import (
    DEFAULT_DURATION,
    DEFAULT_MODEL,
    DEFAULT_SAMPLE_INTERVAL,
    LAST_ALERT_IMAGE_PATH,
    montar_image_info,
    obter_caminho_imagem_alerta,
)
from modules.telegram_alert import mensagemTelegram


app = Flask(__name__)
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("oakd_child_alert")


def bool_arg(name, default=False):
    """Le argumentos booleanos de query string."""
    raw_value = request.args.get(name)
    if raw_value is None:
        return default
    return raw_value.strip().lower() in {"1", "true", "yes", "on"}


def processar_alerta_pos_observacao(result, summary):
    """Chama o stub de Telegram apos uma observacao com alerta confirmado."""
    if result.get("final_decision") != "ALERT_CHILD_ALONE":
        return result

    sensor_data = obter_latest_sensor_data() or {}
    image_path = obter_caminho_imagem_alerta(summary)

    telegram_sent = mensagemTelegram(
        str(image_path),
        sensor_data.get("co2"),
        sensor_data.get("temperatura"),
        sensor_data.get("humidade"),
    )
    result["telegram_sent"] = bool(telegram_sent)
    return result


@app.get("/health")
def health():
    """Endpoint simples para verificar se o Flask esta ativo."""
    logger.info("GET /health")
    return jsonify({"status": "ok"})


@app.post("/sensor_data")
def receber_sensor_data():
    """Recebe dados simulados de sensores enviados pela Heltec/ESP32."""
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        logger.warning("POST /sensor_data com JSON ausente ou invalido.")
        return jsonify({"status": "INVALID_JSON"}), 400

    try:
        sensor_data = salvar_sensor_data(data)
    except ValueError as error:
        logger.warning("POST /sensor_data invalido: %s", error)
        return jsonify({"status": "INVALID_DATA", "error": str(error)}), 400

    logger.info(
        "POST /sensor_data -> co2=%.2f temperatura=%.2f humidade=%.2f",
        sensor_data["co2"],
        sensor_data["temperatura"],
        sensor_data["humidade"],
    )
    return jsonify({"status": "OK"})


@app.get("/latest_sensor_data")
def get_latest_sensor_data():
    """Retorna o ultimo pacote de sensores simulados recebido."""
    sensor_data = obter_latest_sensor_data()
    if sensor_data is None:
        logger.info("GET /latest_sensor_data -> NO_SENSOR_DATA")
        return jsonify({"status": "NO_SENSOR_DATA"}), 404

    logger.info("GET /latest_sensor_data -> OK")
    return jsonify(sensor_data)


@app.get("/status")
def status():
    """Retorna estado atual da observacao."""
    current_status = get_status()
    logger.info("GET /status -> %s", current_status)
    return jsonify({"status": current_status})


@app.get("/last_result")
def get_last_result_endpoint():
    """Retorna o ultimo resultado final salvo em memoria."""
    result = get_last_result()
    if result is None:
        logger.info("GET /last_result -> NO_RESULT")
        return jsonify({"status": "NO_RESULT"}), 404

    logger.info("GET /last_result -> %s", result.get("final_decision"))
    return jsonify(result)


@app.get("/last_image")
def get_last_image():
    """Retorna a imagem salva do ultimo alerta confirmado."""
    if not LAST_ALERT_IMAGE_PATH.exists():
        logger.info("GET /last_image -> NO_IMAGE")
        return jsonify({"status": "NO_IMAGE"}), 404

    logger.info("GET /last_image -> %s", LAST_ALERT_IMAGE_PATH)
    return send_file(LAST_ALERT_IMAGE_PATH, mimetype="image/jpeg")


@app.get("/image_info")
def get_image_info():
    """Retorna metadados do melhor frame child salvo."""
    info = montar_image_info()
    logger.info("GET /image_info -> exists=%s conf=%.4f", info["exists"], info["best_child_conf"])
    return jsonify(info)


@app.get("/check_car")
def check_car():
    """Inicia a observacao em background, ou informa BUSY se ja estiver rodando."""
    try:
        duration = float(request.args.get("duration", DEFAULT_DURATION))
        sample_interval = float(request.args.get("sample_interval", DEFAULT_SAMPLE_INTERVAL))
        yolo_conf = float(request.args.get("yolo_conf", 0.25))
    except ValueError:
        logger.warning("GET /check_car com argumentos invalidos: %s", request.query_string.decode())
        return jsonify({"status": "INVALID_ARGUMENTS"}), 400

    if duration <= 0 or sample_interval <= 0:
        logger.warning(
            "GET /check_car com valores fora do intervalo: duration=%s sample_interval=%s",
            duration,
            sample_interval,
        )
        return jsonify({"status": "INVALID_ARGUMENTS"}), 400
    if not 0.0 <= yolo_conf <= 1.0:
        logger.warning("GET /check_car com yolo_conf invalido: %s", yolo_conf)
        return jsonify({"status": "INVALID_ARGUMENTS"}), 400

    if not set_running_if_idle():
        logger.info("GET /check_car -> BUSY")
        return jsonify({"status": "BUSY"})

    model = request.args.get("model", str(DEFAULT_MODEL))
    debug_detections = bool_arg("debug_detections", False)
    command = montar_comando_observacao(
        model,
        duration,
        sample_interval,
        yolo_conf,
        debug_detections=debug_detections,
    )

    thread = threading.Thread(
        target=executar_observacao_background,
        args=(command, duration + 90, processar_alerta_pos_observacao, logger),
        daemon=True,
    )
    thread.start()

    logger.info(
        "GET /check_car -> CHECK_STARTED duration=%.1f sample_interval=%.2f yolo_conf=%.2f debug=%s",
        duration,
        sample_interval,
        yolo_conf,
        debug_detections,
    )
    return jsonify({"status": "CHECK_STARTED"})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, threaded=True)
