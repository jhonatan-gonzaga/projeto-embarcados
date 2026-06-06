#include <WiFi.h>
#include <HTTPClient.h>

const char* ssid = "Pedro Arthur_2.4GHz";
const char* password = "Pa29R11T10";

const char* checkCarUrl = "http://192.168.0.11:5000/check_car";
const char* statusUrl   = "http://192.168.0.11:5000/status";
const char* resultUrl   = "http://192.168.0.11:5000/last_result";

const int BOTAO_PIN = 0;

// Simulação da condição externa.
// Depois outra pessoa troca essa função pela condição real.
bool condicaoParaVerificar() {
  return digitalRead(BOTAO_PIN) == LOW;
}

void conectarWiFi() {
  WiFi.mode(WIFI_STA);
  WiFi.begin(ssid, password);

  Serial.print("Conectando no WiFi");

  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }

  Serial.println("\nWiFi conectado!");
  Serial.print("IP: ");
  Serial.println(WiFi.localIP());
}

String httpGET(const char* url) {
  if (WiFi.status() != WL_CONNECTED) {
    conectarWiFi();
  }

  HTTPClient http;
  http.begin(url);
  http.setTimeout(8000);

  int httpCode = http.GET();
  String resposta = "";

  if (httpCode > 0) {
    resposta = http.getString();
  } else {
    resposta = "ERRO_HTTP";
  }

  http.end();
  return resposta;
}

String extrairDecisao(String json) {
  if (json.indexOf("CRIANCA_SOZINHA_CONFIRMADA") >= 0) {
    return "CRIANCA_SOZINHA_CONFIRMADA";
  }

  if (json.indexOf("CRIANCA_DETECTADA_MAS_NAO_CONFIRMADA") >= 0) {
    return "CRIANCA_DETECTADA_MAS_NAO_CONFIRMADA";
  }

  if (json.indexOf("ADULTO_PRESENTE") >= 0) {
    return "ADULTO_PRESENTE";
  }

  if (json.indexOf("NENHUMA_PRESENCA_CONFIRMADA") >= 0) {
    return "NENHUMA_PRESENCA_CONFIRMADA";
  }

  if (json.indexOf("OAKD_NOT_FOUND") >= 0) {
    return "OAKD_NOT_FOUND";
  }

  return "RESULTADO_DESCONHECIDO";
}

String consultarRaspberry() {
  Serial.println("Enviando CHECK_CAR...");

  String respostaCheck = httpGET(checkCarUrl);

  if (respostaCheck.indexOf("BUSY") >= 0) {
    Serial.println("Raspberry ocupada. Aguardando resultado...");
  } 
  else if (respostaCheck.indexOf("CHECK_STARTED") >= 0) {
    Serial.println("Verificacao iniciada.");
  } 
  else {
    Serial.println("Falha ao iniciar verificacao.");
    return "ERRO_CHECK_CAR";
  }

  while (true) {
    delay(3000);

    String status = httpGET(statusUrl);
    Serial.println(status);

    if (status.indexOf("FINISHED") >= 0 || status.indexOf("IDLE") >= 0) {
      String resultadoJson = httpGET(resultUrl);
      String decisao = extrairDecisao(resultadoJson);

      Serial.print("Decisao final: ");
      Serial.println(decisao);

      return decisao;
    }

    if (status.indexOf("RUNNING") >= 0) {
      Serial.println("Ainda verificando...");
    }
  }
}

void tratarResposta(String resposta) {
  if (resposta == "CRIANCA_SOZINHA_CONFIRMADA") {
    Serial.println("ACAO: alerta de crianca sozinha");
  } 
  else if (resposta == "ADULTO_PRESENTE") {
    Serial.println("ACAO: adulto presente, sem alerta");
  } 
  else if (resposta == "CRIANCA_DETECTADA_MAS_NAO_CONFIRMADA") {
    Serial.println("ACAO: crianca detectada, mas nao confirmada");
  } 
  else if (resposta == "NENHUMA_PRESENCA_CONFIRMADA") {
    Serial.println("ACAO: nenhuma presenca confirmada");
  } 
  else {
    Serial.print("ACAO: erro ou resultado desconhecido: ");
    Serial.println(resposta);
  }
}

void setup() {
  Serial.begin(115200);
  delay(1000);

  pinMode(BOTAO_PIN, INPUT_PULLUP);

  Serial.println("===== LoRa 32 V2 - Modulo de Consulta Raspberry =====");

  conectarWiFi();
}

void loop() {
  if (condicaoParaVerificar()) {
    String resposta = consultarRaspberry();
    tratarResposta(resposta);

    delay(3000); // evita repetir várias vezes segurando o botão
  }
}