/* ==========================================================================
 * PROJETO: Sistema Embarcado de Monitoramento Veicular (ESP32 / LoRa32)
 * DESCRIÇÃO: Coleta de dados com IA Embarcada (Árvore de Decisão) e 
 * Validação por Persistência para evitar falsos alarmes.
 * ========================================================================== */

#include <ArduinoJson.h>
#include <WiFi.h>
#include <HTTPClient.h>
#include <Adafruit_SSD1306.h>
#include <SPI.h>
#include <LoRa.h>
#include <DHTesp.h>
#include <MQUnifiedsensor.h>
#include <Wire.h>

/* ==========================================================================
 * CONFIGURAÇÕES E CONSTANTES
 * ========================================================================== */

// --- Rede Wi-Fi e Servidor ---
const char* WIFI_SSID           = "Pedro Arthur_2.4GHz";
const char* WIFI_PASSWORD       = "Pa29R11T10";
const char* ENDPOINT_SERVIDOR   = "http://192.168.0.11:5000/sensor_data";

// --- Tempos e Timeouts ---
const unsigned long TIMEOUT_WIFI_MS = 20000;
const unsigned long TIMEOUT_HTTP_MS = 10000;
const unsigned long TEMPO_FASE_MS   = 300000; // 5 minutos por fase
const unsigned long INTERVALO_LEITURA = 2000; // 2 segundos entre leituras

// --- LIMITES DE SEGURANÇA E PERSISTÊNCIA ---
const float LIMITE_PERIGOSO_CO = 30.0; // PPM (Ajuste conforme seus testes reais)
const int LEITURAS_PARA_ALARME = 5;    // Exige 5 leituras de perigo seguidas (10 segundos)

// --- Pinos de Hardware ---
const int PINO_DHT   = 17;
const int PINO_MQ9   = 32;
const int OLED_RST   = 16;
const int LORA_SS    = 18;
const int LORA_RST   = 14;
const int LORA_DIO0  = 26;
const long FREQUENCIA_BR = 915E6; // 915 MHz (Padrão Brasil)

// --- Parâmetros de Calibração (MQ-9) ---
const float RATIO_MQ9_CLEAN_AIR = 9.6;
const float MQ9_CURVA_A         = 599.65;
const float MQ9_CURVA_B         = -2.244;

// --- Configurações do FreeRTOS ---
const int NUCLEO_0 = 0;
const int NUCLEO_1 = 1;

/* ==========================================================================
 * ESTRUTURAS DE DADOS E VARIÁVEIS GLOBAIS
 * ========================================================================== */

struct DadosSensores {
    volatile float temperatura;
    volatile float umidade;
    volatile float monoxidoCarbono;
};

DadosSensores leiturasAtuais = {0.0, 0.0, 0.0};

struct EstadoSistema {
    volatile int contadorPerigoTermico;
    volatile int contadorPerigoToxico;
    volatile bool modoLeituraAtivo;
    volatile bool emEmergencia; // Trava para não enviar 1000 JSONs seguidos
    unsigned long cronometroFase;
};

EstadoSistema estadoApp = {0, 0, false, false, 0};

Adafruit_SSD1306 display(128, 64, &Wire, OLED_RST);
DHTesp dhtSensor;
MQUnifiedsensor mqSensor("ESP-32", 3.3, 12, PINO_MQ9, "MQ-9"); 

TaskHandle_t taskHandleDHT = NULL; 
TaskHandle_t taskHandleMQ9 = NULL; 

/* ==========================================================================
 * PROTÓTIPOS DE FUNÇÕES
 * ========================================================================== */
void inicializarHardware();
void inicializarSensores();
void inicializarRede();
void gerenciarCicloDeEstados();
int classificarRiscoTermico(float temperatura, float humidade);
void verificarRiscoContinuo();
bool enviarDadosParaServidor(float co2, float temperatura, float umidade);
void taskLeituraDHT(void *pvParameters);
void taskLeituraMQ9(void *pvParameters);

/* ==========================================================================
 * SETUP E LOOP PRINCIPAL
 * ========================================================================== */

void setup() 
{
    Serial.begin(115200);
    Serial.println("\n[SISTEMA] Iniciando Boot do Sistema...");

    inicializarHardware();
    inicializarSensores();
    inicializarRede();
    
    estadoApp.cronometroFase = millis();
    Serial.println("\n[CICLO] Fase 1 Iniciada: HIBERNANDO por 5 minutos...");
}

