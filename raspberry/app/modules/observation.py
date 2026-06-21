"""Controle da observacao OAK-D em background."""

import subprocess
import sys
import tempfile
import threading
import time

from modules.internet import tem_internet
from modules.storage import APP_DIR, SUMMARY_PATH, ler_resumo, ler_tail, resumo_float


_state_lock = threading.Lock()
_server_state = "IDLE"
_last_result = None
_current_process = None


def get_status():
    """Retorna o estado atual da observacao."""
    with _state_lock:
        return _server_state


def get_last_result():
    """Retorna uma copia do ultimo resultado em memoria."""
    with _state_lock:
        if _last_result is None:
            return None
        return dict(_last_result)


def set_running_if_idle():
    """Marca a observacao como RUNNING se ela nao estiver em execucao."""
    global _server_state

    with _state_lock:
        if _server_state == "RUNNING":
            return False
        _server_state = "RUNNING"
        return True


def _set_finished(result):
    """Salva resultado final e libera o estado da API."""
    global _last_result, _server_state, _current_process

    with _state_lock:
        _last_result = result
        _server_state = "FINISHED"
        _current_process = None


def _set_current_process(process):
    """Guarda referencia do subprocesso atual."""
    global _current_process

    with _state_lock:
        _current_process = process


def montar_last_result(summary, stdout="", logger=None):
    """Monta o JSON publico do ultimo resultado."""
    final_decision = summary.get("final_decision")
    if final_decision is None and "OAK-D nao encontrada" in stdout:
        final_decision = "OAKD_NOT_FOUND"
    elif final_decision is None:
        final_decision = "ERROR"
        if logger is not None:
            logger.warning("Resumo da observacao nao foi encontrado.")

    internet_ok = tem_internet(logger)

    return {
        "final_decision": final_decision,
        "child_presence_ratio": resumo_float(summary, "child_presence_ratio"),
        "adult_presence_ratio": resumo_float(summary, "adult_presence_ratio"),
        "child_avg_conf": resumo_float(summary, "child_avg_conf"),
        "internet_ok": internet_ok,
        "telegram_sent": False,
        "send_to_lora": bool(internet_ok),
        "timestamp": time.time(),
    }


def montar_comando_observacao(model, duration, sample_interval, yolo_conf, debug_detections=False):
    """Monta comando do script de observacao preservando os testes existentes."""
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
        "--yolo-conf",
        str(yolo_conf),
        "--save-best-frame",
    ]
    if debug_detections:
        command.append("--debug-detections")
    return command


def executar_observacao_background(command, timeout, on_finished=None, logger=None):
    """Executa a observacao em background e atualiza o estado ao terminar."""
    process = None
    stdout_file = None
    stderr_file = None

    try:
        # Evita que uma falha atual use resumo antigo como se fosse novo.
        if SUMMARY_PATH.exists():
            SUMMARY_PATH.unlink()

        if logger is not None:
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
        _set_current_process(process)

        process.wait(timeout=timeout)
        stdout = ler_tail(stdout_file)
        stderr = ler_tail(stderr_file)

        summary = ler_resumo()
        result = montar_last_result(summary, stdout, logger)
        if process.returncode != 0 and logger is not None:
            logger.warning(
                "Subprocesso terminou com returncode=%s stderr_tail=%s",
                process.returncode,
                stderr[-1000:] if stderr else "",
            )

        if on_finished is not None:
            result = on_finished(result, summary)

        _set_finished(result)
        if logger is not None:
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

        internet_ok = tem_internet(logger)
        result = {
            "final_decision": "TIMEOUT",
            "child_presence_ratio": 0.0,
            "adult_presence_ratio": 0.0,
            "child_avg_conf": 0.0,
            "internet_ok": internet_ok,
            "telegram_sent": False,
            "send_to_lora": bool(internet_ok),
            "timestamp": time.time(),
        }
        _set_finished(result)
        if logger is not None:
            logger.warning("Observacao encerrada por timeout.")
    except Exception as error:
        internet_ok = tem_internet(logger)
        result = {
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
        _set_finished(result)
        if logger is not None:
            logger.exception("Erro ao executar observacao: %s", error)
    finally:
        if stdout_file is not None:
            stdout_file.close()
        if stderr_file is not None:
            stderr_file.close()
