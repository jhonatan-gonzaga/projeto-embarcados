#include <WiFi.h>
#include <HTTPClient.h>

const char* ssid = "Pedro Arthur_2.4GHz";
const char* password = "Pa29R11T10";

// TESTE com 10 segundos
const char* checkCarUrl = "http://192.168.0.11:5000/check_car?duration=10&sample_interval=1.0";
const char* statusUrl   = "http://192.168.0.11:5000/status";
const char* resultUrl   = "http://192.168.0.11:5000/last_result";

// Botão PRG/BOOT da Heltec LoRa 32 V2
const int BOTAO_PIN = 0;

bool botaoAnterior = HIGH;
unsigned long ultimoClique = 0;
const unsigned long debounceMs = 500;

bool verificacaoEmAndamento = false;

void conectarWiFi() {
  WiFi.mode(WIFI_STA);
  WiFi.begin(ssid, password);

  Serial.print("Conectando no WiFi");

  int tentativas = 0;
  while (WiFi.status() != WL_CONNECTED && tentativas < 40) {
    delay(500);
    Serial.print(".");
    tentativas++;
  }

  Serial.println();

  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("WiFi conectado!");
    Serial.print("IP da LoRa 32: ");
    Serial.println(WiFi.localIP());
  } else {
    Serial.println("Falha ao conectar no WiFi.");
  }
}

String httpGET(const char* url) {
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("WiFi desconectado. Reconectando...");
    conectarWiFi();
  }

  if (WiFi.status() != WL_CONNECTED) {
    return "ERRO_WIFI";
  }

  HTTPClient http;
  http.begin(url);
  http.setTimeout(8000);

  int httpCode = http.GET();
  String resposta = "";

  if (httpCode > 0) {
    resposta = http.getString();

    Serial.print("HTTP ");
    Serial.println(httpCode);
    Serial.println(resposta);
  } else {
    resposta = "ERRO_HTTP";
    Serial.print("Erro HTTP: ");
    Serial.println(http.errorToString(httpCode));
  }

  http.end();
  return resposta;
}

String extrairDecisao(String resposta) {
  if (resposta.indexOf("CRIANCA_SOZINHA_CONFIRMADA") >= 0) {
    return "CRIANCA_SOZINHA_CONFIRMADA";
  }

  if (resposta.indexOf("CRIANCA_DETECTADA_MAS_NAO_CONFIRMADA") >= 0) {
    return "CRIANCA_DETECTADA_MAS_NAO_CONFIRMADA";
  }

  if (resposta.indexOf("ADULTO_PRESENTE") >= 0) {
    return "ADULTO_PRESENTE";
  }

  if (resposta.indexOf("NENHUMA_PRESENCA_CONFIRMADA") >= 0) {
    return "NENHUMA_PRESENCA_CONFIRMADA";
  }

  if (resposta.indexOf("OAKD_NOT_FOUND") >= 0) {
    return "OAKD_NOT_FOUND";
  }

  if (resposta.indexOf("TIMEOUT") >= 0) {
    return "TIMEOUT";
  }

  if (resposta.indexOf("ERROR") >= 0) {
    return "ERROR";
  }

  return "RESULTADO_DESCONHECIDO";
}

bool extrairInternet(String resposta) {
  if (resposta.indexOf("\"internet\":true") >= 0) {
    return true;
  }

  if (resposta.indexOf("\"internet\": true") >= 0) {
    return true;
  }

  return false;
}

void imprimirResultadoFinal(String decisao, bool internet) {
  Serial.println();
  Serial.println("===== RESULTADO FINAL =====");

  Serial.print("Decisao: ");
  Serial.println(decisao);

  Serial.print("Internet: ");
  Serial.println(internet ? "true" : "false");

  if (decisao == "CRIANCA_SOZINHA_CONFIRMADA") {
    Serial.println("RESULTADO: CRIANCA SOZINHA CONFIRMADA");

    if (internet) {
      Serial.println("ACAO: Internet disponivel. Telegram pode ser usado.");
    } else {
      Serial.println("ACAO: Sem internet. Encaminhar para SMS/SIM800L.");
    }
  } 
  else if (decisao == "CRIANCA_DETECTADA_MAS_NAO_CONFIRMADA") {
    Serial.println("RESULTADO: CRIANCA DETECTADA, MAS NAO CONFIRMADA");
  } 
  else if (decisao == "ADULTO_PRESENTE") {
    Serial.println("RESULTADO: ADULTO PRESENTE");
  } 
  else if (decisao == "NENHUMA_PRESENCA_CONFIRMADA") {
    Serial.println("RESULTADO: NENHUMA PRESENCA CONFIRMADA");
  } 
  else if (decisao == "OAKD_NOT_FOUND") {
    Serial.println("RESULTADO: OAK-D NAO ENCONTRADA");
  } 
  else {
    Serial.println("RESULTADO: resposta recebida, mas decisao nao identificada.");
  }

  Serial.println("===========================");
}

void consultarResultado() {
  Serial.println();
  Serial.println("Consultando ultimo resultado...");

  String resposta = httpGET(resultUrl);

  String decisao = extrairDecisao(resposta);
  bool internet = extrairInternet(resposta);

  imprimirResultadoFinal(decisao, internet);
}

void aguardarResultado() {
  Serial.println();
  Serial.println("Aguardando resultado da verificacao...");

  verificacaoEmAndamento = true;

  while (verificacaoEmAndamento) {
    delay(3000);

    Serial.println();
    Serial.println("Consultando status...");

    String status = httpGET(statusUrl);

    if (status.indexOf("FINISHED") >= 0) {
      Serial.println("Verificacao finalizada.");
      verificacaoEmAndamento = false;
      consultarResultado();
      break;
    }

    if (status.indexOf("IDLE") >= 0) {
      Serial.println("Servidor em IDLE. Consultando ultimo resultado...");
      verificacaoEmAndamento = false;
      consultarResultado();
      break;
    }

    if (status.indexOf("RUNNING") >= 0) {
      Serial.println("Ainda verificando...");
    } else {
      Serial.println("Status inesperado. Tentando novamente...");
    }
  }
}

void enviarCheckCar() {
  Serial.println();
  Serial.println("Enviando CHECK_CAR para Raspberry...");

  String resposta = httpGET(checkCarUrl);

  if (resposta.indexOf("CHECK_STARTED") >= 0) {
    Serial.println("Raspberry iniciou a verificacao.");
    aguardarResultado();
  } 
  else if (resposta.indexOf("BUSY") >= 0) {
    Serial.println("Raspberry ja esta verificando.");
    aguardarResultado();
  } 
  else {
    Serial.println("Resposta inesperada ao CHECK_CAR.");
  }
}

void setup() {
  Serial.begin(115200);
  delay(1000);

  pinMode(BOTAO_PIN, INPUT_PULLUP);

  Serial.println("===== LoRa 32 V2 - TESTE Controle Raspberry =====");

  conectarWiFi();

  Serial.println("Pressione o botao PRG/BOOT para enviar CHECK_CAR.");
}

void loop() {
  bool botaoAtual = digitalRead(BOTAO_PIN);

  if (botaoAnterior == HIGH && botaoAtual == LOW) {
    unsigned long agora = millis();

    if (agora - ultimoClique > debounceMs) {
      ultimoClique = agora;
      enviarCheckCar();
    }
  }

  botaoAnterior = botaoAtual;
}