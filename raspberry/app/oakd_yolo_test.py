"""
Exemplo de uso:

python oakd_yolo_test.py
python oakd_yolo_test.py --model models/best_yolov8n_openvino_model

Captura frames RGB da OAK-D, roda YOLOv8n OpenVINO em tempo real e salva
benchmark em results/reports/oakd_benchmark.csv.
"""

import argparse
import csv
import time
from pathlib import Path

import cv2
import depthai as dai
from ultralytics import YOLO


MODEL_PATH = Path("../models/best_yolov8n_openvino_model")
BENCHMARK_PATH = Path("../results/reports/oakd_benchmark.csv")

PREVIEW_WIDTH = 640
PREVIEW_HEIGHT = 480
CAMERA_FPS = 30
IMG_SIZE = 320
CONF_THRESHOLD = 0.50


def listar_dispositivos():
    """Lista dispositivos DepthAI disponiveis antes de abrir a camera."""
    dispositivos = dai.Device.getAllAvailableDevices()
    if not dispositivos:
        print("OAK-D nao encontrada.")
        return []

    print("OAK-D encontrada.")
    for device_info in dispositivos:
        mx_id = device_info.getDeviceId() if hasattr(device_info, "getDeviceId") else getattr(device_info, "deviceId", "desconhecido")
        estado = getattr(device_info, "state", getattr(device_info, "status", "desconhecido"))
        print(f"Dispositivo: {device_info.name} | MX ID: {mx_id} | Estado: {estado}")

    return dispositivos


def inicializar_camera():
    """Configura a camera RGB em 640x480 a 30 FPS para DepthAI v3 ou v2."""
    if not hasattr(dai.node, "XLinkOut"):
        device = dai.Device()
        pipeline = dai.Pipeline(device)
        cam = pipeline.create(dai.node.Camera).build()
        output = cam.requestOutput(
            (PREVIEW_WIDTH, PREVIEW_HEIGHT),
            type=dai.ImgFrame.Type.BGR888p,
            fps=CAMERA_FPS,
        )
        queue = output.createOutputQueue(maxSize=4, blocking=False)
        return "v3", device, pipeline, queue

    pipeline = dai.Pipeline()
    cam = pipeline.create(dai.node.ColorCamera)
    cam.setPreviewSize(PREVIEW_WIDTH, PREVIEW_HEIGHT)
    cam.setFps(CAMERA_FPS)
    cam.setInterleaved(False)
    cam.setColorOrder(dai.ColorCameraProperties.ColorOrder.BGR)

    xout = pipeline.create(dai.node.XLinkOut)
    xout.setStreamName("rgb")
    cam.preview.link(xout.input)

    return "v2", None, pipeline, "rgb"


def carregar_modelo(model_path):
    """Carrega o modelo OpenVINO exportado pelo Ultralytics."""
    model_path = Path(model_path)
    if not model_path.exists():
        raise FileNotFoundError(f"Modelo nao encontrado: {model_path}")

    return YOLO(str(model_path), task="detect")


def executar_inferencia(model, frame, conf_threshold=CONF_THRESHOLD):
    """Executa YOLOv8n OpenVINO com parametros fixos de baixa latencia."""
    return model(
        frame,
        imgsz=IMG_SIZE,
        conf=conf_threshold,
        verbose=False,
    )[0]


def calcular_fps_camera(last_time, frame_counter):
    """Calcula FPS real da camera a cada segundo."""
    now = time.perf_counter()
    elapsed = now - last_time
    if elapsed >= 1.0:
        fps = frame_counter / elapsed
        return fps, now, 0
    return None, last_time, frame_counter


def calcular_fps_inferencia(result):
    """Calcula FPS usando apenas o tempo de inferencia do Ultralytics."""
    infer_ms = float(result.speed.get("inference", 0.0))
    return 1000 / infer_ms if infer_ms > 0 else 0.0


def desenhar_resultados(frame, result, camera_fps, inference_fps):
    """Desenha caixas, classes, confianca e FPS na imagem."""
    annotated = result.plot()

    cv2.putText(annotated, f"Camera FPS: {camera_fps:.2f}", (20, 35), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
    cv2.putText(annotated, f"Inference FPS: {inference_fps:.2f}", (20, 70), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)

    return annotated


def preparar_benchmark():
    """Cria o arquivo CSV de benchmark e retorna o writer."""
    BENCHMARK_PATH.parent.mkdir(parents=True, exist_ok=True)
    file = BENCHMARK_PATH.open("w", newline="", encoding="utf-8")
    fieldnames = [
        "timestamp",
        "camera_fps",
        "inference_fps",
        "preprocess_ms",
        "inference_ms",
        "postprocess_ms",
    ]
    writer = csv.DictWriter(file, fieldnames=fieldnames)
    writer.writeheader()
    return file, writer


def salvar_benchmark(writer, camera_fps, inference_fps, result):
    """Salva uma linha de benchmark por frame."""
    writer.writerow(
        {
            "timestamp": time.time(),
            "camera_fps": round(camera_fps, 4),
            "inference_fps": round(inference_fps, 4),
            "preprocess_ms": round(float(result.speed.get("preprocess", 0.0)), 4),
            "inference_ms": round(float(result.speed.get("inference", 0.0)), 4),
            "postprocess_ms": round(float(result.speed.get("postprocess", 0.0)), 4),
        }
    )


def main():
    parser = argparse.ArgumentParser(description="Teste OAK-D + YOLOv8n OpenVINO.")
    parser.add_argument("--model", default=str(MODEL_PATH), help="Pasta do modelo OpenVINO.")
    args = parser.parse_args()

    if not listar_dispositivos():
        return

    model = carregar_modelo(args.model)
    api_version, device, pipeline, queue_info = inicializar_camera()
    benchmark_file, benchmark_writer = preparar_benchmark()

    def loop(queue):
        camera_fps = 0.0
        frame_counter = 0
        last_camera_time = time.perf_counter()

        print("OAK-D + YOLO iniciados. Pressione 'q' para encerrar.")

        while True:
            packet = queue.get()
            frame = packet.getCvFrame()

            frame_counter += 1
            fps_update, last_camera_time, frame_counter = calcular_fps_camera(last_camera_time, frame_counter)
            if fps_update is not None:
                camera_fps = fps_update

            result = executar_inferencia(model, frame)
            inference_fps = calcular_fps_inferencia(result)

            salvar_benchmark(benchmark_writer, camera_fps, inference_fps, result)

            print(
                f"Tempo preprocess: {result.speed.get('preprocess', 0.0):.2f} ms | "
                f"Tempo inference: {result.speed.get('inference', 0.0):.2f} ms | "
                f"Tempo postprocess: {result.speed.get('postprocess', 0.0):.2f} ms | "
                f"FPS inferencia: {inference_fps:.2f} | "
                f"FPS camera: {camera_fps:.2f}"
            )

            annotated = desenhar_resultados(frame, result, camera_fps, inference_fps)
            cv2.imshow("OAK-D YOLOv8n OpenVINO", annotated)

            if cv2.waitKey(1) & 0xFF == ord("q"):
                break

    try:
        if api_version == "v3":
            with pipeline:
                pipeline.start()
                loop(queue_info)
        else:
            with dai.Device(pipeline) as device:
                queue = device.getOutputQueue(name=queue_info, maxSize=4, blocking=False)
                loop(queue)
    finally:
        benchmark_file.close()
        cv2.destroyAllWindows()
        print(f"Benchmark salvo em: {BENCHMARK_PATH}")


if __name__ == "__main__":
    main()
