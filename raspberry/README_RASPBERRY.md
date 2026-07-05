# Implantacao Raspberry Pi

Esta pasta contem apenas os arquivos necessarios para executar a OAK-D com o
modelo YOLO11 OpenVINO na Raspberry Pi. Os arquivos originais do projeto nao
foram movidos.

## Instalar

Entre na pasta `raspberry/` e execute:

```bash
chmod +x scripts/*.sh
./scripts/install.sh
```

O script cria `venv/` dentro de `raspberry/` e instala `app/requirements.txt`.

## Menu de Execucao

No Manjaro:

```bash
cd raspberry
./menu_manjaro.sh
```

Na Raspberry Pi:

```bash
cd raspberry
./menu_raspberry.sh
```

Opcoes principais:

```text
0 - Ligar servidor
1 - Verificar conexao com OAK-D
2 - Verificar conexao com LoRa/sensores
3 - Testar somente a camera por 30 segundos
4 - Trocar modelo YOLO
5 - Modo padrao: aguardar LoRa enviar sinal
6 - Ver imagem do results
7 - Sair
8 - Rodar observacao rapida manual
9 - Ver status do servidor/ultimo resultado
10 - Testar notificacao Telegram
11 - Fluxo real: LoRa envia sensores -> verificar -> Telegram
12 - Configurar Telegram
13 - Simular evento LoRa sensores -> Raspberry
14 - Descobrir chat_id do Telegram
```

No fluxo normal, use a opcao `5`. Ela liga o servidor Flask e aguarda a
Heltec/LoRa enviar `POST /lora_event` com os dados de sensores.

Para o fluxo real completo, use a opcao `11`. Ela garante a configuracao do
Telegram, liga o servidor e aguarda a Heltec/LoRa enviar `POST /lora_event`
com `temperatura`, `umidade` e `co`. Quando o sinal chegar, a Raspberry verifica a
OAK-D/YOLO e, se confirmar `ALERT_CHILD_ALONE`, envia Telegram com a imagem e
os dados de sensores recebidos da LoRa.

A configuracao do Telegram fica salva em `raspberry/.runtime/telegram_env`.
Se o Telegram retornar `Bad Request: chat not found`, abra o bot no Telegram,
envie `/start`, rode a opcao `14` para descobrir o `chat_id` correto e salve
esse ID na opcao `12`.

## Ativar Ambiente Virtual

```bash
cd raspberry
source venv/bin/activate
```

## Testar OAK-D

```bash
cd raspberry/app
source ../venv/bin/activate
python oakd_check.py
```

Saida esperada:

```text
OAK-D encontrada.
Dispositivo encontrado
MX ID: ...
Estado: ...
```

## Testar Camera

```bash
cd raspberry/app
source ../venv/bin/activate
python oakd_camera_test.py
```

Pressione `q` para encerrar.

## Converter YOLO11 para OpenVINO

Se `raspberry/yolo11.pt` ainda nao foi convertido, execute:

```bash
cd raspberry
source venv/bin/activate
python scripts/convert_yolo11_openvino.py
```

O modelo convertido fica em:

```text
raspberry/models/yolo11_openvino_model
```

## Testar YOLO11 OpenVINO

```bash
cd raspberry/app
source ../venv/bin/activate
python oakd_yolo_test.py --model ../models/yolo11_openvino_model
```

O benchmark fica em:

```text
raspberry/results/reports/oakd_benchmark.csv
```

## Testar Flask

```bash
cd raspberry
./scripts/start_server.sh
```

Em outro terminal:

```bash
curl http://localhost:5000/health
```

## Testar Endpoint /check_car

```bash
curl "http://localhost:5000/check_car?duration=180&sample_interval=1.0"
```

Para teste rapido:

```bash
curl "http://localhost:5000/check_car?duration=10&sample_interval=1.0"
```

O endpoint executa `oakd_observation_test.py` e retorna o resumo final em JSON.

## Testar Fluxo LoRa Sensores

Com o servidor ligado, simule a Heltec enviando temperatura, umidade e CO:

```bash
curl -X POST "http://localhost:5000/lora_event?duration=10&sample_interval=1.0" \
  -H "Content-Type: application/json" \
  -d '{"temperatura":32.5,"umidade":60.0,"co":18.0}'
```

Esse endpoint salva os dados de sensores, inicia a observacao OAK-D/YOLO e, se o
resultado final for `ALERT_CHILD_ALONE`, tenta enviar o Telegram com imagem,
temperatura, umidade e CO.

## Executar Observacao

```bash
cd raspberry
./scripts/start_observation.sh
```

Ou manualmente:

```bash
cd raspberry/app
source ../venv/bin/activate
python oakd_observation_test.py --model ../models/yolo11_openvino_model
```

Relatorios:

```text
raspberry/results/reports/oakd_observation.csv
raspberry/results/reports/oakd_observation_summary.txt
```


