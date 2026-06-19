"""Exporta raspberry/yolo11.pt para OpenVINO em raspberry/models/.

Uso:
    python scripts/convert_yolo11_openvino.py
"""

import argparse
import shutil
from pathlib import Path

from ultralytics import YOLO


RASPBERRY_DIR = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = RASPBERRY_DIR / "yolo11.pt"
DEFAULT_OUTPUT = RASPBERRY_DIR / "models/yolo11_openvino_model"
DEFAULT_IMGSZ = 320


def exportar_openvino(source, output, imgsz):
    """Converte um modelo .pt para uma pasta OpenVINO .xml/.bin."""
    source = Path(source).resolve()
    output = Path(output).resolve()

    if not source.exists():
        raise FileNotFoundError(f"Modelo de origem nao encontrado: {source}")

    model = YOLO(str(source), task="detect")
    exported_path = Path(model.export(format="openvino", imgsz=imgsz)).resolve()

    if output.exists():
        shutil.rmtree(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(exported_path), str(output))

    return output


def main():
    parser = argparse.ArgumentParser(description="Converte yolo11.pt para OpenVINO.")
    parser.add_argument("--source", default=str(DEFAULT_SOURCE), help="Caminho do arquivo .pt.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="Pasta de saida OpenVINO.")
    parser.add_argument("--imgsz", type=int, default=DEFAULT_IMGSZ, help="Tamanho de entrada usado na exportacao.")
    args = parser.parse_args()

    output = exportar_openvino(args.source, args.output, args.imgsz)
    print(f"Modelo OpenVINO salvo em: {output}")


if __name__ == "__main__":
    main()
