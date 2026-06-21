"""Verificacao simples de internet."""

import urllib.error
import urllib.request


INTERNET_TEST_URL = "https://api.telegram.org"
INTERNET_TIMEOUT_SECONDS = 3


def tem_internet(logger=None):
    """Verifica conexao com internet sem travar a API por muito tempo."""
    try:
        request_obj = urllib.request.Request(
            INTERNET_TEST_URL,
            headers={"User-Agent": "raspberry-oakd-child-alert/1.0"},
        )
        with urllib.request.urlopen(request_obj, timeout=INTERNET_TIMEOUT_SECONDS):
            return True
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        if logger is not None:
            logger.info("Internet indisponivel: %s", error)
        return False
