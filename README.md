# CalcuCalo Vision Backend

A Python-based AI backend for a Vietnamese food nutrition application. This repository handles the core computer vision pipeline and nutrition estimation logic, exposing a FastAPI server for mobile clients (e.g., React Native).

## Core Features

1. **Object Detection**: Uses YOLO to detect 68 classes of Vietnamese food (VietFood67 dataset).
2. **Segmentation**: Extracts polygon masks (via SAM 2 or GrabCut fallback) for mobile clients to render interactive food overlays.
3. **Smart Portion Estimation**: Employs a **Fill-Ratio** algorithm combined with **Container Scaling**. It removes the need for physical depth sensors or manual cm measurements by calculating the percentage of food filling the detected plate/bowl boundaries.
4. **Nutrition Engine**: Breaks down complex dishes into base ingredients using a recipe catalog, scaling Calories, Protein, Fat, and Carbs dynamically based on the estimated volume.

## Quick Start (API Server)

Requirements: Python 3.10-3.12.

1. Setup virtual environment and install dependencies:
   ```powershell
   py -3.11 -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install -e ".[all]"
   ```

2. Start the API server:
   ```powershell
   # Ensure you have your trained weights in models/best.pt or models/best.onnx
   uvicorn calcucalo.api:app --host 0.0.0.0 --port 8000
   ```

## API Usage

The main endpoint is `POST /api/v1/food/analyze`. It accepts an image and a user-selected container type.

```powershell
curl.exe -X POST "http://localhost:8000/api/v1/food/analyze" \
  -F "image=@path\to\meal.jpg" \
  -F "container_type=to_lon" \
  -F "response_format=nutrition"
```

**Supported `container_type` values:**
- `chen` (Small bowl)
- `to` (Standard bowl - Default for soup)
- `to_lon` (Large bowl)
- `dia_nho` (Small plate)
- `dia` (Standard plate - Default for dry food)
- `dia_lon` (Large plate)
- `hop` (Takeout box - requires `container_length_cm` and `container_width_cm`)

## Dataset Preparation & Training

1. **Download Dataset**:
   ```powershell
   kaggle datasets download -d thomasnguyen6868/vietfood68 --unzip -p data\raw\vietfood67
   ```

2. **Prepare Configs**:
   ```powershell
   calcucalo prepare-dataset data\raw\vietfood67 --output configs\vietfood67.yaml
   ```

3. **Train YOLO**:
   ```powershell
   python scripts/train_detector.py --data configs\vietfood67.yaml --model yolo11n.pt --epochs 100 --batch -1 --device 0 --export-onnx
   ```
