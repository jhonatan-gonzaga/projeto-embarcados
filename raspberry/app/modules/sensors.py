"""Armazenamento em memoria dos dados de sensores enviados pela LoRa/Heltec."""

import threading
import time


_sensor_lock = threading.Lock()
_latest_sensor_data = None
CO_FIELD_NAMES = (
    "co",
    "CO",
    "co_ppm",
    "coPpm",
    "COppm",
    "monoxido_carbono",
    "monoxidoCarbono",
    "carbon_monoxide",
    "carbonMonoxide",
    "mq7",
    "mq7_co",
    "mq9",
    "mq9_ppm",
    "mq9ppm",
    "mq9_co",
    "mq9Co",
    "mq9_co_ppm",
)


def converter_sensor_float(data, key):
    """Converte campo numerico recebido do ESP32 para float."""
    try:
        value = float(data[key])
    except KeyError as error:
        raise ValueError(f"Campo obrigatorio ausente: {key}") from error
    except (TypeError, ValueError) as error:
        raise ValueError(f"Campo invalido: {key}") from error

    return value


def converter_sensor_float_opcional(data, *keys):
    """Converte o primeiro campo numerico encontrado ou retorna None."""
    for key in keys:
        if key not in data:
            continue
        try:
            return float(data[key])
        except (TypeError, ValueError) as error:
            raise ValueError(f"Campo invalido: {key}") from error
    return None


def salvar_sensor_data(data):
    """Valida e salva o ultimo pacote de sensores em memoria.

    Aceita `temperatura`, `umidade` ou `humidade`, e CO opcional.
    """
    global _latest_sensor_data

    humidade = converter_sensor_float_opcional(data, "humidade", "umidade", "humidity")
    if humidade is None:
        raise ValueError("Campo obrigatorio ausente: humidade/umidade")
    co = converter_sensor_float_opcional(data, *CO_FIELD_NAMES)

    sensor_data = {
        "temperatura": converter_sensor_float(data, "temperatura"),
        "humidade": humidade,
        "umidade": humidade,
        "timestamp": time.time(),
    }
    if co is not None:
        sensor_data["co"] = co
        sensor_data["co_ppm"] = co

    with _sensor_lock:
        _latest_sensor_data = sensor_data

    return sensor_data


def obter_latest_sensor_data():
    """Retorna uma copia do ultimo pacote de sensores salvo."""
    with _sensor_lock:
        if _latest_sensor_data is None:
            return None
        return dict(_latest_sensor_data)