void loop() 
{ 
    gerenciarCicloDeEstados();
    verificarRiscoContinuo();
    delay(100); 
}

/* ==========================================================================
 * LÓGICA DE INTELIGÊNCIA ARTIFICIAL (Árvore de Decisão Extraída do Python)
 * ========================================================================== */

// Retorna 1 (Risco de Hipertermia) ou 0 (Seguro)
int classificarRiscoTermico(float temperatura, float humidade) {
    // Cenário 1
    if (temperatura > 26.45 && temperatura <= 26.75 && humidade <= 52.65) {
        return 1; 
    }
    // Cenário 2
    if (temperatura > 26.75 && temperatura <= 27.65 && humidade > 43.10 && humidade <= 46.70) {
        return 1; 
    }
    // Cenário 3
    if (temperatura > 27.65 && temperatura <= 28.45 && humidade <= 52.15) {
        return 1; 
    }
    // REGRA DE SEGURANÇA (Hard Rule): Acima de 29°C no Brasil num carro fechado é SEMPRE risco
    if (temperatura > 29.00) {
        return 1;
    }

    return 0; // Ambiente Seguro
}

/* ==========================================================================
 * AVALIAÇÃO DE PERSISTÊNCIA (A Solução para Alarmes Falsos)
 * ========================================================================== */

void verificarRiscoContinuo()
{
    // Se não estivermos na fase de leitura ou já enviou o alerta, não faz nada
    if (!estadoApp.modoLeituraAtivo || estadoApp.emEmergencia) return;

    // 1. Avalia o Risco Térmico usando a IA
    if (classificarRiscoTermico(leiturasAtuais.temperatura, leiturasAtuais.umidade) == 1) {
        estadoApp.contadorPerigoTermico++;
    } else {
        estadoApp.contadorPerigoTermico = 0; // Se ficou seguro, zera o contador
    }

    // 2. Avalia o Risco Tóxico
    if (leiturasAtuais.monoxidoCarbono > LIMITE_PERIGOSO_CO) {
        estadoApp.contadorPerigoToxico++;
    } else {
        estadoApp.contadorPerigoToxico = 0; // Se o gás dissipou, zera o contador
    }

    // 3. O VEREDICTO: Bateu 5 vezes seguidas? (10 segundos de perigo real)
    if (estadoApp.contadorPerigoTermico >= LEITURAS_PARA_ALARME || estadoApp.contadorPerigoToxico >= LEITURAS_PARA_ALARME) 
    {
        Serial.println("\n=======================================================");
        Serial.println("🚨 EMERGÊNCIA CONFIRMADA: RISCO DETETADO HÁ 10 SEGUNDOS 🚨");
        Serial.println("=======================================================");
        
        bool sucesso = enviarDadosParaServidor(
            leiturasAtuais.monoxidoCarbono, 
            leiturasAtuais.temperatura, 
            leiturasAtuais.umidade
        );

        if(sucesso) {
            // Trava o sistema para não enviar 1000 JSONs seguidos enquanto o perigo existir
            estadoApp.emEmergencia = true; 
        }
    }
}

/* ==========================================================================
 * GERENCIAMENTO DE ESTADOS (Hibernar / Ler)
 * ========================================================================== */

void gerenciarCicloDeEstados()
{
    if (millis() - estadoApp.cronometroFase >= TEMPO_FASE_MS) 
    {
        estadoApp.cronometroFase = millis(); 
        estadoApp.modoLeituraAtivo = !estadoApp.modoLeituraAtivo; 
        
        if (estadoApp.modoLeituraAtivo) 
        {
            Serial.println("\n[CICLO] Fase 2: ACORDANDO! Iniciando leituras contínuas (5 min)...");
            estadoApp.emEmergencia = false; // Destrava a emergência para um novo ciclo
            estadoApp.contadorPerigoTermico = 0;
            estadoApp.contadorPerigoToxico = 0;
            
            vTaskResume(taskHandleDHT);
            vTaskResume(taskHandleMQ9);
        } 
        else 
        {
            Serial.println("\n[CICLO] Fase 1: HIBERNANDO. As leituras voltarão em 5 minutos...");
            
            // Só envia o pacote de rotina (histórico) se não houve emergência neste ciclo
            if(!estadoApp.emEmergencia) {
                Serial.println("[REDE] Enviando pacote de rotina do ciclo concluído...");
                enviarDadosParaServidor(
                    leiturasAtuais.monoxidoCarbono, 
                    leiturasAtuais.temperatura, 
                    leiturasAtuais.umidade
                );
            }
        }
    }
}

