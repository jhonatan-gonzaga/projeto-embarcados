"""Envio de alerta Telegram para o fluxo LoRa -> Raspberry -> Telegram."""

import logging
import os

from telegram_notifier import DEFAULT_BOT_TOKEN, DEFAULT_CHAT_ID, send_telegram_alert_result


logger = logging.getLogger(__name__)
_last_telegram_error = None


def get_last_telegram_error():
    """Retorna o ultimo motivo de falha do Telegram, se houver."""
    return _last_telegram_error


def mensagemTelegram(imagem, temperatura, humidade, co=None):
    """Envia alerta com imagem e dados de sensores quando as credenciais existem."""
    global _last_telegram_error

    _last_telegram_error = None
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN", DEFAULT_BOT_TOKEN).strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", DEFAULT_CHAT_ID).strip()

    if not bot_token or not chat_id:
        _last_telegram_error = "Telegram nao enviado: configure TELEGRAM_BOT_TOKEN e TELEGRAM_CHAT_ID."
        logger.warning(_last_telegram_error)
        return False

    logger.info(
        "Tentando enviar Telegram com imagem=%s temperatura=%s humidade=%s co=%s",
        imagem,
        temperatura,
        humidade,
        co,
    )
    sent, error = send_telegram_alert_result(
        image_path=imagem,
        temperature=temperatura,
        humidity=humidade,
        bot_token=bot_token,
        chat_id=chat_id,
        co=co,
    )
    _last_telegram_error = error
    logger.info("Telegram enviado: %s", sent)
    return sent
