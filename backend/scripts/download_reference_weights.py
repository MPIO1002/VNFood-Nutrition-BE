from __future__ import annotations

import argparse
import hashlib
import shutil
from pathlib import Path
from urllib.request import Request, urlopen

REFERENCE_URL = (
    "https://raw.githubusercontent.com/nvhnam/FoodDetector/v2/model/yolov10/"
    "YOLOv10m_new_total_VN_5_SGD.onnx"
)
EXPECTED_BYTES = 30_865_560
EXPECTED_SHA256 = "6e8ee58d4a05ee5a785dc5377727ab0835404a3c9c8d649acc9e37403ef018e9"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Download the authors' public YOLOv10 ONNX demo checkpoint "
            "(58 classes from the earlier VietFood57 model)"
        )
    )
    parser.add_argument("--output", default="models/vietfood57_yolov10m.onnx")
    args = parser.parse_args()
    output = Path(args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".part")

    request = Request(REFERENCE_URL, headers={"User-Agent": "CalcuCalo/0.1"})
    with urlopen(request, timeout=60) as response, temporary.open("wb") as stream:
        shutil.copyfileobj(response, stream)
    if temporary.stat().st_size != EXPECTED_BYTES or sha256(temporary) != EXPECTED_SHA256:
        temporary.unlink(missing_ok=True)
        raise SystemExit("Downloaded weights failed size/SHA-256 verification")
    temporary.replace(output)
    print(output)
    print("This public ONNX file has 58 classes (57 foods + human), not all 68 VietFood67 classes.")
    print("Train with VietFood67 for the full class set. Check dataset/model licenses before commercial use.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
