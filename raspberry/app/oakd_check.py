"""
Exemplo de uso:

python oakd_check.py

Lista dispositivos OAK-D/DepthAI conectados ao computador.
"""

import depthai as dai


def obter_mx_id(device_info):
    """Obtem MX ID em versoes diferentes do DepthAI."""
    if hasattr(device_info, "mxid"):
        return device_info.mxid
    if hasattr(device_info, "getDeviceId"):
        return device_info.getDeviceId()
    return getattr(device_info, "deviceId", "desconhecido")


def obter_estado(device_info):
    """Obtem estado do dispositivo com fallback entre APIs."""
    return getattr(device_info, "state", getattr(device_info, "status", "desconhecido"))


def listar_dispositivos():
    """Lista dispositivos DepthAI e imprime nome, MX ID e estado."""
    dispositivos = dai.Device.getAllAvailableDevices()

    if not dispositivos:
        print("OAK-D nao encontrada.")
        return []

    print("OAK-D encontrada.")
    for device_info in dispositivos:
        print("\nDispositivo encontrado")
        print(f"Nome: {device_info.name}")
        print(f"MX ID: {obter_mx_id(device_info)}")
        print(f"Estado: {obter_estado(device_info)}")

    return dispositivos


def main():
    listar_dispositivos()


if __name__ == "__main__":
    main()
