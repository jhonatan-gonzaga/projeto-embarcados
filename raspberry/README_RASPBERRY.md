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
```

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
