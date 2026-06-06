"""
Servidor Flask para acionar o modo de observacao da OAK-D sem travar a API.

Exemplos:
python server.py
curl http://localhost:5000/health
curl http://localhost:5000/status
curl http://localhost:5000/check_car
curl http://localhost:5000/last_result
"""

import os
import logging
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from flask import Flask, jsonify, request, send_file


APP_DIR = Path(__file__).resolve().parent
RESULTS_DIR = APP_DIR / "../results"
SUMMARY_PATH = RESULTS_DIR / "reports/oakd_observation_summary.txt"
LAST_ALERT_IMAGE_PATH = RESULTS_DIR / "images/last_child_alert.jpg"
DEFAULT_MODEL = APP_DIR / "../models/best_yolov8n_openvino_model"
DEFAULT_DURATION = 180
DEFAULT_SAMPLE_INTERVAL = 1.0
INTERNET_TEST_URL = "https://api.telegram.org"
INTERNET_TIMEOUT_SECONDS = 3

app = Flask(__name__)
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("oakd_child_alert")

state_lock = threading.Lock()
server_state = "IDLE"
last_result = None
current_process = None


def tem_internet():
    """Verifica conexao com internet sem travar a API por muito tempo."""
    try:
        request_obj = urllib.request.Request(
            INTERNET_TEST_URL,
            headers={"User-Agent": "raspberry-oakd-child-alert/1.0"},
        )
        with urllib.request.urlopen(request_obj, timeout=INTERNET_TIMEOUT_SECONDS):
            return True
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        logger.info("Internet indisponivel: %s", error)
        return False


