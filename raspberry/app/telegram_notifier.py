"""Modulo isolado para envio de alertas via Telegram.

Este arquivo nao depende do Flask. A API pode importar `send_telegram_alert`
apos a IA confirmar uma crianca sozinha no veiculo.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import requests


logger = logging.getLogger(__name__)

TELEGRAM_SEND_PHOTO_URL = "https://api.telegram.org/bot{bot_token}/sendPhoto"
DEFAULT_TIMEOUT_SECONDS = 15


class TelegramNotifier:
    """Cliente minimo para enviar fotos pela API do Telegram."""

    def __init__(
        self,
        bot_token: str,
        chat_id: str | int,
        timeout: int | float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        self.bot_token = str(bot_token).strip()
        self.chat_id = str(chat_id).strip()
        self.timeout = timeout

    def send_alert_photo(
        self,
        image_path: str | Path,
        temperature: float | int | str | None,
        co2: float | int | str | None,
    ) -> bool:
        """Envia foto com legenda Markdown e retorna True somente no sucesso."""
        if not self.bot_token or not self.chat_id:
            logger.warning("Telegram nao enviado: bot_token ou chat_id ausente.")
            return False

        photo_path = Path(image_path)
        if not photo_path.is_file():
            logger.warning("Telegram nao enviado: imagem nao encontrada em %s.", photo_path)
            return False

        url = TELEGRAM_SEND_PHOTO_URL.format(bot_token=self.bot_token)
        payload: dict[str, Any] = {
            "chat_id": self.chat_id,
            "caption": self._build_caption(temperature, co2),
            "parse_mode": "Markdown",
        }

        try:
            with photo_path.open("rb") as photo_file:
                files = {
                    "photo": (
                        photo_path.name,
                        photo_file,
                        "image/jpeg",
                    )
                }
                response = requests.post(
                    url,
                    data=payload,
                    files=files,
                    timeout=self.timeout,
                )
        except requests.Timeout:
            logger.warning("Telegram nao enviado: timeout apos %ss.", self.timeout)
            return False
        except requests.ConnectionError as error:
            logger.warning("Telegram nao enviado: falha de conexao: %s", error)
            return False
        except requests.RequestException as error:
            logger.warning("Telegram nao enviado: erro HTTP local: %s", error)
            return False
        except OSError as error:
            logger.warning("Telegram nao enviado: erro ao ler imagem: %s", error)
            return False

        if response.status_code != requests.codes.ok:
            logger.warning(
                "Telegram nao enviado: API retornou HTTP %s: %s",
                response.status_code,
                response.text[:300],
            )
            return False

        try:
            response_body = response.json()
        except ValueError:
            logger.warning("Telegram nao enviado: resposta HTTP 200 sem JSON valido.")
            return False

        if response_body.get("ok") is not True:
            logger.warning("Telegram nao enviado: API retornou ok=false: %s", response.text[:300])
            return False

        logger.info("Telegram enviado com sucesso para chat_id=%s.", self.chat_id)
        return True

    @staticmethod
    def _build_caption(
        temperature: float | int | str | None,
        co2: float | int | str | None,
    ) -> str:
        """Monta a legenda Markdown enviada junto da foto."""
        temperature_text = _format_sensor_value(temperature, suffix="C")
        co2_text = _format_sensor_value(co2, suffix="ppm")

        return (
            "*ALERTA CRITICO: crianca detectada sozinha no veiculo!*\n\n"
            f"*Temperatura:* {temperature_text}\n"
            f"*CO2:* {co2_text}\n\n"
            "Verifique o veiculo imediatamente."
        )


def send_telegram_alert(
    image_path: str | Path,
    temperature: float | int | str | None,
    co2: float | int | str | None,
    bot_token: str,
    chat_id: str | int,
    timeout: int | float = DEFAULT_TIMEOUT_SECONDS,
) -> bool:
    """Envia alerta Telegram com foto e retorna True em caso de sucesso.

    Retorna False em falhas de rede, timeout, erro de leitura da imagem ou erro
    da API do Telegram. Esse contrato permite que a camada Flask grave
    `telegram_sent` e acione uma redundancia externa quando necessario.
    """
    notifier = TelegramNotifier(bot_token=bot_token, chat_id=chat_id, timeout=timeout)
    return notifier.send_alert_photo(
        image_path=image_path,
        temperature=temperature,
        co2=co2,
    )


def _format_sensor_value(value: float | int | str | None, suffix: str) -> str:
    if value is None:
        return f"indisponivel {suffix}"

    try:
        numeric_value = float(value)
    except (TypeError, ValueError):
        return f"{value} {suffix}"

    return f"{numeric_value:.1f} {suffix}"

if __name__ == "__main__":
    # Configuração para imprimir os avisos no terminal durante o teste
    logging.basicConfig(level=logging.INFO)

    # 1. Suas Credenciais
    MEU_TOKEN = "COLE_SEU_TOKEN_AQUI"
    MEU_CHAT_ID = "COLE_SEU_CHAT_ID_AQUI"
    
    # 2. Arquivo de Imagem
    # Coloque uma foto real chamada "foto_teste.jpg" na mesma pasta deste script
    IMAGEM_TESTE = "last_child_alert.jpg"

    print("Iniciando teste de notificação...")
    
    # 3. Executando a função principal
    sucesso = send_telegram_alert(
        image_path=IMAGEM_TESTE,
        temperature=38.5,
        co2=1200,
        bot_token=MEU_TOKEN,
        chat_id=MEU_CHAT_ID
    )

    # 4. Validando o retorno (O coração da sua arquitetura)
    if sucesso:
        print("\n✅ SUCESSO: O Flask salvaria telegram_sent = True")
        print("A ESP32 não enviará SMS.")
    else:
        print("\n❌ FALHA: O Flask salvaria telegram_sent = False")
        print("A ESP32 ativará o módulo GSM SIM800L.")