"""
Exemplo de uso:

python oakd_observation_test.py --model models/best_yolov8n_openvino_model --duration 180 --sample-interval 1.0

Modo de observacao:
- Mantem a OAK-D ligada por ate 3 minutos.
- A cada intervalo configurado, coleta uma amostra.
- No final, decide se crianca sozinha foi confirmada por presenca estatistica.
"""

import argparse
import csv
import time
from pathlib import Path

import cv2
import depthai as dai

from oakd_yolo_test import carregar_modelo, executar_inferencia, inicializar_camera, listar_dispositivos


OBSERVATION_SECONDS = 180
SAMPLE_INTERVAL = 1.0
CHILD_MIN_PRESENCE = 0.20
ADULT_MAX_PRESENCE = 0.05
MIN_AVG_CONF = 0.60

ADULT_CLASSES = ["adult", "adultface"]
CHILD_CLASSES = ["child"]

REPORT_PATH = Path("../results/reports/oakd_observation.csv")
SUMMARY_PATH = Path("../results/reports/oakd_observation_summary.txt")


def normalizar_classe(class_name):
    """Normaliza nomes de classe para comparar sem depender de maiusculas."""
    return str(class_name).strip().lower()


def analisar_resultado(result):
    """Extrai maior confianca de child e adult/adultface acima do limiar."""
    child_conf_max = 0.0
    adult_conf_max = 0.0

    for box in result.boxes:
        class_id = int(box.cls[0])
        class_name = normalizar_classe(result.names[class_id])
        confidence = float(box.conf[0])

        if confidence < MIN_AVG_CONF:
            continue

        if class_name in CHILD_CLASSES:
            child_conf_max = max(child_conf_max, confidence)
        elif class_name in ADULT_CLASSES:
            adult_conf_max = max(adult_conf_max, confidence)

    child_detected = child_conf_max >= MIN_AVG_CONF
    adult_detected = adult_conf_max >= MIN_AVG_CONF

    return child_detected, child_conf_max, adult_detected, adult_conf_max


def calcular_metricas(samples):
    """Calcula presenca e confianca media com base nas amostras coletadas."""
    total_samples = len(samples)
    child_samples = sum(1 for sample in samples if sample["child_detected"])
    adult_samples = sum(1 for sample in samples if sample["adult_detected"])

    child_conf_values = [sample["child_conf_max"] for sample in samples if sample["child_detected"]]
    adult_conf_values = [sample["adult_conf_max"] for sample in samples if sample["adult_detected"]]

    child_presence_ratio = child_samples / total_samples if total_samples else 0.0
    adult_presence_ratio = adult_samples / total_samples if total_samples else 0.0
    child_avg_conf = sum(child_conf_values) / len(child_conf_values) if child_conf_values else 0.0
    adult_avg_conf = sum(adult_conf_values) / len(adult_conf_values) if adult_conf_values else 0.0

    return {
        "total_samples": total_samples,
        "child_samples": child_samples,
        "adult_samples": adult_samples,
        "child_presence_ratio": child_presence_ratio,
        "adult_presence_ratio": adult_presence_ratio,
        "child_avg_conf": child_avg_conf,
        "adult_avg_conf": adult_avg_conf,
    }


def decidir_status_parcial(metrics):
    """Gera status parcial durante a observacao."""
    if (
        metrics["child_presence_ratio"] >= CHILD_MIN_PRESENCE
        and metrics["adult_presence_ratio"] <= ADULT_MAX_PRESENCE
        and metrics["child_avg_conf"] >= MIN_AVG_CONF
    ):
        return "CRIANCA_SOZINHA_PARCIAL"
    if metrics["adult_presence_ratio"] > ADULT_MAX_PRESENCE:
        return "ADULTO_PRESENTE"
    if metrics["child_presence_ratio"] > 0:
        return "CRIANCA_DETECTADA_EM_OBSERVACAO"
    return "OBSERVANDO"


