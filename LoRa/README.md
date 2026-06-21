# Sistema de Comunicacao Heltec LoRa 32 V2

## Hardware

* Heltec WiFi LoRa 32 V2 / ESP32
* Raspberry Pi executando Flask

## Dependencias Arduino

Instale pelo Library Manager da IDE Arduino:

* ArduinoJson
* DHT sensor library ou DHTesp, dependendo do sketch usado

As bibliotecas `WiFi` e `HTTPClient` ja fazem parte do core ESP32.

## Fluxo

1. A Heltec le o DHT22.
2. A Heltec envia `POST /lora_event` com `temperatura` e `umidade`.
3. A Raspberry salva os dados DHT22 e inicia a observacao OAK-D + YOLO OpenVINO.
4. A Heltec consulta `GET /status` ate receber `FINISHED`.
5. Se a IA confirmar `ALERT_CHILD_ALONE`, a Raspberry envia Telegram com imagem, temperatura e umidade.
6. A Heltec consulta `GET /last_result` e interpreta o JSON com ArduinoJson.

## Endpoints utilizados

```text
POST /lora_event
GET /status
GET /last_result
```

`GET /check_car` continua existindo para testes manuais. `GET /last_image` continua existindo na Raspberry, mas nao e usado pela Heltec.

Payload do fluxo normal:

```json
{
  "temperatura": 32.5,
  "umidade": 60.0
}
```

## Configuracao

Atualize nos sketches:

```cpp
const char* ssid = "...";
const char* password = "...";

const char* loraEventUrl = "http://192.168.0.11:5000/lora_event";
const char* statusUrl = "http://192.168.0.11:5000/status";
const char* resultUrl = "http://192.168.0.11:5000/last_result";
```

Na Raspberry, configure o Telegram antes de iniciar o servidor:

```bash
export TELEGRAM_BOT_TOKEN="seu_token"
export TELEGRAM_CHAT_ID="seu_chat_id"
cd raspberry
./menu_raspberry.sh
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
