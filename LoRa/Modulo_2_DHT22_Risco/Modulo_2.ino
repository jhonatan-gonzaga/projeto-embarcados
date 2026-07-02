/* ==========================================================================
 * PROJETO: Sistema Embarcado de Monitoramento Veicular (ESP32 / LoRa32)
 * DESCRICAO: Monitoramento com DHT22 e MQ-9 (Em PPM) com Feedback Visual.
 * ========================================================================== */

#include <ArduinoJson.h>
#include <SPI.h>
#include <LoRa.h>
#include <DHTesp.h>
#include <Wire.h>
#include <MQUnifiedsensor.h> // Biblioteca matemática do MQ-9 readicionada

#define USAR_WIFI 1

#if USAR_WIFI
#include <WiFi.h>
#include <HTTPClient.h>
#endif

/* ==========================================================================
 * CONFIGURACOES E CONSTANTES
 * ========================================================================== */

// --- Rede Wi-Fi e Servidor ---
const char* WIFI_SSID           = "Jhonatan";
const char* WIFI_PASSWORD       = "jhon2020";
const char* ENDPOINT_SERVIDOR   = "http://172.26.150.249:5000/lora_event";

// --- Tempos e Timeouts ---
const unsigned long TIMEOUT_WIFI_MS   = 30000;
const unsigned long TIMEOUT_HTTP_MS   = 10000;
const unsigned long TEMPO_FASE_MS     = 300000; // 5 minutos por fase
const unsigned long INTERVALO_LEITURA = 2000;   // 2 segundos entre leituras

// --- Limites de seguranca e persistencia ---
const int LEITURAS_PARA_ALARME = 30;   // 30 leituras seguidas = cerca de 60 segundos
const float LIMIAR_MQ9_RISCO   = 30.0; // LIMITE VOLTOU PARA PPM (30 PPM = Perigo na Cabine)

// --- Pinos de Hardware ---
const int PINO_DHT   = 17;
const int PINO_MQ9   = 32; // Entrada analogica ADC1 do ESP32
const int PINO_LED   = 25; // LED branco embutido na placa Heltec V2
const int LORA_SCK   = 5;
const int LORA_MISO  = 19;
const int LORA_MOSI  = 27;
const int LORA_SS    = 18;
const int LORA_RST   = 14;
const int LORA_DIO0  = 26;
const long FREQUENCIA_BR = 915E6; // 915 MHz (Padrao Brasil)

// --- Parametros de Calibracao (MQ-9 / Monoxido de Carbono) ---
const float RATIO_MQ9_CLEAN_AIR = 9.6;
const float MQ9_CURVA_A         = 599.65;
const float MQ9_CURVA_B         = -2.244;

/* ==========================================================================
 * ESTRUTURAS DE DADOS E VARIAVEIS GLOBAIS
 * ========================================================================== */

struct DadosSensores {
    float temperatura;
    float umidade;
    float mq9; // Transformado em DECIMAL (float) para armazenar PPM
};

DadosSensores leiturasAtuais = {0.0, 0.0, 0.0};

struct EstadoSistema {
    int contadorPerigoTermico;
    int contadorPerigoMQ9;
    bool modoLeituraAtivo;
    bool emEmergencia;
    unsigned long cronometroFase;
    unsigned long ultimaLeituraSensores;
    bool novaLeituraDisponivel;
};

EstadoSistema estadoApp = {0, 0, false, false, 0, 0, false};

DHTesp dhtSensor;
// Objeto matematico do MQ-9 configurado para o ESP32 (3.3v, 12 bits)
MQUnifiedsensor mqSensor("ESP-32", 3.3, 12, PINO_MQ9, "MQ-9"); 

/* ==========================================================================
 * PROTOTIPOS DE FUNCOES
 * ========================================================================== */

