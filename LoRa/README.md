# Sistema de Comunicação LoRa 32 V2

## Hardware

* Heltec WiFi LoRa 32 V2

## Objetivo

Enviar comando de verificação para a Raspberry Pi e receber o resultado final da análise.

## Fluxo

PRG
↓
CHECK_CAR
↓
Raspberry
↓
OAK-D
↓
YOLOv8
↓
Resultado
↓
LoRa

## Endpoints utilizados

/check_car

/status

/last_result

## Configuração Wi-Fi

const char\* ssid = "...";

const char\* password = "...";

## Configuração da Raspberry

const char\* checkCarUrl =
"<http://192.168.0.11:5000/check_car>";

const char\* statusUrl =
"<http://192.168.0.11:5000/status>";

const char\* resultUrl =
"<http://192.168.0.11:5000/last_result>";

## Resultados possíveis

CRIANCA_SOZINHA_CONFIRMADA

CRIANCA_DETECTADA_MAS_NAO_CONFIRMADA

ADULTO_PRESENTE

NENHUMA_PRESENCA_CONFIRMADA

OAKD_NOT_FOUND

## Informação de Internet

internet = true

internet = false

## Exemplo

if (resposta == "CRIANCA_SOZINHA_CONFIRMADA") {

}

if (internet == true) {

}