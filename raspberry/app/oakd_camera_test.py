"""
Exemplo de uso:

python oakd_camera_test.py

Abre a camera RGB da OAK-D em 640x480 a 30 FPS e mostra o FPS real.
Pressione q para encerrar.
"""

import argparse
import time

import cv2
import depthai as dai


PREVIEW_WIDTH = 640
PREVIEW_HEIGHT = 480
CAMERA_FPS = 30


def inicializar_camera():
    """Cria a camera RGB da OAK-D em DepthAI v3 ou v2."""
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


def calcular_fps_camera(last_time, frame_counter):
    """Calcula FPS da camera a cada segundo."""
    now = time.perf_counter()
    elapsed = now - last_time
    if elapsed >= 1.0:
        fps = frame_counter / elapsed
        return fps, now, 0
    return None, last_time, frame_counter


def main():
    parser = argparse.ArgumentParser(description="Teste da camera RGB da OAK-D.")
    parser.add_argument("--duration", type=float, default=0.0, help="Duracao do teste em segundos. Use 0 para rodar ate apertar q.")
    parser.add_argument("--no-display", action="store_true", help="Executa sem abrir janela OpenCV.")
    args = parser.parse_args()

    if args.duration < 0:
        raise ValueError("--duration nao pode ser negativo.")

    api_version, device, pipeline, queue_info = inicializar_camera()

    def loop(queue):
        camera_fps = 0.0
        frame_counter = 0
        last_time = time.perf_counter()
        start_time = time.perf_counter()

        if args.duration > 0:
            print(f"Camera OAK-D iniciada por {args.duration:.0f}s.")
        elif args.no_display:
            print("Camera OAK-D iniciada. Pressione Ctrl+C para encerrar.")
        else:
            print("Camera OAK-D iniciada. Pressione 'q' para encerrar.")

        while True:
            packet = queue.get()
            frame = packet.getCvFrame()

            frame_counter += 1
            fps_update, last_time, frame_counter = calcular_fps_camera(last_time, frame_counter)
            if fps_update is not None:
                camera_fps = fps_update
                print(f"Camera FPS: {camera_fps:.2f}")

            if not args.no_display:
                cv2.putText(frame, f"Camera FPS: {camera_fps:.2f}", (20, 35), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
                cv2.imshow("OAK-D RGB", frame)

            if args.duration > 0 and time.perf_counter() - start_time >= args.duration:
                break
            if not args.no_display and cv2.waitKey(1) & 0xFF == ord("q"):
                break

    if api_version == "v3":
        with pipeline:
            pipeline.start()
            loop(queue_info)
    else:
        with dai.Device(pipeline) as device:
            queue = device.getOutputQueue(name=queue_info, maxSize=4, blocking=False)
            loop(queue)

    if not args.no_display:
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
