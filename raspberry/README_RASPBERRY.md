# Implantacao Raspberry Pi

Esta pasta contem apenas os arquivos necessarios para executar a OAK-D com o
modelo YOLOv8n OpenVINO na Raspberry Pi. Os arquivos originais do projeto nao
foram movidos.

## Instalar

Entre na pasta `raspberry/` e execute:

```bash
chmod +x scripts/*.sh
./scripts/install.sh
```

O script cria `venv/` dentro de `raspberry/` e instala `app/requirements.txt`.

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

## Testar YOLO OpenVINO

```bash
cd raspberry/app
source ../venv/bin/activate
python oakd_yolo_test.py --model ../models/best_yolov8n_openvino_model
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
python oakd_observation_test.py --model ../models/best_yolov8n_openvino_model
```

Relatorios:

```text
raspberry/results/reports/oakd_observation.csv
raspberry/results/reports/oakd_observation_summary.txt
```
