# Sistema de Comunicacao Heltec LoRa 32 V2

## Hardware

* Heltec WiFi LoRa 32 V2 / ESP32
* Raspberry Pi executando Flask

## Dependencias Arduino

Instale pelo Library Manager da IDE Arduino:

* ArduinoJson

As bibliotecas `WiFi`, `HTTPClient` e `SPIFFS` ja fazem parte do core ESP32.

## Fluxo

1. Usuario pressiona o botao PRG/BOOT.
2. A Heltec envia `GET /check_car`.
3. A Raspberry inicia a observacao OAK-D + YOLOv8 OpenVINO.
4. A Heltec consulta `GET /status` ate receber `FINISHED`.
5. A Heltec consulta `GET /last_result` e interpreta o JSON com ArduinoJson.
6. Se `final_decision == "ALERT_CHILD_ALONE"`, a Heltec baixa `GET /last_image` para `/last_alert.jpg` no SPIFFS.

## Endpoints utilizados

```text
GET /check_car
GET /status
GET /last_result
GET /last_image
```

## Configuracao

Atualize nos sketches:

```cpp
const char* ssid = "...";
const char* password = "...";

const char* checkCarUrl = "http://192.168.0.11:5000/check_car";
const char* statusUrl = "http://192.168.0.11:5000/status";
const char* resultUrl = "http://192.168.0.11:5000/last_result";
const char* imageUrl = "http://192.168.0.11:5000/last_image";
```

## Decisoes esperadas

```text
ALERT_CHILD_ALONE
CRIANCA_DETECTADA_MAS_NAO_CONFIRMADA
NO_ALERT
OAKD_NOT_FOUND
TIMEOUT
ERROR
```

## Campos esperados em /last_result

```json
{
  "final_decision": "NO_ALERT",
  "child_presence_ratio": 0.0,
  "adult_presence_ratio": 0.0,
  "child_avg_conf": 0.0,
  "internet_ok": true,
  "telegram_sent": false,
  "send_to_lora": true,
  "timestamp": 0
}
```
