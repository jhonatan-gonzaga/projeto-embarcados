"""Envio de alerta Telegram para o fluxo LoRa -> Raspberry -> Telegram."""

import logging
import os

from telegram_notifier import DEFAULT_BOT_TOKEN, DEFAULT_CHAT_ID, send_telegram_alert


logger = logging.getLogger(__name__)


def mensagemTelegram(imagem, temperatura, humidade):
    """Envia alerta com imagem e dados DHT22 quando as credenciais existem."""
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN", DEFAULT_BOT_TOKEN).strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", DEFAULT_CHAT_ID).strip()

    if not bot_token or not chat_id:
        logger.warning("Telegram nao enviado: configure TELEGRAM_BOT_TOKEN e TELEGRAM_CHAT_ID.")
        return False

    logger.info(
        "Tentando enviar Telegram com imagem=%s temperatura=%s humidade=%s",
        imagem,
        temperatura,
        humidade,
    )
    sent = send_telegram_alert(
        image_path=imagem,
        temperature=temperatura,
        humidity=humidade,
        bot_token=bot_token,
        chat_id=chat_id,
    )
    logger.info("Telegram enviado: %s", sent)
    return sent
