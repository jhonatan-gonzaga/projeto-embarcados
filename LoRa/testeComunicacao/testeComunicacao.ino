#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>

// Sketch de teste: simula DHT22 e usa duracao curta para validar o fluxo.
const char* ssid = "Galaxy A10s7785";
const char* password = "ventilador1";

const char* loraEventUrl = "http://10.112.100.249:5000/lora_event?duration=10&sample_interval=1.0&debug_detections=true&yolo_conf=0.05";
const char* statusUrl = "http://10.112.100.249:5000/status";
const char* resultUrl = "http://10.112.100.249:5000/last_result";

const int BOTAO_PIN = 0;
const unsigned long WIFI_TIMEOUT_MS = 20000;
const unsigned long HTTP_TIMEOUT_MS = 10000;
const unsigned long POLL_INTERVAL_MS = 3000;
const unsigned long OBSERVATION_TIMEOUT_MS = 90000;
const unsigned long DEBOUNCE_MS = 500;

bool botaoAnterior = HIGH;
unsigned long ultimoClique = 0;

struct HttpResponse {
  int statusCode;
  String body;
  bool ok;
};

struct ResultadoRaspberry {
  String finalDecision;
  float childPresenceRatio;
  float adultPresenceRatio;
  float childAvgConf;
  bool internetOk;
  bool telegramSent;
  bool sendToLora;
  double timestamp;
};

void logLinha(const String& mensagem) {
  Serial.println(mensagem);
}

void logHeap(const char* contexto) {
  Serial.print("[MEM] ");
  Serial.print(contexto);
  Serial.print(" | heap livre: ");
  Serial.println(ESP.getFreeHeap());
}

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

  logLinha("[WiFi] Falha ao conectar.");
  return false;
}

HttpResponse httpGET(const char* url) {
  HttpResponse resposta = {-1, "", false};

  if (!conectarWiFi()) {
    resposta.body = "ERRO_WIFI";
    return resposta;
  }

  HTTPClient http;
  http.setTimeout(HTTP_TIMEOUT_MS);

  if (!http.begin(url)) {
    resposta.body = "ERRO_HTTP_BEGIN";
    return resposta;
  }

  resposta.statusCode = http.GET();
  if (resposta.statusCode > 0) {
    resposta.body = http.getString();
    resposta.ok = resposta.statusCode >= 200 && resposta.statusCode < 300;
  } else {
    resposta.body = http.errorToString(resposta.statusCode);
  }

  Serial.print("[HTTP] GET ");
  Serial.print(url);
  Serial.print(" -> ");
  Serial.println(resposta.statusCode);

  http.end();
  return resposta;
}

HttpResponse httpPOSTJson(const char* url, const String& json) {
  HttpResponse resposta = {-1, "", false};

  if (!conectarWiFi()) {
    resposta.body = "ERRO_WIFI";
    return resposta;
  }

  HTTPClient http;
  http.setTimeout(HTTP_TIMEOUT_MS);

  if (!http.begin(url)) {
    resposta.body = "ERRO_HTTP_BEGIN";
    return resposta;
  }

  http.addHeader("Content-Type", "application/json");
  resposta.statusCode = http.POST(json);
  if (resposta.statusCode > 0) {
    resposta.body = http.getString();
    resposta.ok = resposta.statusCode >= 200 && resposta.statusCode < 300;
  } else {
    resposta.body = http.errorToString(resposta.statusCode);
  }

  Serial.print("[HTTP] POST ");
  Serial.print(url);
  Serial.print(" -> ");
  Serial.println(resposta.statusCode);

  http.end();
  return resposta;
}

bool extrairStatusJson(const String& body, String& status) {
  StaticJsonDocument<160> doc;
  DeserializationError erro = deserializeJson(doc, body);
  if (erro) {
    Serial.print("[JSON] Falha ao ler status: ");
    Serial.println(erro.c_str());
    return false;
  }

  status = doc["status"] | "";
  return status.length() > 0;
}

bool extrairResultadoJson(const String& body, ResultadoRaspberry& resultado) {
  StaticJsonDocument<768> doc;
  StaticJsonDocument<256> filtro;
  filtro["final_decision"] = true;
  filtro["child_presence_ratio"] = true;
  filtro["adult_presence_ratio"] = true;
  filtro["child_avg_conf"] = true;
  filtro["internet_ok"] = true;
  filtro["telegram_sent"] = true;
  filtro["send_to_lora"] = true;
  filtro["timestamp"] = true;

  DeserializationError erro = deserializeJson(doc, body, DeserializationOption::Filter(filtro));
  if (erro) {
    Serial.print("[JSON] Falha ao ler resultado: ");
    Serial.println(erro.c_str());
    return false;
  }

  resultado.finalDecision = doc["final_decision"] | "ERROR";
  resultado.childPresenceRatio = doc["child_presence_ratio"] | 0.0;
  resultado.adultPresenceRatio = doc["adult_presence_ratio"] | 0.0;
  resultado.childAvgConf = doc["child_avg_conf"] | 0.0;
  resultado.internetOk = doc["internet_ok"] | false;
  resultado.telegramSent = doc["telegram_sent"] | false;
  resultado.sendToLora = doc["send_to_lora"] | false;
  resultado.timestamp = doc["timestamp"] | 0.0;
  return resultado.finalDecision.length() > 0;
}