/* ==========================================================================
 * TAREFAS DO FREERTOS (TASKS) E REDE (Apenas as atualizações das globais)
 * ========================================================================== */

void taskLeituraDHT(void *pvParameters)   
{
    while (1) {
        if (estadoApp.modoLeituraAtivo) {
            TempAndHumidity data = dhtSensor.getTempAndHumidity();
            if (!isnan(data.temperature) && !isnan(data.humidity)) {
                leiturasAtuais.temperatura = data.temperature;
                leiturasAtuais.umidade = data.humidity;
                Serial.println("[DHT22] Temp: " + String(data.temperature, 1) + "ºC | Umi: " + String(data.humidity, 1) + "%");
            }
            vTaskDelay(pdMS_TO_TICKS(INTERVALO_LEITURA)); 
        } else {
            vTaskSuspend(NULL);
        }
    }
}

void taskLeituraMQ9(void *pvParameters)
{
    while (1) {
        if (estadoApp.modoLeituraAtivo) {
            mqSensor.update();
            float ppm = mqSensor.readSensor(false, 0.0); 
            leiturasAtuais.monoxidoCarbono = ppm;
            Serial.println("[MQ-9] CO: " + String(ppm, 2) + " PPM");
            vTaskDelay(pdMS_TO_TICKS(INTERVALO_LEITURA)); 
        } else {
            vTaskSuspend(NULL);
        }
    }
}

// Inicializações de Hardware e Rede mantidas intactas...
void inicializarHardware() {
    LoRa.setPins(LORA_SS, LORA_RST, LORA_DIO0);
    if (!LoRa.begin(FREQUENCIA_BR)) {
        Serial.println("[HARDWARE] AVISO: Rádio LoRa não detectado.");
    }
}

void inicializarSensores() {
    dhtSensor.setup(PINO_DHT, DHTesp::DHT22); 
    mqSensor.setRegressionMethod(1); 
    mqSensor.setA(MQ9_CURVA_A); mqSensor.setB(MQ9_CURVA_B); 
    mqSensor.init();

    Serial.print("[SENSORES] Calibrando MQ-9 (Aguarde)");
    float calcR0 = 0;
    for(int i = 1; i <= 10; i++) {
        mqSensor.update(); 
        calcR0 += mqSensor.calibrate(RATIO_MQ9_CLEAN_AIR);
        delay(100);
    }
    mqSensor.setR0(calcR0 / 10.0);
    Serial.println(" Concluído!");

    xTaskCreatePinnedToCore(taskLeituraDHT, "Task_DHT", 10000, NULL, 4, &taskHandleDHT, NUCLEO_1); 
    xTaskCreatePinnedToCore(taskLeituraMQ9, "Task_MQ9", 10000, NULL, 5, &taskHandleMQ9, NUCLEO_1);
}

void inicializarRede() {
    Serial.println("[REDE] Conectando ao Wi-Fi...");
    
    // Configura o modo da antena
    WiFi.mode(WIFI_STA);
    
    // ===============================================================
    // ---> TRUQUE ANTI-BROWNOUT <---
    // Reduz a potência do rádio de 19.5dBm para 8.5dBm. 
    // Isso evita o pico de corrente de 500mA e salva o ESP32 do colapso!
    WiFi.setTxPower(WIFI_POWER_8_5dBm); 
    // ===============================================================

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

bool enviarDadosParaServidor(float co2, float temperatura, float umidade) {
    if (WiFi.status() != WL_CONNECTED) return false;
    StaticJsonDocument<200> docJson;
    docJson["co2"] = co2; docJson["temperatura"] = temperatura; docJson["humidade"] = umidade;
    String payload; serializeJson(docJson, payload);

    HTTPClient http; http.setTimeout(TIMEOUT_HTTP_MS);
    if (!http.begin(ENDPOINT_SERVIDOR)) return false;
    http.addHeader("Content-Type", "application/json");
    int httpCode = http.POST(payload);
    http.end();
    return (httpCode == 200 || httpCode == 201);
}
