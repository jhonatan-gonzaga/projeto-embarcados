"""Stub de alerta Telegram.

Telegram real ainda nao e implementado aqui. Esta funcao existe para manter
o contrato de integracao do projeto e facilitar a troca futura pela chamada
real da API do Telegram.
"""


def mensagemTelegram(imagem, co2, temperatura, humidade):
    """Stub do envio de alerta com imagem e dados ambientais."""
    print("===== STUB mensagemTelegram =====")
    print(f"Imagem: {imagem}")
    print(f"CO2: {co2}")
    print(f"Temperatura: {temperatura}")
    print(f"Humidade: {humidade}")
    print("Telegram real ainda nao implementado. Retornando False.")
    print("=================================")
    return False