void inicializarHardware();
void inicializarSensores();
void inicializarRede();
void gerenciarCicloDeEstados();
void realizarLeituraSensores();
int classificarRiscoTermico(float temperatura, float umidade);
bool classificarRiscoMQ9(float leituraMQ9); // Atualizado para float
void verificarRiscoContinuo();
bool enviarDadosParaServidor(float temperatura, float umidade, float leituraMQ9, bool riscoTermico, bool riscoMQ9); // Atualizado para float

/* ==========================================================================
 * SETUP E LOOP PRINCIPAL
 * ========================================================================== */

void setup()
{
    Serial.begin(115200);
    Serial.println("\n[SISTEMA] Iniciando sistema DHT22 + MQ-9...");

    // 1. Liga o Rádio LoRa
    inicializarHardware(); 
    
    // 2. O Fôlego Elétrico: Aguarda a tensão estabilizar (Evita o Brownout)
    delay(1000); 

    // 3. Inicializa e calibra os sensores
    inicializarSensores();

    // 4. Liga o Wi-Fi 
#if USAR_WIFI
    inicializarRede();
#else
    Serial.println("[REDE] Wi-Fi desativado neste build de diagnostico.");
#endif

    estadoApp.cronometroFase = millis();
    Serial.println("\n[CICLO] Fase 1 iniciada: HIBERNANDO por " + String(TEMPO_FASE_MS / 1000) + " segundos...");
}

void loop()
{
    gerenciarCicloDeEstados();
    realizarLeituraSensores();
    verificarRiscoContinuo();
    delay(100);
}

/* ==========================================================================
 * LOGICA DE INTELIGENCIA ARTIFICIAL (Arvore de Decisao)
 * ========================================================================== */

int classificarRiscoTermico(float temperatura, float umidade)
{
    if (temperatura > 26.45 && temperatura <= 26.75 && umidade <= 52.65) return 1;
    if (temperatura > 26.75 && temperatura <= 27.65 && umidade > 43.10 && umidade <= 46.70) return 1;
    if (temperatura > 27.65 && temperatura <= 28.45 && umidade <= 52.15) return 1;
    if (temperatura > 29.00) return 1;
    return 0;
}

bool classificarRiscoMQ9(float leituraMQ9) // Recebe o decimal (PPM)
{
    return leituraMQ9 >= LIMIAR_MQ9_RISCO;
}

/* ==========================================================================
 * AVALIACAO DE PERSISTENCIA
 * ========================================================================== */

void verificarRiscoContinuo()
{
    if (!estadoApp.modoLeituraAtivo || estadoApp.emEmergencia || !estadoApp.novaLeituraDisponivel) return;

    estadoApp.novaLeituraDisponivel = false;

    bool riscoTermico = classificarRiscoTermico(leiturasAtuais.temperatura, leiturasAtuais.umidade) == 1;
    bool riscoMQ9 = classificarRiscoMQ9(leiturasAtuais.mq9);

    if (riscoTermico) {
        estadoApp.contadorPerigoTermico++;
    } else {
        estadoApp.contadorPerigoTermico = 0;
    }

    if (riscoMQ9) {
        estadoApp.contadorPerigoMQ9++;
    } else {
        estadoApp.contadorPerigoMQ9 = 0;
    }

    if (estadoApp.contadorPerigoTermico >= LEITURAS_PARA_ALARME ||
        estadoApp.contadorPerigoMQ9 >= LEITURAS_PARA_ALARME)
    {
        Serial.println("\n=======================================================");
        if (estadoApp.contadorPerigoMQ9 >= LEITURAS_PARA_ALARME) {
            Serial.println("[ALERTA] EMERGENCIA CONFIRMADA: RISCO DE CO (MQ-9)");
        }
        if (estadoApp.contadorPerigoTermico >= LEITURAS_PARA_ALARME) {
            Serial.println("[ALERTA] EMERGENCIA CONFIRMADA: RISCO TERMICO DHT22");
        }
        Serial.println("=======================================================");

        bool sucesso = enviarDadosParaServidor(
            leiturasAtuais.temperatura,
            leiturasAtuais.umidade,
            leiturasAtuais.mq9,
            riscoTermico,
            riscoMQ9
        );

        if (sucesso) {
            estadoApp.emEmergencia = true;
        }
    }
}