def decidir_final(metrics):
    """Aplica a regra final apos o periodo de observacao."""
    if (
        metrics["child_presence_ratio"] >= CHILD_MIN_PRESENCE
        and metrics["adult_presence_ratio"] <= ADULT_MAX_PRESENCE
        and metrics["child_avg_conf"] >= MIN_AVG_CONF
    ):
        return "CRIANCA_SOZINHA_CONFIRMADA"
    if metrics["adult_presence_ratio"] > ADULT_MAX_PRESENCE:
        return "ADULTO_PRESENTE"
    if metrics["child_presence_ratio"] > 0:
        return "CRIANCA_DETECTADA_MAS_NAO_CONFIRMADA"
    return "NENHUMA_PRESENCA_CONFIRMADA"


def preparar_csv():
    """Cria CSV de observacao e retorna arquivo e writer."""
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    file = REPORT_PATH.open("w", newline="", encoding="utf-8")
    fieldnames = [
        "timestamp",
        "sample_index",
        "child_detected",
        "child_conf_max",
        "adult_detected",
        "adult_conf_max",
        "child_presence_ratio",
        "adult_presence_ratio",
        "partial_status",
    ]
    writer = csv.DictWriter(file, fieldnames=fieldnames)
    writer.writeheader()
    return file, writer


def salvar_amostra(writer, sample, metrics, partial_status):
    """Salva uma linha no CSV com a amostra e as metricas acumuladas."""
    writer.writerow(
        {
            "timestamp": sample["timestamp"],
            "sample_index": sample["sample_index"],
            "child_detected": sample["child_detected"],
            "child_conf_max": round(sample["child_conf_max"], 4),
            "adult_detected": sample["adult_detected"],
            "adult_conf_max": round(sample["adult_conf_max"], 4),
            "child_presence_ratio": round(metrics["child_presence_ratio"], 4),
            "adult_presence_ratio": round(metrics["adult_presence_ratio"], 4),
            "partial_status": partial_status,
        }
    )


def salvar_resumo(metrics, final_decision):
    """Salva resumo final em TXT."""
    SUMMARY_PATH.parent.mkdir(parents=True, exist_ok=True)
    with SUMMARY_PATH.open("w", encoding="utf-8") as file:
        file.write(f"total_samples: {metrics['total_samples']}\n")
        file.write(f"child_samples: {metrics['child_samples']}\n")
        file.write(f"adult_samples: {metrics['adult_samples']}\n")
        file.write(f"child_presence_ratio: {metrics['child_presence_ratio']:.4f}\n")
        file.write(f"adult_presence_ratio: {metrics['adult_presence_ratio']:.4f}\n")
        file.write(f"child_avg_conf: {metrics['child_avg_conf']:.4f}\n")
        file.write(f"adult_avg_conf: {metrics['adult_avg_conf']:.4f}\n")
        file.write(f"final_decision: {final_decision}\n")


