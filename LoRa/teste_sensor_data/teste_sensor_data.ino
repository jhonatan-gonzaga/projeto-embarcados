#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>

// Teste isolado de comunicacao ESP32 -> Flask.
// Envia somente os dados DHT22 simulados: temperatura e umidade.
const char* ssid = "Pedro Arthur_2.4GHz";
const char* password = "Pa29R11T10";

const char* loraEventUrl = "http://192.168.0.11:5000/lora_event?duration=10&sample_interval=1.0";

const unsigned long WIFI_TIMEOUT_MS = 20000;
const unsigned long HTTP_TIMEOUT_MS = 10000;

bool envioRealizado = false;

bool conectarWiFi() {
  if (WiFi.status() == WL_CONNECTED) {
    return true;
  }

  WiFi.mode(WIFI_STA);
  WiFi.setAutoReconnect(true);
  WiFi.persistent(false);
  WiFi.begin(ssid, password);

  Serial.print("[WiFi] Conectando");
  unsigned long inicio = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - inicio < WIFI_TIMEOUT_MS) {
    delay(500);
    Serial.print(".");
  }
  Serial.println();

  if (WiFi.status() == WL_CONNECTED) {
    Serial.print("[WiFi] Conectado. IP: ");
    Serial.println(WiFi.localIP());
    return true;
  }

  Serial.println("[WiFi] Falha ao conectar.");
  return false;
}

bool enviarSensorData(float temperatura, float umidade) {
  if (!conectarWiFi()) {
    Serial.println("[SENSOR] Envio cancelado: WiFi indisponivel.");
    return false;
  }

  StaticJsonDocument<192> doc;
  doc["temperatura"] = temperatura;
  doc["umidade"] = umidade;

  String json;
  serializeJson(doc, json);

  Serial.println();
  Serial.println("===== ENVIO SENSOR DATA =====");
  Serial.print("Endpoint: ");
  Serial.println(loraEventUrl);
  Serial.print("JSON enviado: ");
  Serial.println(json);

  HTTPClient http;
  http.setTimeout(HTTP_TIMEOUT_MS);

  if (!http.begin(loraEventUrl)) {
    Serial.println("[HTTP] Falha no http.begin().");
    return false;
  }

  http.addHeader("Content-Type", "application/json");
  int httpCode = http.POST(json);

  Serial.print("HTTP code: ");
  Serial.println(httpCode);

  String resposta = "";
  if (httpCode > 0) {
    resposta = http.getString();
  } else {
    resposta = http.errorToString(httpCode);
  }

  Serial.print("Resposta recebida: ");
  Serial.println(resposta);
  Serial.println("=============================");

  http.end();
  return httpCode == HTTP_CODE_OK;
}

void setup() {
  Serial.begin(115200);
  delay(1000);

  Serial.println("===== TESTE POST /lora_event =====");
  conectarWiFi();
}

void loop() {
  if (!envioRealizado) {
    envioRealizado = true;

    bool ok = enviarSensorData(
      45.2,
      72.5
    );

    Serial.print("[RESULTADO] enviarSensorData retornou: ");
    Serial.println(ok ? "true" : "false");
  }

  delay(1000);
}