/* ==========================================================================
 * GERENCIAMENTO DE ESTADOS (Hibernar / Ler)
 * ========================================================================== */

void gerenciarCicloDeEstados()
{
    if (millis() - estadoApp.cronometroFase < TEMPO_FASE_MS) return;

    estadoApp.cronometroFase = millis();
    estadoApp.modoLeituraAtivo = !estadoApp.modoLeituraAtivo;

    if (estadoApp.modoLeituraAtivo)
    {
        Serial.println("\n[CICLO] Fase 2: ACORDANDO! Iniciando leituras dos sensores...");
        estadoApp.emEmergencia = false;
        estadoApp.contadorPerigoTermico = 0;
        estadoApp.contadorPerigoMQ9 = 0;
        estadoApp.ultimaLeituraSensores = 0;
        estadoApp.novaLeituraDisponivel = false;
    }
    else
    {
        Serial.println("\n[CICLO] Fase 1: HIBERNANDO. As leituras voltarao em " + String(TEMPO_FASE_MS / 1000) + " minutos...");
        if (!estadoApp.emEmergencia) {
            bool riscoTermico = classificarRiscoTermico(leiturasAtuais.temperatura, leiturasAtuais.umidade) == 1;
            bool riscoMQ9 = classificarRiscoMQ9(leiturasAtuais.mq9);
            Serial.println("[REDE] Enviando pacote de rotina do ciclo concluido...");
            enviarDadosParaServidor(leiturasAtuais.temperatura, leiturasAtuais.umidade, leiturasAtuais.mq9, riscoTermico, riscoMQ9);
        }
    }
}

void realizarLeituraSensores()
{
    if (!estadoApp.modoLeituraAtivo) return;

    unsigned long agora = millis();
    if (estadoApp.ultimaLeituraSensores != 0 &&
        agora - estadoApp.ultimaLeituraSensores < INTERVALO_LEITURA) {
        return;
    }

    estadoApp.ultimaLeituraSensores = agora;

    TempAndHumidity data = dhtSensor.getTempAndHumidity();
    
    // --- Calculo Logaritmico do Gás (Decimais / PPM) ---
    mqSensor.update(); // Puxa a voltagem bruta
    float ppmCO = mqSensor.readSensor(false, 0.0); // Converte para a unidade PPM

    if (!isnan(data.temperature) && !isnan(data.humidity)) {
        leiturasAtuais.temperatura = data.temperature;
        leiturasAtuais.umidade = data.humidity;
        leiturasAtuais.mq9 = ppmCO; // Armazena o valor com decimais
        estadoApp.novaLeituraDisponivel = true;

        Serial.println(
            "[SENSORES] Temp: " + String(data.temperature, 1) +
            " C | Umi: " + String(data.humidity, 1) +
            "% | CO: " + String(leiturasAtuais.mq9, 2) + " PPM" // Exibe com 2 casas decimais
        );
    } else {
        Serial.println("[DHT22] Falha ao ler. CO Atual: " + String(ppmCO, 2) + " PPM");
    }
}

/* ==========================================================================
 * INICIALIZACOES DE HARDWARE, SENSORES E REDE
 * ========================================================================== */

void inicializarHardware()
{
    pinMode(PINO_LED, OUTPUT);
    digitalWrite(PINO_LED, LOW);
    pinMode(PINO_MQ9, INPUT);

    SPI.begin(LORA_SCK, LORA_MISO, LORA_MOSI, LORA_SS);
    LoRa.setPins(LORA_SS, LORA_RST, LORA_DIO0);
    if (!LoRa.begin(FREQUENCIA_BR)) {
        Serial.println("[HARDWARE] AVISO: Radio LoRa nao detectado.");
    } else {
        Serial.println("[HARDWARE] Radio LoRa inicializado.");
    }
}