def desenhar_tela(frame, remaining_seconds, metrics, partial_status):
    """Mostra progresso da observacao na tela."""
    child_percent = metrics["child_presence_ratio"] * 100
    adult_percent = metrics["adult_presence_ratio"] * 100

    cv2.putText(frame, f"Tempo restante: {remaining_seconds:.0f}s", (20, 35), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
    cv2.putText(frame, f"Amostras: {metrics['total_samples']}", (20, 70), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
    cv2.putText(frame, f"Child presence: {child_percent:.1f}%", (20, 105), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
    cv2.putText(frame, f"Adult presence: {adult_percent:.1f}%", (20, 140), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
    cv2.putText(frame, f"Status: {partial_status}", (20, 180), cv2.FONT_HERSHEY_SIMPLEX, 0.75, (0, 255, 255), 2)

    return frame


def executar_observacao(model, queue, duration, sample_interval):
    """Executa observacao por tempo limitado, amostrando a cada intervalo."""
    samples = []
    csv_file, csv_writer = preparar_csv()

    warmup_packet = queue.get()
    warmup_frame = warmup_packet.getCvFrame()
    executar_inferencia(model, warmup_frame)
    print("Warm-up do modelo concluido. Iniciando cronometro de observacao.")

    start_time = time.perf_counter()
    next_sample_time = start_time
    sample_index = 0
    last_frame = None
    partial_status = "OBSERVANDO"
    metrics = calcular_metricas(samples)

    print("Modo de observacao iniciado. Pressione 'q' para encerrar antes do tempo.")

    try:
        while True:
            now = time.perf_counter()
            elapsed = now - start_time
            remaining = max(0.0, duration - elapsed)

            if elapsed >= duration:
                break

            packet = queue.get()
            frame = packet.getCvFrame()
            last_frame = frame

            if now >= next_sample_time:
                result = executar_inferencia(model, frame)
                child_detected, child_conf_max, adult_detected, adult_conf_max = analisar_resultado(result)

                sample_index += 1
                sample = {
                    "timestamp": time.time(),
                    "sample_index": sample_index,
                    "child_detected": child_detected,
                    "child_conf_max": child_conf_max,
                    "adult_detected": adult_detected,
                    "adult_conf_max": adult_conf_max,
                }
                samples.append(sample)

                metrics = calcular_metricas(samples)
                partial_status = decidir_status_parcial(metrics)
                salvar_amostra(csv_writer, sample, metrics, partial_status)
                csv_file.flush()

                print(
                    f"Amostra {sample_index} | "
                    f"child={child_detected} conf={child_conf_max:.3f} | "
                    f"adult={adult_detected} conf={adult_conf_max:.3f} | "
                    f"child_presence={metrics['child_presence_ratio']:.2%} | "
                    f"adult_presence={metrics['adult_presence_ratio']:.2%} | "
                    f"status={partial_status}"
                )

                # Agenda a proxima coleta a partir do fim da amostra atual.
                # Isso evita rajadas quando a primeira inferencia demora.
                next_sample_time = time.perf_counter() + sample_interval

            display = desenhar_tela(frame.copy(), remaining, metrics, partial_status)
            cv2.imshow("OAK-D Observation Mode", display)

            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
    finally:
        csv_file.close()
        cv2.destroyAllWindows()

    metrics = calcular_metricas(samples)
    final_decision = decidir_final(metrics)
    salvar_resumo(metrics, final_decision)

    print("\nResumo final")
    print("-" * 40)
    print(f"total_samples: {metrics['total_samples']}")
    print(f"child_samples: {metrics['child_samples']}")
    print(f"adult_samples: {metrics['adult_samples']}")
    print(f"child_presence_ratio: {metrics['child_presence_ratio']:.4f}")
    print(f"adult_presence_ratio: {metrics['adult_presence_ratio']:.4f}")
    print(f"child_avg_conf: {metrics['child_avg_conf']:.4f}")
    print(f"adult_avg_conf: {metrics['adult_avg_conf']:.4f}")
    print(f"final_decision: {final_decision}")
    print(f"CSV salvo em: {REPORT_PATH}")
    print(f"Resumo salvo em: {SUMMARY_PATH}")

    return last_frame, metrics, final_decision


def main():
    parser = argparse.ArgumentParser(description="Modo de observacao OAK-D + YOLOv8n OpenVINO.")
    parser.add_argument("--model", default="../models/best_yolov8n_openvino_model", help="Pasta do modelo OpenVINO.")
    parser.add_argument("--duration", type=float, default=OBSERVATION_SECONDS, help="Duracao da observacao em segundos.")
    parser.add_argument("--sample-interval", type=float, default=SAMPLE_INTERVAL, help="Intervalo entre amostras em segundos.")
    args = parser.parse_args()

    if args.duration <= 0:
        raise ValueError("--duration deve ser maior que zero.")
    if args.sample_interval <= 0:
        raise ValueError("--sample-interval deve ser maior que zero.")

    if not listar_dispositivos():
        return

    model = carregar_modelo(args.model)
    api_version, device, pipeline, queue_info = inicializar_camera()

    if api_version == "v3":
        with pipeline:
            pipeline.start()
            executar_observacao(model, queue_info, args.duration, args.sample_interval)
    else:
        with dai.Device(pipeline) as device:
            queue = device.getOutputQueue(name=queue_info, maxSize=4, blocking=False)
            executar_observacao(model, queue, args.duration, args.sample_interval)


if __name__ == "__main__":
    main()
