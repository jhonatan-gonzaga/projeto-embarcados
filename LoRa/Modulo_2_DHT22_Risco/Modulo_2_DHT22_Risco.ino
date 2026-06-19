/* ==========================================================================
 * PROJETO: Sistema Embarcado de Monitoramento Veicular (ESP32 / LoRa32)
 * DESCRICAO: Versao focada apenas no DHT22.
 *            Verifica risco termico por temperatura/umidade, sem MQ-9.
 * ========================================================================== */

#include <ArduinoJson.h>
#include <WiFi.h>
#include <HTTPClient.h>
#include <SPI.h>
#include <LoRa.h>
#include <DHTesp.h>
#include <Wire.h>

/* ==========================================================================
 * CONFIGURACOES E CONSTANTES
 * ========================================================================== */

// --- Rede Wi-Fi e Servidor ---
const char* WIFI_SSID           = "Pedro Arthur_2.4GHz";
const char* WIFI_PASSWORD       = "Pa29R11T10";
const char* ENDPOINT_SERVIDOR   = "http://192.168.0.11:5000/sensor_data";

// --- Tempos e Timeouts ---
const unsigned long TIMEOUT_WIFI_MS   = 20000;
const unsigned long TIMEOUT_HTTP_MS   = 10000;
const unsigned long TEMPO_FASE_MS     = 300000; // 5 minutos por fase
const unsigned long INTERVALO_LEITURA = 2000;   // 2 segundos entre leituras

// --- Limites de seguranca e persistencia ---
const int LEITURAS_PARA_ALARME = 5; // 5 leituras seguidas = cerca de 10 segundos

// --- Pinos de Hardware ---
const int PINO_DHT   = 17;
const int LORA_SS    = 18;
const int LORA_RST   = 14;
const int LORA_DIO0  = 26;
const long FREQUENCIA_BR = 915E6; // 915 MHz (Padrao Brasil)

// --- Configuracoes do FreeRTOS ---
const int NUCLEO_1 = 1;

/* ==========================================================================
 * ESTRUTURAS DE DADOS E VARIAVEIS GLOBAIS
 * ========================================================================== */

struct DadosSensores {
    volatile float temperatura;
    volatile float umidade;
};

DadosSensores leiturasAtuais = {0.0, 0.0};

struct EstadoSistema {
    volatile int contadorPerigoTermico;
    volatile bool modoLeituraAtivo;
    volatile bool emEmergencia;
    unsigned long cronometroFase;
};

EstadoSistema estadoApp = {0, false, false, 0};

DHTesp dhtSensor;
TaskHandle_t taskHandleDHT = NULL;

/* ==========================================================================
 * PROTOTIPOS DE FUNCOES
 * ========================================================================== */

void inicializarHardware();
void inicializarSensores();
void inicializarRede();
void gerenciarCicloDeEstados();
int classificarRiscoTermico(float temperatura, float umidade);
void verificarRiscoContinuo();
bool enviarDadosParaServidor(float temperatura, float umidade, bool riscoTermico);
void taskLeituraDHT(void *pvParameters);

/* ==========================================================================
 * SETUP E LOOP PRINCIPAL
 * ========================================================================== */

void setup()
{
    Serial.begin(115200);
    Serial.println("\n[SISTEMA] Iniciando sistema DHT22 sem MQ-9...");

    inicializarHardware();
    inicializarSensores();
    inicializarRede();

    estadoApp.cronometroFase = millis();
    Serial.println("\n[CICLO] Fase 1 iniciada: HIBERNANDO por 5 minutos...");
}

void loop()
{
    gerenciarCicloDeEstados();
    verificarRiscoContinuo();
    delay(100);
}

/* ==========================================================================
 * LOGICA DE INTELIGENCIA ARTIFICIAL (Arvore de Decisao Extraida do Python)
 * ========================================================================== */

// Retorna 1 para risco de hipertermia ou 0 para ambiente seguro.
int classificarRiscoTermico(float temperatura, float umidade)
{
    // Cenario 1
    if (temperatura > 26.45 && temperatura <= 26.75 && umidade <= 52.65) {
        return 1;
    }

    // Cenario 2
    if (temperatura > 26.75 && temperatura <= 27.65 && umidade > 43.10 && umidade <= 46.70) {
        return 1;
    }

    // Cenario 3
    if (temperatura > 27.65 && temperatura <= 28.45 && umidade <= 52.15) {
        return 1;
    }

    // Regra de seguranca: acima de 29 C em carro fechado e sempre risco.
    if (temperatura > 29.00) {
        return 1;
    }

    return 0;
}

