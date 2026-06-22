"""
Exemplo de uso:

python oakd_observation_test.py --model ../models/yolo11_openvino_model --duration 180 --sample-interval 1.0

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

from oakd_yolo_test import CONF_THRESHOLD, carregar_modelo, executar_inferencia, inicializar_camera, listar_dispositivos


OBSERVATION_SECONDS = 180
SAMPLE_INTERVAL = 1.0
CHILD_MIN_PRESENCE = 0.20
ADULT_MAX_PRESENCE = 0.05
MIN_CHILD_CONF = 0.60
MIN_ADULT_CONF = MIN_CHILD_CONF
DIAGNOSTIC_YOLO_CONF = 0.25

ADULT_CLASSES = ["adult", "adultface"]
CHILD_CLASSES = ["child"]

APP_DIR = Path(__file__).resolve().parent
RESULTS_DIR = APP_DIR / "../results"
REPORT_PATH = RESULTS_DIR / "reports/oakd_observation.csv"
SUMMARY_PATH = RESULTS_DIR / "reports/oakd_observation_summary.txt"
DEBUG_LOG_PATH = RESULTS_DIR / "reports/oakd_observation_debug.log"
LAST_ALERT_IMAGE_PATH = RESULTS_DIR / "images/last_child_alert.jpg"


def normalizar_classe(class_name):
    """Normaliza nomes de classe para comparar sem depender de maiusculas."""
    return str(class_name).strip().lower().replace("-", "").replace("_", "").replace(" ", "")


def obter_nome_classe(names, class_id):
    """Obtem nome de classe em modelos que usam dict ou lista."""
    if hasattr(names, "get"):
        return names.get(class_id, f"class_{class_id}")
    if 0 <= class_id < len(names):
        return names[class_id]
    return f"class_{class_id}"


def extrair_deteccoes(result):
    """Extrai todas as deteccoes do YOLO antes de aplicar filtros de decisao."""
    detections = []

    if result.boxes is None:
        return detections

    for box in result.boxes:
        class_id = int(box.cls[0])
        class_name = str(obter_nome_classe(result.names, class_id))
        normalized = normalizar_classe(class_name)
        confidence = float(box.conf[0])
        x1, y1, x2, y2 = [int(value) for value in box.xyxy[0].tolist()]
        detections.append(
            {
                "class_id": class_id,
                "class_name": class_name,
                "normalized": normalized,
                "confidence": confidence,
                "xyxy": (x1, y1, x2, y2),
            }
        )

    return detections


def formatar_deteccoes_resumo(detections):
    """Gera resumo curto das deteccoes para log e CSV."""
    if not detections:
        return "NO_BOXES"
    return ", ".join(f"{item['normalized']} {item['confidence']:.3f}" for item in detections)


def log_diagnostico(log_file, message):
    """Imprime e grava mensagens de diagnostico da observacao."""
    print(message)
    if log_file is not None:
        log_file.write(f"{message}\n")
        log_file.flush()


def imprimir_diagnostico_amostra(sample_index, detections, debug=False, log_file=None):
    """Imprime diagnostico das boxes antes e depois da normalizacao."""
    log_diagnostico(log_file, f"[DIAG] Amostra {sample_index} | Quantidade de boxes: {len(detections)}")

    if not detections:
        log_diagnostico(log_file, "[DIAG] result.boxes vazio nesta amostra.")
        return

    log_diagnostico(log_file, f"[DIAG] Deteccoes no frame: {formatar_deteccoes_resumo(detections)}")
    if debug:
        for item in detections:
            log_diagnostico(
                log_file,
                "Deteccao: "
                f"class_id={item['class_id']} "
                f"class_name={item['class_name']} "
                f"normalized={item['normalized']} "
                f"confidence={item['confidence']:.4f}"
            )


def analisar_resultado(result, detections=None, debug=False, log_file=None):
    """Extrai maior confianca de child e adult/adultface acima do limiar."""
    child_conf_max = 0.0
    adult_conf_max = 0.0
    detections = detections if detections is not None else extrair_deteccoes(result)

    for detection in detections:
        class_name = detection["normalized"]
        confidence = detection["confidence"]

        if class_name in CHILD_CLASSES:
            if confidence >= MIN_CHILD_CONF:
                child_conf_max = max(child_conf_max, confidence)
            elif debug:
                log_diagnostico(log_file, f"[DIAG] child ignorado por confianca baixa: {confidence:.4f} < {MIN_CHILD_CONF:.2f}")
        elif class_name in ADULT_CLASSES:
            if confidence >= MIN_ADULT_CONF:
                adult_conf_max = max(adult_conf_max, confidence)
            elif debug:
                log_diagnostico(log_file, f"[DIAG] adult/adultface ignorado por confianca baixa: {confidence:.4f} < {MIN_ADULT_CONF:.2f}")
        elif debug:
            log_diagnostico(log_file, f"[DIAG] classe ignorada por nome nao mapeado: {detection['class_name']} -> {class_name}")

    child_detected = child_conf_max >= MIN_CHILD_CONF
    adult_detected = adult_conf_max >= MIN_ADULT_CONF

    if debug:
        log_diagnostico(
            log_file,
            "[DIAG] Resultado apos filtros | "
            f"child_detected={child_detected} child_conf_max={child_conf_max:.4f} | "
            f"adult_detected={adult_detected} adult_conf_max={adult_conf_max:.4f}"
        )

    return child_detected, child_conf_max, adult_detected, adult_conf_max


def obter_melhor_child_conf(result, detections=None):
    """Retorna a maior confianca da classe child, mesmo antes da decisao final."""
    best_conf = 0.0
    detections = detections if detections is not None else extrair_deteccoes(result)

    for detection in detections:
        if detection["normalized"] in CHILD_CLASSES:
            best_conf = max(best_conf, detection["confidence"])

    return best_conf


def obter_melhor_child_detection(detections):
    """Retorna a deteccao child com maior confianca no frame atual."""
    best_detection = None

    for detection in detections:
        if detection["normalized"] not in CHILD_CLASSES:
            continue
        if best_detection is None or detection["confidence"] > best_detection["confidence"]:
            best_detection = detection

    return best_detection


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
        and metrics["child_avg_conf"] >= MIN_CHILD_CONF
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
        and metrics["child_avg_conf"] >= MIN_CHILD_CONF
    ):
        return "ALERT_CHILD_ALONE"
    if metrics["child_presence_ratio"] > 0:
        return "CRIANCA_DETECTADA_MAS_NAO_CONFIRMADA"
    return "NO_ALERT"


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
        "boxes_count",
        "detections",
        "raw_child_conf",
        "child_presence_ratio",
        "adult_presence_ratio",
        "partial_status",
    ]
    writer = csv.DictWriter(file, fieldnames=fieldnames)
    writer.writeheader()
    return file, writer


def preparar_debug_log():
    """Cria arquivo de diagnostico detalhado da observacao."""
    DEBUG_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    return DEBUG_LOG_PATH.open("w", encoding="utf-8")


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
            "boxes_count": sample["boxes_count"],
            "detections": sample["detections"],
            "raw_child_conf": round(sample["raw_child_conf"], 4),
            "child_presence_ratio": round(metrics["child_presence_ratio"], 4),
            "adult_presence_ratio": round(metrics["adult_presence_ratio"], 4),
            "partial_status": partial_status,
        }
    )


def salvar_resumo(metrics, final_decision, best_child_conf=0.0, alert_image_path="", best_child_timestamp=0.0):
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
        file.write(f"best_child_conf: {best_child_conf:.4f}\n")
        file.write(f"alert_image_path: {alert_image_path}\n")
        file.write(f"best_child_timestamp: {best_child_timestamp:.6f}\n")


def desenhar_frame_melhor_child(frame, detections, final_decision, timestamp):
    """Desenha boxes, classes, confiancas, timestamp e decisao no melhor frame."""
    annotated = frame.copy()
    readable_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(timestamp))

    for detection in detections:
        x1, y1, x2, y2 = detection["xyxy"]
        is_child = detection["normalized"] in CHILD_CLASSES
        color = (0, 255, 0) if is_child else (0, 180, 255)
        label = f"{detection['class_name']} {detection['confidence']:.2f}"

        cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 2)
        label_y = max(20, y1 - 8)
        cv2.putText(annotated, label, (x1, label_y), cv2.FONT_HERSHEY_SIMPLEX, 0.65, color, 2)

    cv2.putText(annotated, f"timestamp: {readable_time}", (20, 35), cv2.FONT_HERSHEY_SIMPLEX, 0.75, (255, 255, 255), 2)
    cv2.putText(annotated, f"final_decision: {final_decision}", (20, 70), cv2.FONT_HERSHEY_SIMPLEX, 0.75, (255, 255, 255), 2)
    return annotated


def salvar_frame_alerta(frame, detections, final_decision, timestamp):
    """Salva a imagem anotada do melhor frame child para consulta pelo Flask."""
    if frame is None or frame.size == 0:
        raise RuntimeError("Frame vazio; imagem nao sera salva.")
    if not any(detection["normalized"] in CHILD_CLASSES for detection in detections):
        raise RuntimeError("Nenhuma box child encontrada nas deteccoes do melhor frame.")

    LAST_ALERT_IMAGE_PATH.parent.mkdir(parents=True, exist_ok=True)
    annotated = desenhar_frame_melhor_child(frame, detections, final_decision, timestamp)
    saved = cv2.imwrite(str(LAST_ALERT_IMAGE_PATH), annotated)
    if not saved or not LAST_ALERT_IMAGE_PATH.exists() or LAST_ALERT_IMAGE_PATH.stat().st_size <= 0:
        raise RuntimeError(f"Falha ao salvar imagem valida em {LAST_ALERT_IMAGE_PATH}")
    return str(LAST_ALERT_IMAGE_PATH)


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


def executar_observacao(model, queue, duration, sample_interval, show_window=True, debug=False, yolo_conf=DIAGNOSTIC_YOLO_CONF, save_best_frame=False):
    """Executa observacao por tempo limitado, amostrando a cada intervalo."""
    samples = []
    csv_file, csv_writer = preparar_csv()
    debug_log_file = preparar_debug_log()
    best_child_frame = None
    best_child_detections = []
    best_child_conf = 0.0
    best_child_timestamp = 0.0

    if save_best_frame and LAST_ALERT_IMAGE_PATH.exists():
        log_diagnostico(debug_log_file, f"Imagem anterior preservada ate uma nova ser salva: {LAST_ALERT_IMAGE_PATH}")

    warmup_packet = queue.get()
    warmup_frame = warmup_packet.getCvFrame()
    executar_inferencia(model, warmup_frame, conf_threshold=yolo_conf)
    log_diagnostico(debug_log_file, "Warm-up do modelo concluido. Iniciando cronometro de observacao.")
    log_diagnostico(debug_log_file, f"Nomes de classes do modelo: {model.names}")
    log_diagnostico(
        debug_log_file,
        "Parametros de observacao | "
        f"yolo_conf={yolo_conf:.2f} | "
        f"MIN_CHILD_CONF={MIN_CHILD_CONF:.2f} | "
        f"MIN_ADULT_CONF={MIN_ADULT_CONF:.2f} | "
        f"CHILD_MIN_PRESENCE={CHILD_MIN_PRESENCE:.2f} | "
        f"ADULT_MAX_PRESENCE={ADULT_MAX_PRESENCE:.2f}"
    )

    start_time = time.perf_counter()
    next_sample_time = start_time
    sample_index = 0
    last_frame = None
    partial_status = "OBSERVANDO"
    metrics = calcular_metricas(samples)

    log_diagnostico(debug_log_file, "Modo de observacao iniciado. Pressione 'q' para encerrar antes do tempo.")

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
                result = executar_inferencia(model, frame, conf_threshold=yolo_conf)
                detections = extrair_deteccoes(result)
                next_sample_number = sample_index + 1
                imprimir_diagnostico_amostra(next_sample_number, detections, debug=debug, log_file=debug_log_file)
                child_detected, child_conf_max, adult_detected, adult_conf_max = analisar_resultado(
                    result,
                    detections=detections,
                    debug=debug,
                    log_file=debug_log_file,
                )
                raw_child_conf = obter_melhor_child_conf(result, detections=detections)
                best_child_detection = obter_melhor_child_detection(detections)

                # Mantem apenas uma copia do melhor frame para evitar crescimento de memoria.
                if best_child_detection is not None and best_child_detection["confidence"] > best_child_conf:
                    previous_conf = best_child_conf
                    new_conf = best_child_detection["confidence"]
                    best_child_conf = raw_child_conf
                    best_child_frame = frame.copy()
                    best_child_detections = list(detections)
                    best_child_timestamp = time.time()
                    log_diagnostico(debug_log_file, "Novo melhor frame encontrado.")
                    log_diagnostico(debug_log_file, f"Confianca anterior: {previous_conf:.4f}")
                    log_diagnostico(debug_log_file, f"Nova confianca: {new_conf:.4f}")

                sample_index += 1
                sample = {
                    "timestamp": time.time(),
                    "sample_index": sample_index,
                    "child_detected": child_detected,
                    "child_conf_max": child_conf_max,
                    "adult_detected": adult_detected,
                    "adult_conf_max": adult_conf_max,
                    "boxes_count": len(detections),
                    "detections": formatar_deteccoes_resumo(detections),
                    "raw_child_conf": raw_child_conf,
                }
                samples.append(sample)

                metrics = calcular_metricas(samples)
                partial_status = decidir_status_parcial(metrics)
                salvar_amostra(csv_writer, sample, metrics, partial_status)
                csv_file.flush()

                log_diagnostico(
                    debug_log_file,
                    f"Amostra {sample_index} | "
                    f"boxes={len(detections)} | "
                    f"detections=[{formatar_deteccoes_resumo(detections)}] | "
                    f"raw_child_conf={raw_child_conf:.3f} | "
                    f"child={child_detected} conf={child_conf_max:.3f} | "
                    f"adult={adult_detected} conf={adult_conf_max:.3f} | "
                    f"child_presence={metrics['child_presence_ratio']:.2%} | "
                    f"adult_presence={metrics['adult_presence_ratio']:.2%} | "
                    f"status={partial_status}"
                )

                # Agenda a proxima coleta a partir do fim da amostra atual.
                # Isso evita rajadas quando a primeira inferencia demora.
                next_sample_time = time.perf_counter() + sample_interval

            if show_window:
                display = desenhar_tela(frame.copy(), remaining, metrics, partial_status)
                cv2.imshow("OAK-D Observation Mode", display)

            if show_window and cv2.waitKey(1) & 0xFF == ord("q"):
                break
    finally:
        csv_file.close()
        if show_window:
            cv2.destroyAllWindows()

    metrics = calcular_metricas(samples)
    final_decision = decidir_final(metrics)
    alert_image_path = ""

    if save_best_frame and best_child_frame is not None:
        try:
            alert_image_path = salvar_frame_alerta(
                best_child_frame,
                best_child_detections,
                final_decision,
                best_child_timestamp,
            )
            log_diagnostico(debug_log_file, "Melhor frame salvo:")
            log_diagnostico(debug_log_file, alert_image_path)
            log_diagnostico(debug_log_file, "Confianca:")
            log_diagnostico(debug_log_file, f"{best_child_conf:.4f}")
        except Exception as error:
            # A decisao nao deve ser perdida se houver falha de escrita da imagem.
            log_diagnostico(debug_log_file, f"Falha ao salvar frame do alerta: {error}")
    elif save_best_frame:
        log_diagnostico(debug_log_file, "Nenhuma deteccao child encontrada; melhor frame nao foi salvo.")

    if save_best_frame and not alert_image_path and LAST_ALERT_IMAGE_PATH.exists():
        alert_image_path = str(LAST_ALERT_IMAGE_PATH)
        log_diagnostico(debug_log_file, "Usando imagem anterior preservada:")
        log_diagnostico(debug_log_file, alert_image_path)

    salvar_resumo(metrics, final_decision, best_child_conf, alert_image_path, best_child_timestamp)

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
    print(f"best_child_conf: {best_child_conf:.4f}")
    print(f"alert_image_path: {alert_image_path}")
    print(f"CSV salvo em: {REPORT_PATH}")
    print(f"Resumo salvo em: {SUMMARY_PATH}")
    print(f"Diagnostico salvo em: {DEBUG_LOG_PATH}")
    debug_log_file.close()

    return last_frame, metrics, final_decision


def main():
    parser = argparse.ArgumentParser(description="Modo de observacao OAK-D + YOLO11 OpenVINO.")
    parser.add_argument("--model", default="../models/yolo11_openvino_model", help="Pasta do modelo OpenVINO.")
    parser.add_argument("--duration", type=float, default=OBSERVATION_SECONDS, help="Duracao da observacao em segundos.")
    parser.add_argument("--sample-interval", type=float, default=SAMPLE_INTERVAL, help="Intervalo entre amostras em segundos.")
    parser.add_argument("--no-display", action="store_true", help="Executa sem abrir janela OpenCV, ideal para Flask/headless.")
    parser.add_argument("--debug-detections", action="store_true", help="Imprime todas as deteccoes antes dos filtros.")
    parser.add_argument("--yolo-conf", type=float, default=DIAGNOSTIC_YOLO_CONF, help=f"Limiar bruto do YOLO antes dos filtros. Padrao diagnostico: {DIAGNOSTIC_YOLO_CONF}. Padrao do teste YOLO: {CONF_THRESHOLD}.")
    parser.add_argument("--save-best-frame", action="store_true", help="Salva o melhor frame child anotado em results/images/last_child_alert.jpg.")
    args = parser.parse_args()

    if args.duration <= 0:
        raise ValueError("--duration deve ser maior que zero.")
    if args.sample_interval <= 0:
        raise ValueError("--sample-interval deve ser maior que zero.")
    if not 0.0 <= args.yolo_conf <= 1.0:
        raise ValueError("--yolo-conf deve ficar entre 0.0 e 1.0.")

    if not listar_dispositivos():
        return

    model = carregar_modelo(args.model)
    api_version, device, pipeline, queue_info = inicializar_camera()

    if api_version == "v3":
        with pipeline:
            pipeline.start()
            executar_observacao(
                model,
                queue_info,
                args.duration,
                args.sample_interval,
                show_window=not args.no_display,
                debug=args.debug_detections,
                yolo_conf=args.yolo_conf,
                save_best_frame=args.save_best_frame,
            )
    else:
        with dai.Device(pipeline) as device:
            queue = device.getOutputQueue(name=queue_info, maxSize=4, blocking=False)
            executar_observacao(
                model,
                queue,
                args.duration,
                args.sample_interval,
                show_window=not args.no_display,
                debug=args.debug_detections,
                yolo_conf=args.yolo_conf,
                save_best_frame=args.save_best_frame,
            )


if __name__ == "__main__":
    main()