void imprimirResultadoFinal(const ResultadoRaspberry& resultado) {
  Serial.println();
  Serial.println("===== RESULTADO FINAL =====");
  Serial.print("Decisao: ");
  Serial.println(resultado.finalDecision);
  Serial.print("child_presence_ratio: ");
  Serial.println(resultado.childPresenceRatio, 4);
  Serial.print("adult_presence_ratio: ");
  Serial.println(resultado.adultPresenceRatio, 4);
  Serial.print("child_avg_conf: ");
  Serial.println(resultado.childAvgConf, 4);
  Serial.print("internet_ok: ");
  Serial.println(resultado.internetOk ? "true" : "false");
  Serial.print("telegram_sent: ");
  Serial.println(resultado.telegramSent ? "true" : "false");
  Serial.print("send_to_lora: ");
  Serial.println(resultado.sendToLora ? "true" : "false");

  if (resultado.finalDecision == "ALERT_CHILD_ALONE") {
    logLinha("ACAO: alerta de crianca sozinha.");
  } else if (resultado.finalDecision == "CRIANCA_DETECTADA_MAS_NAO_CONFIRMADA") {
    logLinha("ACAO: crianca detectada, mas nao confirmada.");
  } else if (resultado.finalDecision == "NO_ALERT") {
    logLinha("ACAO: sem alerta.");
  } else if (resultado.finalDecision == "OAKD_NOT_FOUND") {
    logLinha("ACAO: verificar OAK-D.");
  } else if (resultado.finalDecision == "TIMEOUT") {
    logLinha("ACAO: timeout.");
  } else {
    logLinha("ACAO: erro ou decisao desconhecida.");
  }

  Serial.println("===========================");
  logHeap("apos resultado");
}

bool consultarUltimoResultado(ResultadoRaspberry& resultado) {
  logLinha("[RPI] Consultando /last_result...");
  HttpResponse resposta = httpGET(resultUrl);
  if (!resposta.ok) {
    Serial.print("[RPI] Falha em /last_result. HTTP=");
    Serial.println(resposta.statusCode);
    return false;
  }

  Serial.print("[RPI] JSON: ");
  Serial.println(resposta.body);
  return extrairResultadoJson(resposta.body, resultado);
}

bool aguardarResultado(ResultadoRaspberry& resultado) {
  logLinha("[RPI] Aguardando fim da observacao...");
  unsigned long inicio = millis();
  int falhasConsecutivas = 0;

  while (millis() - inicio < OBSERVATION_TIMEOUT_MS) {
    delay(POLL_INTERVAL_MS);

    HttpResponse respostaStatus = httpGET(statusUrl);
    if (!respostaStatus.ok) {
      falhasConsecutivas++;
      Serial.print("[RPI] Falha ao consultar /status. Tentativa ");
      Serial.println(falhasConsecutivas);
      if (falhasConsecutivas >= 5) {
        return false;
      }
      continue;
    }

    falhasConsecutivas = 0;
    String status;
    if (!extrairStatusJson(respostaStatus.body, status)) {
      return false;
    }

    Serial.print("[RPI] Status: ");
    Serial.println(status);

    if (status == "FINISHED" || status == "IDLE") {
      return consultarUltimoResultado(resultado);
    }
  }

  logLinha("[RPI] Timeout local aguardando resultado.");
  return false;
}

bool enviarEventoLoRa(ResultadoRaspberry& resultado) {
  StaticJsonDocument<160> doc;
  doc["temperatura"] = 38.5;
  doc["umidade"] = 72.5;

  String json;
  serializeJson(doc, json);

  logLinha("[RPI] Enviando DHT22 simulado para /lora_event...");
  Serial.print("[RPI] JSON: ");
  Serial.println(json);

  HttpResponse resposta = httpPOSTJson(loraEventUrl, json);
  if (!resposta.ok) {
    Serial.print("[RPI] Falha em /lora_event. HTTP=");
    Serial.println(resposta.statusCode);
    return false;
  }

  String status;
  if (!extrairStatusJson(resposta.body, status)) {
    return false;
  }

  Serial.print("[RPI] Resposta /lora_event: ");
  Serial.println(status);

  if (status == "CHECK_STARTED" || status == "BUSY") {
    return aguardarResultado(resultado);
  }

  return false;
}

void setup() {
  Serial.begin(115200);
  delay(1000);
  pinMode(BOTAO_PIN, INPUT_PULLUP);

  Serial.println("===== TESTE Fluxo LoRa -> Raspberry -> Telegram =====");
  conectarWiFi();
  logHeap("setup");
  Serial.println("Pressione o botao PRG/BOOT para enviar DHT22 simulado.");
}

void loop() {
  bool botaoAtual = digitalRead(BOTAO_PIN);

  if (botaoAnterior == HIGH && botaoAtual == LOW) {
    unsigned long agora = millis();
    if (agora - ultimoClique > DEBOUNCE_MS) {
      ultimoClique = agora;

      ResultadoRaspberry resultado;
      if (enviarEventoLoRa(resultado)) {
        imprimirResultadoFinal(resultado);
      } else {
        logLinha("[ERRO] Nao foi possivel concluir o teste.");
      }
    }
  }

  botaoAnterior = botaoAtual;
  delay(20);
}