void inicializarSensores()
{
    dhtSensor.setup(PINO_DHT, DHTesp::DHT22);
    
    // Configuracao da biblioteca matematica do MQ-9
    mqSensor.setRegressionMethod(1); // Linear
    mqSensor.setA(MQ9_CURVA_A); 
    mqSensor.setB(MQ9_CURVA_B); 
    mqSensor.init();

    Serial.print("[SENSORES] Calibrando resistencia do ar limpo (MQ-9)...");
    float calcR0 = 0;
    for(int i = 1; i <= 10; i++) {
        mqSensor.update(); 
        calcR0 += mqSensor.calibrate(RATIO_MQ9_CLEAN_AIR);
        delay(100);
    }
    mqSensor.setR0(calcR0 / 10.0);
    Serial.println(" Concluido!");
}

void inicializarRede()
{
#if USAR_WIFI
    Serial.println("[REDE] Conectando ao Wi-Fi...");

    WiFi.mode(WIFI_STA);
    
    // --- Atenuacao de Potencia RF (A Salvação contra o Brownout) ---
    WiFi.setTxPower(WIFI_POWER_8_5dBm); 
    
    WiFi.setSleep(false);
    WiFi.disconnect(false);
    delay(500); 

    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

    unsigned long inicio = millis();
    bool ledEstado = false;

    while (WiFi.status() != WL_CONNECTED && millis() - inicio < TIMEOUT_WIFI_MS) {
        ledEstado = !ledEstado;
        digitalWrite(PINO_LED, ledEstado ? HIGH : LOW);
        delay(500);
        Serial.print(".");
    }

    if (WiFi.status() == WL_CONNECTED) {
        Serial.println("\n[REDE] Conectado com sucesso!");
        digitalWrite(PINO_LED, HIGH); 
    } else {
        Serial.println("\n[REDE] Falha ao conectar (Timeout).");
        digitalWrite(PINO_LED, LOW); 
    }
#else
    Serial.println("[REDE] Wi-Fi desativado. Inicializacao ignorada.");
#endif
}

bool enviarDadosParaServidor(float temperatura, float umidade, float leituraMQ9, bool riscoTermico, bool riscoMQ9)
{
#if USAR_WIFI
    if (WiFi.status() != WL_CONNECTED) {
        Serial.println("[REDE] Wi-Fi desconectado. Pacote nao enviado.");
        return false;
    }

    StaticJsonDocument<384> docJson;
    docJson["temperatura"] = temperatura;
    docJson["umidade"] = umidade;
    docJson["co"] = leituraMQ9; // Chave alterada para "co" (Monoxido de Carbono) e enviando decimal
    docJson["risco_termico"] = riscoTermico;
    docJson["risco_mq9"] = riscoMQ9;
    docJson["risco"] = riscoTermico || riscoMQ9;

    if (riscoTermico && riscoMQ9) {
        docJson["sensor_risco"] = "DHT22+MQ9";
    } else if (riscoMQ9) {
        docJson["sensor_risco"] = "MQ9";
    } else if (riscoTermico) {
        docJson["sensor_risco"] = "DHT22";
    } else {
        docJson["sensor_risco"] = "NENHUM";
    }

    String payload;
    serializeJson(docJson, payload);

    HTTPClient http;
    http.setTimeout(TIMEOUT_HTTP_MS);

    if (!http.begin(ENDPOINT_SERVIDOR)) {
        Serial.println("[REDE] Falha ao iniciar HTTP.");
        return false;
    }

    http.addHeader("Content-Type", "application/json");
    int httpCode = http.POST(payload);
    http.end();

    Serial.println("[REDE] HTTP " + String(httpCode) + " | Payload: " + payload);
    return (httpCode == 200 || httpCode == 201);
#else
    Serial.println("[REDE] Wi-Fi desativado. Pacote nao enviado.");
    return false;
#endif
}