/* ==========================================================================
 * AVALIACAO DE PERSISTENCIA
 * ========================================================================== */

void verificarRiscoContinuo()
{
    if (!estadoApp.modoLeituraAtivo || estadoApp.emEmergencia) {
        return;
    }

    bool riscoTermico = classificarRiscoTermico(
        leiturasAtuais.temperatura,
        leiturasAtuais.umidade
    ) == 1;

    if (riscoTermico) {
        estadoApp.contadorPerigoTermico++;
    } else {
        estadoApp.contadorPerigoTermico = 0;
    }

    if (estadoApp.contadorPerigoTermico >= LEITURAS_PARA_ALARME)
    {
        Serial.println("\n=======================================================");
        Serial.println("[ALERTA] EMERGENCIA CONFIRMADA: RISCO TERMICO DHT22");
        Serial.println("=======================================================");

        bool sucesso = enviarDadosParaServidor(
            leiturasAtuais.temperatura,
            leiturasAtuais.umidade,
            true
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
    if (millis() - estadoApp.cronometroFase < TEMPO_FASE_MS) {
        return;
    }

    estadoApp.cronometroFase = millis();
    estadoApp.modoLeituraAtivo = !estadoApp.modoLeituraAtivo;

    if (estadoApp.modoLeituraAtivo)
    {
        Serial.println("\n[CICLO] Fase 2: ACORDANDO! Iniciando leituras do DHT22...");
        estadoApp.emEmergencia = false;
        estadoApp.contadorPerigoTermico = 0;

        vTaskResume(taskHandleDHT);
    }
    else
    {
        Serial.println("\n[CICLO] Fase 1: HIBERNANDO. As leituras voltarao em 5 minutos...");

        if (!estadoApp.emEmergencia) {
            bool riscoTermico = classificarRiscoTermico(
                leiturasAtuais.temperatura,
                leiturasAtuais.umidade
            ) == 1;

            Serial.println("[REDE] Enviando pacote de rotina do ciclo concluido...");
            enviarDadosParaServidor(
                leiturasAtuais.temperatura,
                leiturasAtuais.umidade,
                riscoTermico
            );
        }
    }
}

/* ==========================================================================
 * TAREFA DO FREERTOS
 * ========================================================================== */

void taskLeituraDHT(void *pvParameters)
{
    while (1) {
        if (estadoApp.modoLeituraAtivo) {
            TempAndHumidity data = dhtSensor.getTempAndHumidity();

            if (!isnan(data.temperature) && !isnan(data.humidity)) {
                leiturasAtuais.temperatura = data.temperature;
                leiturasAtuais.umidade = data.humidity;

                Serial.println(
                    "[DHT22] Temp: " + String(data.temperature, 1) +
                    " C | Umi: " + String(data.humidity, 1) + "%"
                );
            } else {
                Serial.println("[DHT22] Falha ao ler temperatura/umidade.");
            }

            vTaskDelay(pdMS_TO_TICKS(INTERVALO_LEITURA));
        } else {
            vTaskSuspend(NULL);
        }
    }
}

/* ==========================================================================
 * INICIALIZACOES DE HARDWARE, SENSORES E REDE
 * ========================================================================== */

void inicializarHardware()
{
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

    xTaskCreatePinnedToCore(
        taskLeituraDHT,
        "Task_DHT",
        10000,
        NULL,
        4,
        &taskHandleDHT,
        NUCLEO_1
    );
}

void inicializarRede()
{
    Serial.println("[REDE] Conectando ao Wi-Fi...");

    WiFi.mode(WIFI_STA);
    WiFi.setTxPower(WIFI_POWER_8_5dBm);
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

    unsigned long inicio = millis();
    while (WiFi.status() != WL_CONNECTED && millis() - inicio < TIMEOUT_WIFI_MS) {
        delay(500);
        Serial.print(".");
    }

    if (WiFi.status() == WL_CONNECTED) {
        Serial.println("\n[REDE] Conectado!");
    } else {
        Serial.println("\n[REDE] Falha ao conectar (Timeout).");
    }
}

bool enviarDadosParaServidor(float temperatura, float umidade, bool riscoTermico)
{
    if (WiFi.status() != WL_CONNECTED) {
        Serial.println("[REDE] Wi-Fi desconectado. Pacote nao enviado.");
        return false;
    }

    StaticJsonDocument<200> docJson;
    docJson["temperatura"] = temperatura;
    docJson["humidade"] = umidade;
    docJson["risco_termico"] = riscoTermico;
    docJson["sensor_risco"] = "DHT22";

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
}
