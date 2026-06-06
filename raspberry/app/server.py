"""
Servidor Flask para acionar o modo de observacao da OAK-D sem travar a API.

Exemplos:
python server.py
curl http://localhost:5000/health
curl http://localhost:5000/status
curl http://localhost:5000/check_car
curl http://localhost:5000/last_result
"""

import subprocess
import sys
import threading
import time
from pathlib import Path

from flask import Flask, jsonify, request


APP_DIR = Path(__file__).resolve().parent
SUMMARY_PATH = APP_DIR / "../results/reports/oakd_observation_summary.txt"
DEFAULT_MODEL = APP_DIR / "../models/best_yolov8n_openvino_model"
DEFAULT_DURATION = 180
DEFAULT_SAMPLE_INTERVAL = 1.0

app = Flask(__name__)

state_lock = threading.Lock()
server_state = "IDLE"
last_result = None
current_process = None


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


def montar_last_result(summary, stdout=""):
    """Monta o JSON publico do ultimo resultado."""
    final_decision = summary.get("final_decision")
    if final_decision is None and "OAK-D nao encontrada" in stdout:
        final_decision = "OAKD_NOT_FOUND"
    elif final_decision is None:
        final_decision = "NO_SUMMARY"

    return {
        "final_decision": final_decision,
        "child_presence_ratio": summary.get("child_presence_ratio"),
        "adult_presence_ratio": summary.get("adult_presence_ratio"),
        "child_avg_conf": summary.get("child_avg_conf"),
        "timestamp": time.time(),
    }


def executar_observacao_background(command, timeout):
    """Executa a observacao em background e atualiza o estado ao terminar."""
    global current_process, last_result, server_state

    try:
        process = subprocess.Popen(
            command,
            cwd=APP_DIR,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        with state_lock:
            current_process = process

        stdout, stderr = process.communicate(timeout=timeout)

        summary = ler_resumo()
        result = montar_last_result(summary, stdout)
        result["returncode"] = process.returncode
        result["stdout"] = stdout[-4000:] if stdout else ""
        result["stderr"] = stderr[-4000:] if stderr else ""

        with state_lock:
            last_result = result
            server_state = "FINISHED"
            current_process = None
    except subprocess.TimeoutExpired:
        process.kill()
        stdout, stderr = process.communicate()
        with state_lock:
            last_result = {
                "final_decision": "TIMEOUT",
                "child_presence_ratio": None,
                "adult_presence_ratio": None,
                "child_avg_conf": None,
                "timestamp": time.time(),
                "returncode": -1,
                "stdout": stdout[-4000:] if stdout else "",
                "stderr": stderr[-4000:] if stderr else "",
            }
            server_state = "FINISHED"
            current_process = None
    except Exception as error:
        with state_lock:
            last_result = {
                "final_decision": "ERROR",
                "child_presence_ratio": None,
                "adult_presence_ratio": None,
                "child_avg_conf": None,
                "timestamp": time.time(),
                "error": str(error),
            }
            server_state = "FINISHED"
            current_process = None


@app.get("/health")
def health():
    """Endpoint simples para verificar se o Flask esta ativo."""
    return jsonify({"status": "ok"})


@app.get("/status")
def status():
    """Retorna estado atual da observacao."""
    with state_lock:
        return jsonify({"status": server_state})


@app.get("/last_result")
def get_last_result():
    """Retorna o ultimo resultado final salvo em memoria."""
    with state_lock:
        if last_result is None:
            return jsonify({"status": "NO_RESULT"}), 404
        return jsonify(last_result)


@app.get("/check_car")
def check_car():
    """Inicia a observacao em background, ou informa BUSY se ja estiver rodando."""
    global server_state

    with state_lock:
        if server_state == "RUNNING":
            return jsonify({"status": "BUSY"})
        server_state = "RUNNING"

    duration = float(request.args.get("duration", DEFAULT_DURATION))
    sample_interval = float(request.args.get("sample_interval", DEFAULT_SAMPLE_INTERVAL))
    model = request.args.get("model", str(DEFAULT_MODEL))

    command = [
        sys.executable,
        "oakd_observation_test.py",
        "--model",
        model,
        "--duration",
        str(duration),
        "--sample-interval",
        str(sample_interval),
    ]

    thread = threading.Thread(
        target=executar_observacao_background,
        args=(command, duration + 90),
        daemon=True,
    )
    thread.start()

    return jsonify({"status": "CHECK_STARTED"})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, threaded=True)
