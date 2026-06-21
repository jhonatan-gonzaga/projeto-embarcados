"""Armazenamento em memoria dos dados simulados de sensores."""

import threading
import time


_sensor_lock = threading.Lock()
_latest_sensor_data = None


def converter_sensor_float(data, key):
    """Converte campo numerico recebido do ESP32 para float."""
    try:
        value = float(data[key])
    except KeyError as error:
        raise ValueError(f"Campo obrigatorio ausente: {key}") from error
    except (TypeError, ValueError) as error:
        raise ValueError(f"Campo invalido: {key}") from error

    return value


def salvar_sensor_data(data):
    """Valida e salva o ultimo pacote de sensores em memoria."""
    global _latest_sensor_data

    sensor_data = {
        "co2": converter_sensor_float(data, "co2"),
        "temperatura": converter_sensor_float(data, "temperatura"),
        "humidade": converter_sensor_float(data, "humidade"),
        "timestamp": time.time(),
    }

    with _sensor_lock:
        _latest_sensor_data = sensor_data

    return sensor_data


def obter_latest_sensor_data():
    """Retorna uma copia do ultimo pacote de sensores salvo."""
    with _sensor_lock:
        if _latest_sensor_data is None:
            return None
        return dict(_latest_sensor_data)
