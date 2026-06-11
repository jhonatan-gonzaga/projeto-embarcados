"""Funcoes de armazenamento, caminhos e leitura de arquivos de resultado."""

import os
from pathlib import Path


APP_DIR = Path(__file__).resolve().parents[1]
RESULTS_DIR = APP_DIR / "../results"
SUMMARY_PATH = RESULTS_DIR / "reports/oakd_observation_summary.txt"
LAST_ALERT_IMAGE_PATH = RESULTS_DIR / "images/last_child_alert.jpg"
DEFAULT_MODEL = APP_DIR / "../models/best_yolov8n_openvino_model"
DEFAULT_DURATION = 180
DEFAULT_SAMPLE_INTERVAL = 1.0


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


def obter_caminho_imagem_alerta(summary=None):
    """Obtem a imagem do ultimo alerta validando o caminho salvo."""
    summary = summary or {}
    raw_path = summary.get("alert_image_path") or str(LAST_ALERT_IMAGE_PATH)
    image_path = Path(str(raw_path))
    if not image_path.is_absolute():
        image_path = APP_DIR / image_path
    return image_path.resolve()


def montar_image_info():
    """Monta metadados da ultima imagem salva do melhor frame child."""
    summary = ler_resumo()
    image_path = obter_caminho_imagem_alerta(summary)
    exists = image_path.exists() and image_path.stat().st_size > 0

    return {
        "exists": exists,
        "best_child_conf": resumo_float(summary, "best_child_conf"),
        "path": str(image_path),
        "timestamp": resumo_float(summary, "best_child_timestamp"),
    }