def converter_valor(value):
    """Converte strings numericas do resumo para float/int quando possivel."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return value

    return int(number) if number.is_integer() else number


def ler_resumo():
    """Le o resumo TXT gerado pelo modo de observacao."""
    if not SUMMARY_PATH.exists():
        return {}

    data = {}
    with SUMMARY_PATH.open("r", encoding="utf-8") as file:
        for line in file:
            if ":" not in line:
                continue
            key, value = line.strip().split(":", 1)
            data[key.strip()] = converter_valor(value.strip())

    return data


def ler_tail(file_obj, max_chars=4000):
    """Le apenas o fim de um arquivo temporario de log."""
    file_obj.flush()
    file_obj.seek(0, os.SEEK_END)
    end_pos = file_obj.tell()
    file_obj.seek(max(0, end_pos - max_chars))
    return file_obj.read()


def resumo_float(summary, key):
    """Retorna campo numerico do resumo com fallback para 0.0."""
    value = summary.get(key, 0.0)
    return float(value) if isinstance(value, (int, float)) else 0.0


def obter_caminho_imagem_alerta(summary):
    """Obtem a imagem do ultimo alerta validando o caminho salvo."""
    raw_path = summary.get("alert_image_path") or str(LAST_ALERT_IMAGE_PATH)
    image_path = Path(str(raw_path))
    if not image_path.is_absolute():
        image_path = APP_DIR / image_path
    return image_path.resolve()


def enviar_telegram_mensagem(texto):
    """Envia mensagem Telegram usando TELEGRAM_BOT_TOKEN e TELEGRAM_CHAT_ID."""
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        raise RuntimeError("TELEGRAM_BOT_TOKEN ou TELEGRAM_CHAT_ID nao configurado.")

    payload = urllib.parse.urlencode({"chat_id": chat_id, "text": texto}).encode("utf-8")
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    request_obj = urllib.request.Request(url, data=payload, method="POST")

    with urllib.request.urlopen(request_obj, timeout=10) as response:
        return response.status == 200


def enviar_telegram_imagem(image_path, caption=""):
    """Envia imagem Telegram por multipart/form-data sem dependencia extra."""
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        raise RuntimeError("TELEGRAM_BOT_TOKEN ou TELEGRAM_CHAT_ID nao configurado.")
    if not image_path.exists():
        raise FileNotFoundError(f"Imagem de alerta nao encontrada: {image_path}")

    boundary = f"----oakd-alert-{int(time.time() * 1000)}"
    image_bytes = image_path.read_bytes()
    filename = image_path.name

    fields = [
        ("chat_id", chat_id.encode("utf-8")),
        ("caption", caption.encode("utf-8")),
    ]

    body = bytearray()
    for name, value in fields:
        body.extend(f"--{boundary}\r\n".encode("utf-8"))
        body.extend(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode("utf-8"))
        body.extend(value)
        body.extend(b"\r\n")

    body.extend(f"--{boundary}\r\n".encode("utf-8"))
    body.extend(
        (
            f'Content-Disposition: form-data; name="photo"; filename="{filename}"\r\n'
            "Content-Type: image/jpeg\r\n\r\n"
        ).encode("utf-8")
    )
    body.extend(image_bytes)
    body.extend(b"\r\n")
    body.extend(f"--{boundary}--\r\n".encode("utf-8"))

    url = f"https://api.telegram.org/bot{token}/sendPhoto"
    request_obj = urllib.request.Request(
        url,
        data=bytes(body),
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )

    with urllib.request.urlopen(request_obj, timeout=15) as response:
        return response.status == 200


def enviar_alerta_telegram(summary):
    """Envia texto e imagem quando houver alerta confirmado."""
    image_path = obter_caminho_imagem_alerta(summary)
    texto = (
        "ALERTA: crianca possivelmente sozinha no veiculo.\n"
        f"child_presence_ratio: {resumo_float(summary, 'child_presence_ratio'):.4f}\n"
        f"adult_presence_ratio: {resumo_float(summary, 'adult_presence_ratio'):.4f}\n"
        f"child_avg_conf: {resumo_float(summary, 'child_avg_conf'):.4f}"
    )

    enviar_telegram_mensagem(texto)
    enviar_telegram_imagem(image_path, "Imagem do alerta OAK-D")
    logger.info("Alerta Telegram enviado com imagem: %s", image_path)
    return True


def montar_last_result(summary, stdout=""):
    """Monta o JSON publico do ultimo resultado."""
    final_decision = summary.get("final_decision")
    if final_decision is None and "OAK-D nao encontrada" in stdout:
        final_decision = "OAKD_NOT_FOUND"
    elif final_decision is None:
        final_decision = "ERROR"
        logger.warning("Resumo da observacao nao foi encontrado.")

    internet_ok = tem_internet()
    telegram_sent = False
    telegram_error = ""

    if final_decision == "ALERT_CHILD_ALONE" and internet_ok:
        try:
            telegram_sent = enviar_alerta_telegram(summary)
        except Exception as error:
            # Falhas de Telegram ficam registradas sem interromper o Flask.
            telegram_sent = False
            telegram_error = str(error)
            logger.exception("Falha ao enviar Telegram")
    elif final_decision == "ALERT_CHILD_ALONE":
        logger.info("Alerta confirmado sem internet; Telegram nao sera enviado.")

    result = {
        "final_decision": final_decision,
        "child_presence_ratio": resumo_float(summary, "child_presence_ratio"),
        "adult_presence_ratio": resumo_float(summary, "adult_presence_ratio"),
        "child_avg_conf": resumo_float(summary, "child_avg_conf"),
        "internet_ok": internet_ok,
        "telegram_sent": telegram_sent,
        "send_to_lora": bool(internet_ok),
        "timestamp": time.time(),
    }

    if telegram_error:
        result["telegram_error"] = telegram_error

    return result


def executar_observacao_background(command, timeout):
    """Executa a observacao em background e atualiza o estado ao terminar."""
    global current_process, last_result, server_state
    process = None
    stdout_file = None
    stderr_file = None

    try:
        # Evita que uma falha atual use resumo antigo como se fosse novo.
        if SUMMARY_PATH.exists():
            SUMMARY_PATH.unlink()

        logger.info("Iniciando subprocesso de observacao: %s", " ".join(command))
        stdout_file = tempfile.TemporaryFile(mode="w+t", encoding="utf-8")
        stderr_file = tempfile.TemporaryFile(mode="w+t", encoding="utf-8")
        process = subprocess.Popen(
            command,
            cwd=APP_DIR,
            stdout=stdout_file,
            stderr=stderr_file,
            text=True,
        )

        with state_lock:
            current_process = process

        process.wait(timeout=timeout)
        stdout = ler_tail(stdout_file)
        stderr = ler_tail(stderr_file)

        summary = ler_resumo()
        result = montar_last_result(summary, stdout)
        if process.returncode != 0:
            logger.warning("Subprocesso terminou com returncode=%s stderr_tail=%s", process.returncode, stderr[-1000:] if stderr else "")

        with state_lock:
            last_result = result
            server_state = "FINISHED"
            current_process = None
        logger.info(
            "Observacao finalizada: decision=%s child=%.4f adult=%.4f conf=%.4f telegram=%s",
            result["final_decision"],
            result["child_presence_ratio"],
            result["adult_presence_ratio"],
            result["child_avg_conf"],
            result["telegram_sent"],
        )
    except subprocess.TimeoutExpired:
        if process is not None:
            process.kill()
            process.wait()
            stdout = ler_tail(stdout_file) if stdout_file is not None else ""
            stderr = ler_tail(stderr_file) if stderr_file is not None else ""
        else:
            stdout, stderr = "", ""
        internet_ok = tem_internet()
        with state_lock:
            last_result = {
                "final_decision": "TIMEOUT",
                "child_presence_ratio": 0.0,
                "adult_presence_ratio": 0.0,
                "child_avg_conf": 0.0,
                "internet_ok": internet_ok,
                "telegram_sent": False,
                "send_to_lora": bool(internet_ok),
                "timestamp": time.time(),
            }
            server_state = "FINISHED"
            current_process = None
        logger.warning("Observacao encerrada por timeout.")
    except Exception as error:
        internet_ok = tem_internet()
        with state_lock:
            last_result = {
                "final_decision": "ERROR",
                "child_presence_ratio": 0.0,
                "adult_presence_ratio": 0.0,
                "child_avg_conf": 0.0,
                "internet_ok": internet_ok,
                "telegram_sent": False,
                "send_to_lora": bool(internet_ok),
                "timestamp": time.time(),
                "error": str(error),
            }
            server_state = "FINISHED"
            current_process = None
        logger.exception("Erro ao executar observacao: %s", error)
    finally:
        if stdout_file is not None:
            stdout_file.close()
        if stderr_file is not None:
            stderr_file.close()


@app.get("/health")
def health():
    """Endpoint simples para verificar se o Flask esta ativo."""
    logger.info("GET /health")
    return jsonify({"status": "ok"})


@app.get("/status")
def status():
    """Retorna estado atual da observacao."""
    with state_lock:
        logger.info("GET /status -> %s", server_state)
        return jsonify({"status": server_state})


@app.get("/last_result")
def get_last_result():
    """Retorna o ultimo resultado final salvo em memoria."""
    with state_lock:
        if last_result is None:
            logger.info("GET /last_result -> NO_RESULT")
            return jsonify({"status": "NO_RESULT"}), 404
        logger.info("GET /last_result -> %s", last_result.get("final_decision"))
        return jsonify(last_result)


@app.get("/last_image")
def get_last_image():
    """Retorna a imagem salva do ultimo alerta confirmado."""
    if not LAST_ALERT_IMAGE_PATH.exists():
        logger.info("GET /last_image -> NO_IMAGE")
        return jsonify({"status": "NO_IMAGE"}), 404
    logger.info("GET /last_image -> %s", LAST_ALERT_IMAGE_PATH)
    return send_file(LAST_ALERT_IMAGE_PATH, mimetype="image/jpeg")


@app.get("/check_car")
def check_car():
    """Inicia a observacao em background, ou informa BUSY se ja estiver rodando."""
    global server_state

    try:
        duration = float(request.args.get("duration", DEFAULT_DURATION))
        sample_interval = float(request.args.get("sample_interval", DEFAULT_SAMPLE_INTERVAL))
    except ValueError:
        logger.warning("GET /check_car com argumentos invalidos: %s", request.query_string.decode())
        return jsonify({"status": "INVALID_ARGUMENTS"}), 400

    if duration <= 0 or sample_interval <= 0:
        logger.warning("GET /check_car com valores fora do intervalo: duration=%s sample_interval=%s", duration, sample_interval)
        return jsonify({"status": "INVALID_ARGUMENTS"}), 400

    model = request.args.get("model", str(DEFAULT_MODEL))

    with state_lock:
        if server_state == "RUNNING":
            logger.info("GET /check_car -> BUSY")
            return jsonify({"status": "BUSY"})
        server_state = "RUNNING"

    command = [
        sys.executable,
        "oakd_observation_test.py",
        "--model",
        model,
        "--duration",
        str(duration),
        "--sample-interval",
        str(sample_interval),
        "--no-display",
    ]

    thread = threading.Thread(
        target=executar_observacao_background,
        args=(command, duration + 90),
        daemon=True,
    )
    thread.start()

    logger.info("GET /check_car -> CHECK_STARTED duration=%.1f sample_interval=%.2f", duration, sample_interval)
    return jsonify({"status": "CHECK_STARTED"})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, threaded=True)
