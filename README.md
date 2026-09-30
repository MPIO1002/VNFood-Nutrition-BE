# CalcuCalo Vision

Baseline Python cho phần phân tích ảnh của ứng dụng dinh dưỡng món Việt:

1. YOLO nhận diện món ăn theo 68 lớp của VietFood67.
2. Mask có sẵn từ YOLO-seg được dùng trực tiếp; với model detection, bounding box được đưa vào SAM 2 hoặc GrabCut để bóc tách vùng món ăn.
3. Mask được đổi thành polygon để mobile app có thể vẽ và cho người dùng hiệu chỉnh.
4. Khối lượng được ước lượng bằng diện tích thật × độ dày × khối lượng riêng khi ảnh có tỷ lệ mét. Nếu ảnh không có vật chuẩn, hệ thống trả về serving prior cùng khoảng bất định rõ ràng.
5. Recipe catalog tách món phức hợp thành nguyên liệu, ghép các detection con nằm trong món tổng và tính calories/protein/fat/carb theo khẩu phần.

Đây là baseline nghiên cứu, không phải thiết bị đo dinh dưỡng hay thiết bị y tế.

## Cấu trúc thư mục dự án

Cây dưới đây mô tả cấu trúc đang dùng của CalcuCalo. Các thư mục dữ liệu, trọng số và kết quả chạy được giữ local, không đưa lên Git theo cấu hình trong `.gitignore`.

```text
CalcuCalo/
├── configs/                              # Cấu hình class, khẩu phần và catalog dinh dưỡng
│   ├── food_catalog.json                 # Món → food_id, thành phần, gram mặc định và macro/100 g
│   ├── portion_priors.yaml               # Độ dày, mật độ, khối lượng và sai số giả định theo món
│   ├── vietfood67_classes.yaml           # Ánh xạ class ID 0..67 của VietFood67
│   └── vietfood67.yaml                   # Data YAML sinh từ dataset để Ultralytics train
│
├── data/                                 # Dữ liệu local, bị Git bỏ qua
│   └── raw/vietfood67/dataset/
│       ├── images/
│       │   ├── train/                    # Ảnh dùng huấn luyện
│       │   ├── valid/                    # Ảnh dùng validation
│       │   └── test/                     # Ảnh đánh giá cuối
│       └── labels/
│           ├── train/                    # Nhãn YOLO tương ứng images/train
│           ├── valid/                    # Nhãn YOLO tương ứng images/valid
│           └── test/                     # Nhãn YOLO tương ứng images/test
│
├── models/                               # Nơi lưu checkpoint .pt/.onnx local
├── outputs/                              # JSON, ảnh overlay và báo cáo đánh giá xuất ra
├── runs/                                 # Log, biểu đồ và weights do Ultralytics sinh khi train
│
├── schemas/                              # JSON Schema cho các contract dữ liệu ổn định
│   ├── nutrition_food.schema.json        # Schema response dinh dưỡng gọn cho mobile
│   └── evaluation_sample.schema.json     # Schema một dòng ground truth evaluation JSONL
│
├── scripts/                              # Các entry point phục vụ dữ liệu, train và đánh giá
│   ├── download_reference_weights.py     # Tải và kiểm tra checksum checkpoint demo
│   ├── evaluate_detector.py              # Đánh giá val/test và export mà không train lại
│   ├── prepare_vietfood67.py             # Wrapper chuẩn bị/kiểm tra dataset VietFood67
│   ├── train_detector.py                 # Fine-tune YOLO, resume và export ONNX
│   ├── validate_catalog.py               # Kiểm tra coverage, ID, gram và macro của catalog
│   └── evaluate_pipeline.py              # Đo F1, MAE, MAPE trên manifest có ground truth
│
├── src/
│   ├── calcucalo/                        # Python package chính
│   │   ├── __init__.py                   # Public exports và phiên bản package
│   │   ├── analyzer.py                   # Điều phối toàn pipeline phân tích một ảnh
│   │   ├── api.py                        # FastAPI: health check và endpoint analyze
│   │   ├── calibration.py                # Tỷ lệ cm/pixel từ đĩa tròn hoặc client cung cấp
│   │   ├── cli.py                        # CLI analyze và prepare-dataset
│   │   ├── dataset.py                    # Tìm layout YOLO, validate nhãn và sinh data YAML
│   │   ├── detector.py                   # Adapter Ultralytics .pt và ONNX Runtime .onnx
│   │   ├── domain.py                     # Dataclass Detection, Calibration, Portion và Result
│   │   ├── evaluation.py                 # Tích lũy confusion matrix và sai số dinh dưỡng
│   │   ├── image_io.py                   # Đọc ảnh, sửa EXIF orientation và chuẩn hóa RGB
│   │   ├── masks.py                      # Chuẩn hóa mask, polygon và kiểm tra chất lượng mask
│   │   ├── nutrition.py                  # Ghép recipe/component và tính calories, macro
│   │   ├── portion.py                    # Ước lượng gram, thể tích và khoảng bất định
│   │   ├── quality.py                    # Chấm độ nét, độ sáng, độ phân giải và gợi ý chụp lại
│   │   ├── segmenter.py                  # SAM 2, GrabCut và bounding-box fallback
│   │   ├── visualize.py                  # Vẽ bbox/mask/nhãn và lưu ảnh overlay
│   │   └── web/                          # Giao diện test được FastAPI phục vụ trực tiếp
│   │       ├── index.html                # Trang upload, hiệu chuẩn và xem kết quả
│   │       └── assets/                   # CSS và JavaScript gọi API/phủ bbox
│   └── calcucalo_vision.egg-info/        # Metadata sinh bởi pip install -e; không sửa tay
│
├── tests/                                # Unit/integration tests
│   ├── test_analyzer.py                  # Pipeline, serialization và calculation trace
│   ├── test_calibration.py               # Công thức hiệu chuẩn từ đường kính đĩa
│   ├── test_dataset.py                   # Layout, label và cấu hình dataset
│   ├── test_detector.py                  # Decode output và hậu xử lý detector
│   ├── test_evaluation.py                # Precision/recall/F1 và MAE/MAPE
│   ├── test_nutrition.py                 # Catalog, component pass, override và macro
│   ├── test_portion.py                   # Geometry, serving prior và món dạng nước
│   ├── test_quality.py                   # Cảnh báo ảnh mờ/tối/sáng và quality score
│   └── test_api.py                       # Static UI, model discovery và readiness checkpoint
│
├── .gitignore                            # Loại dataset, weights, runs, outputs và cache khỏi Git
├── pyproject.toml                        # Metadata package, dependencies, pytest và Ruff
├── requirements.txt                     # Entry cài đặt tối giản cho môi trường hiện tại
├── README.md                             # Hướng dẫn cài đặt, train, API và vận hành
├── MODEL_STATUS_AND_ROADMAP.md           # Trạng thái kỹ thuật, giới hạn và lộ trình model
├── Dự án_ Ứng dụng AI Phân Tích Dinh Dưỡng & Ước Tính Calories Món Ăn Việt Nam (Mô hình tương tự Cal AI).md
│                                           # Đặc tả và dự tính sản phẩm ban đầu
└── yolo11n.pt                            # Pretrained weight Ultralytics đã tải local
```

`yolo11n.pt`, `src/calcucalo_vision.egg-info/`, `.pytest_cache/` và `.ruff_cache/` là artefact sinh tự động. Checkpoint mới nên được lưu trong `models/`; kết quả từng experiment nên nằm trong `runs/`; file cần bàn giao như JSON hoặc overlay nên nằm trong `outputs/`. File `yolo11n.pt` hiện nằm ở root nên chưa khớp pattern ignore `models/*.pt`; cần chuyển nó vào `models/` hoặc tránh stage file này khi commit.

Luồng phụ thuộc chính giữa các module:

```mermaid
flowchart TD
    CLI[cli.py] --> Analyzer[analyzer.py]
    API[api.py] --> Analyzer

    Analyzer --> Detector[detector.py]
    Analyzer --> Segmenter[segmenter.py]
    Analyzer --> Calibration[calibration.py]
    Analyzer --> Portion[portion.py]
    Analyzer --> Nutrition[nutrition.py]

    Segmenter --> Masks[masks.py]
    Portion --> Priors[configs/portion_priors.yaml]
    Nutrition --> Catalog[configs/food_catalog.json]
    Detector --> Classes[configs/vietfood67_classes.yaml]

    Analyzer --> Domain[domain.py]
    Domain --> JSON[Full/compact JSON]
    Domain --> Visualize[visualize.py]
    Visualize --> Overlay[Ảnh overlay]

    Dataset[dataset.py] --> DataYaml[configs/vietfood67.yaml]
    DataYaml --> Train[scripts/train_detector.py]
    Train --> Weights[best.pt / last.pt / best.onnx]
```

## Vì sao không train YOLO-seg trực tiếp?

VietFood67 có khoảng 33.003 ảnh, 67 lớp món ăn và một lớp người, nhưng nhãn công khai là **bounding box**, không phải polygon mask, depth hay khối lượng. Vì vậy:

- YOLO detect có thể train trực tiếp bằng dataset.
- Mask ở bản đầu được tạo bằng SAM 2 từ bounding box (chất lượng tốt hơn, cần tải thêm model) hoặc GrabCut (nhẹ, chạy CPU).
- Khối lượng từ một ảnh RGB không có vật chuẩn không thể là phép đo metric. Pipeline không biến relative monocular depth thành cm giả; nó yêu cầu `cm_per_pixel`, đường kính đĩa đã biết, hoặc trả serving prior để người dùng sửa.

Dataset nặng khoảng 26,4 GB và dùng giấy phép **CC BY-NC-SA 4.0**. Metadata của checkpoint ONNX tham khảo ghi giấy phép **AGPL-3.0**. Cần kiểm tra cả giấy phép dữ liệu lẫn model/framework trước khi làm sản phẩm thương mại.

## Cài đặt

Khuyến nghị Python 3.10–3.12 và môi trường ảo:

```powershell
cd D:\Model\CalcuCalo
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[all]"
```

Nếu chỉ chạy checkpoint ONNX trên CPU và không cần train/SAM, có thể cài bản nhẹ bằng `pip install -e ".[onnx]"`. CLI tự chọn ONNX Runtime cho file `.onnx` và Ultralytics cho file `.pt`.

## Chạy thử với trọng số tham khảo

Repo của tác giả có một checkpoint YOLOv10m ONNX để demo. Metadata bên trong checkpoint này cho thấy nó là bản cũ gồm **58 lớp (57 món + người)**, chưa phải đủ 68 lớp của VietFood67. Có thể dùng để kiểm tra pipeline ngay; để nhận diện đủ lớp vẫn cần train theo phần tiếp theo. Script tải model về local (file model bị `.gitignore`):

```powershell
python scripts/download_reference_weights.py
calcucalo analyze path\to\meal.jpg `
  --model models\vietfood57_yolov10m.onnx `
  --segmenter grabcut `
  --plate-diameter-cm 25 `
  --output-json outputs\result.json `
  --output-image outputs\overlay.jpg
```

Để chỉ lấy JSON dinh dưỡng gọn cho mobile client:

```powershell
calcucalo analyze path\to\com-tam.jpg `
  --model models\vietfood57_yolov10m.onnx `
  --json-format nutrition
```

Component pass được bật mặc định. Hệ thống crop từng món phức hợp có thêm vùng đệm, chạy
detector lần hai ở `imgsz=960`, dùng ngưỡng confidence thấp hơn và NMS theo nguyên liệu để tìm
thành phần nhỏ. Các miếng rời cùng một nguyên liệu được giữ lại thay vì chỉ lấy một detection;
khi có tỷ lệ mét, khối lượng các miếng được cộng trước khi tính dinh dưỡng. Dùng
`--no-component-pass` khi chỉ cần benchmark detector món chính.

Có thể hiệu chỉnh hoặc dùng checkpoint component chuyên biệt:

```powershell
calcucalo analyze meal.jpg `
  --model models\best.pt `
  --component-model models\component_detector.pt `
  --component-confidence 0.15 `
  --component-image-size 960 `
  --component-crop-padding 0.08 `
  --json-format full
```

Nếu không truyền `--component-model`, hệ thống dùng lại trọng số dish detector với một detector
inference cấu hình riêng. Điều này cải thiện khả năng nhìn vật thể nhỏ nhưng không thay thế dữ
liệu gán nhãn component-level. Thành phần không được nhìn thấy vẫn có `basis=catalog_prior`.

Khi người dùng chỉnh gram trên UI, tạo file như sau và truyền bằng `--component-overrides`:

```json
{
  "VN_COM_TAM": {
    "Cơm tấm": 180,
    "Sườn nướng": 120,
    "Chả trứng": 45
  }
}
```

```powershell
calcucalo analyze meal.jpg --model model.onnx `
  --component-overrides corrected-grams.json `
  --json-format full
```

Giá trị người dùng nhập có `basis=user_override`, được ưu tiên hơn geometry/catalog và làm hệ thống tính lại `estimated_totals`. Nên dùng `ingredient_id` từ `estimated_components` làm key ổn định (ví dụ `broken_rice`, `grilled_pork`); tên tiếng Việt cũng được chấp nhận. Contract nutrition gọn vẫn mô tả khẩu phần mặc định nên không thay đổi `default_g`.

Khi chỉ có một món, output tuân theo contract:

```json
{
  "food_id": "VN_COM_TAM",
  "name": "Cơm tấm sườn bì chả",
  "base_portion_g": 380,
  "components": [
    {"name": "Cơm tấm", "default_g": 200, "cal_per_100g": 130, "protein": 2.7, "fat": 0.3, "carb": 28.2},
    {"name": "Sườn nướng", "default_g": 100, "cal_per_100g": 240, "protein": 20.0, "fat": 17.0, "carb": 1.0},
    {"name": "Chả trứng", "default_g": 50, "cal_per_100g": 160, "protein": 11.0, "fat": 11.0, "carb": 4.0}
  ]
}
```

`--json-format full` còn trả về bounding box, polygon, khoảng khối lượng, tổng macro ước lượng, thành phần nào có bằng chứng thị giác và thành phần nào chỉ đến từ công thức. Catalog hiện phủ 67 lớp món ăn tại `configs/food_catalog.json` nhưng các số liệu đang ở mức seed để phát triển, chưa được chuyên gia dinh dưỡng thẩm định.

### Trace chi tiết phép tính

Full JSON giải thích được từng kết quả thay vì chỉ trả một con số cuối:

- `calculation_trace`: phiên bản trace và tuyên bố rõ đây là ước lượng, chưa phải phép đo chiều sâu.
- `calibration.calculation`: cách đổi pixel sang centimet, đầu vào và giới hạn góc chụp.
- `items[].portion.calculation`: công thức diện tích, thể tích, khối lượng thô, giới hạn min/max, sai số và confidence.
- `foods[].estimated_components[].calculation`: phép nhân gram với calories/protein/fat/carb trên 100 g.
- `foods[].total_calculation`: phép cộng dinh dưỡng của các component.

Ví dụ rút gọn khi ảnh có tỷ lệ mét:

```json
{
  "portion": {
    "weight_g": 201.6,
    "method": "mask_area_x_thickness_x_density",
    "calculation": {
      "model": "mask_area_x_assumed_thickness_x_density",
      "is_depth_measured": false,
      "inputs": {
        "mask_area_px": 10000,
        "cm_per_pixel": 0.1,
        "assumed_thickness_cm": 2.8,
        "assumed_density_g_cm3": 0.72
      },
      "intermediate": {
        "area_cm2": 100.0,
        "volume_cm3": 280.0,
        "raw_weight_g": 201.6,
        "weight_was_clamped": false
      },
      "outputs": {
        "estimated_weight_g": 201.6
      }
    }
  }
}
```

`is_depth_measured=false` được trả rõ vì `assumed_thickness_cm` là prior theo class, không phải chiều sâu đo từ ảnh. `--json-format nutrition` vẫn giữ nguyên contract gọn và không mang trace để tránh tăng payload cho mobile.

Contract JSON gọn được khóa tại `schemas/nutrition_food.schema.json`. Kiểm tra coverage, food ID, macro và phân bổ gram trong catalog bằng:

```powershell
python scripts/validate_catalog.py --output outputs/catalog_validation.json
```

Dùng SAM 2 để có mask tốt hơn (lần đầu Ultralytics sẽ tải trọng số):

```powershell
calcucalo analyze path\to\meal.jpg `
  --model models\vietfood57_yolov10m.onnx `
  --segmenter sam `
  --sam-model sam2.1_t.pt `
  --output-json outputs\result.json
```

Nếu app camera đã tự hiệu chuẩn, truyền `--cm-per-pixel 0.042` thay cho đường kính đĩa. Nếu không truyền tỷ lệ, `portion.method` sẽ là `single_image_serving_prior` hoặc `liquid_or_mixed_dish_prior` và confidence thấp hơn.

## Tải và chuẩn bị VietFood67

Cài Kaggle CLI, đăng nhập, sau đó tải dataset:

```powershell
pip install kaggle
kaggle datasets download -d thomasnguyen6868/vietfood68 --unzip -p data\raw\vietfood67
```

Kiểm tra cấu trúc, class ID, tọa độ nhãn và sinh file cấu hình YOLO:

```powershell
calcucalo prepare-dataset data\raw\vietfood67 --output configs\vietfood67.yaml
```

Tool nhận cả hai layout phổ biến:

```text
root/train/images + root/train/labels
root/images/train + root/labels/train
```

`valid` và `validation` được tự động ánh xạ thành `val`.

Audit sâu trước khi train để phát hiện nhãn trùng, box nhỏ, mất cân bằng lớp và
nhãn món/thành phần lồng nhau:

```powershell
calcucalo audit-dataset data\raw\vietfood67 `
  --classes configs\vietfood67_classes.yaml `
  --max-images-per-split 10000 `
  --output reports\vietfood67_audit.json
```

## Train detection model

Baseline cân bằng tốc độ/VRAM dùng YOLO11n; có thể đổi thành `yolo11s.pt` hoặc `yolo11m.pt` nếu GPU đủ mạnh:

```powershell
python scripts/train_detector.py `
  --data configs\vietfood67.yaml `
  --model yolo11n.pt `
  --epochs 100 `
  --batch -1 `
  --device 0 `
  --export-onnx
```

Checkpoint tốt nhất nằm tại `runs/detect/vietfood67_yolo11n/weights/best.pt`. Dataset gốc chỉ huấn luyện **detection**. Muốn có model segmentation thuần, cần tạo và kiểm tra polygon ground truth (có thể lấy SAM 2 làm pseudo-label rồi sửa bằng người) trước khi train `yolo11n-seg.pt`.

Checkpoint của một run đã hoàn tất không nên gọi `resume=True`. Để tối ưu thêm
từ trọng số đã train, dùng một phase mới với `--fine-tune`; `--epochs` khi đó là
số epoch bổ sung:

```powershell
python scripts\train_detector.py `
  --data configs\vietfood67.yaml `
  --model path\to\v4\weights\best.pt `
  --epochs 5 `
  --image-size 640 `
  --batch 32 `
  --device 0 `
  --mosaic 0 `
  --close-mosaic 0 `
  --learning-rate 0.001 `
  --warmup-epochs 1 `
  --name vietfood67_yolo11n_v5_ft_from_v4_5e `
  --fine-tune `
  --test-after-training `
  --export-onnx
```

Quy trình Kaggle đầy đủ cho v5 nằm tại [KAGGLE_TRAINING_GUIDE.md](KAGGLE_TRAINING_GUIDE.md#22-từ-v4-lên-v5-fine-tune-thêm-5-epoch).

## API FastAPI

### Giao diện web để test model

Hướng dẫn riêng theo từng bước: [WEB_UI_GUIDE.md](WEB_UI_GUIDE.md).

Giao diện upload ảnh được phục vụ trực tiếp bởi FastAPI, không cần cài Node.js. API ưu tiên
`CALCUCALO_MODEL`; nếu biến này chưa được đặt, hệ thống tự tìm `models/best.onnx`,
`models/best.pt`, `best.onnx` hoặc `best.pt` theo thứ tự.

```powershell
$env:CALCUCALO_MODEL = "best.pt" # có thể bỏ nếu best.pt/best.onnx nằm ở vị trí tự dò
$env:CALCUCALO_SEGMENTER = "grabcut" # hoặc sam
$env:CALCUCALO_COMPONENT_PASS = "true" # mặc định đã bật
# $env:CALCUCALO_COMPONENT_MODEL = "models\component_detector.pt"
$env:CALCUCALO_COMPONENT_CONFIDENCE = "0.15"
$env:CALCUCALO_COMPONENT_IMAGE_SIZE = "960"
$env:CALCUCALO_COMPONENT_CROP_PADDING = "0.08"
$env:CALCUCALO_COMPONENT_NMS_IOU = "0.50"
$env:CALCUCALO_COMPONENT_MAX_INSTANCES = "12"
uvicorn calcucalo.api:app --host 0.0.0.0 --port 8000
```

Mở `http://localhost:8000`. Giao diện hỗ trợ:

- Upload/drag-drop JPG, PNG, WebP và xem bounding box trên ảnh.
- Nhập đường kính đĩa hoặc `cm_per_pixel` để hiệu chuẩn.
- Xem calories, protein, fat, carb và từng component.
- Sửa gram của component rồi gửi lại để tính tổng dinh dưỡng.
- Xem cảnh báo chất lượng ảnh, trạng thái checkpoint và JSON đầy đủ.

Các cấu hình inference tùy chọn:

```powershell
$env:CALCUCALO_CONFIDENCE = "0.38" # đỉnh F1 validation v5 xấp xỉ 0.384
$env:CALCUCALO_IOU = "0.60"
$env:CALCUCALO_IMAGE_SIZE = "640"
```

Gọi API:

```powershell
curl.exe -X POST "http://localhost:8000/api/v1/food/analyze" `
  -F "image=@path\to\meal.jpg" `
  -F "plate_diameter_cm=25" `
  -F "response_format=nutrition"
```

API nhận cùng dữ liệu hiệu chỉnh qua trường form `component_overrides_json`, ví dụ `{"VN_COM_TAM":{"Cơm tấm":180}}`. Dùng `response_format=full` để nhận gram/tổng macro sau hiệu chỉnh.

Response gồm `bbox_xyxy`, `mask_polygons`, `detection_confidence`, `image_quality`,
`weight_g`, khoảng ước lượng, phương pháp và các giả định. Endpoint health là `GET /health`;
metadata và mức sẵn sàng của checkpoint nằm tại `GET /api/v1/model/info`.

## Hiệu chuẩn khối lượng cho dữ liệu thật

Các giá trị trong `configs/portion_priors.yaml` chỉ là điểm khởi đầu. Để model hữu dụng:

1. Chụp món từ góc gần vuông góc, luôn có đĩa/bát kích thước biết trước hoặc marker ArUco/card chuẩn.
2. Cân từng thành phần bằng cân bếp và lưu `true_weight_g` cùng ảnh/mask.
3. Fit lại `thickness_cm`, `density_g_cm3` hoặc một regressor theo class trên train set; đánh giá MAE/MAPE trên người dùng và quán ăn chưa xuất hiện trong train.
4. Với phở/bún/canh, thu thêm đường kính, chiều cao bát và mức nước hoặc dùng RGB-D/multi-view. Không suy thể tích nước từ diện tích mặt thoáng.
5. Luôn giữ bước hiệu chỉnh của người dùng; lưu correction để active learning.

## Kiểm thử

```powershell
pytest
```

Các test hiện kiểm tra công thức portion, fallback không hiệu chuẩn, lọc lớp người, serialization, validator YOLO dataset, contract cơm tấm, coverage 67 lớp, component second-pass và metric evaluation.

## Đánh giá trên dữ liệu cân thật

Tạo JSONL, mỗi dòng là một ảnh. Đường dẫn ảnh tương đối được tính từ vị trí manifest:

```json
{"image":"images/com-tam-001.jpg","plate_diameter_cm":25,"foods":[{"food_id":"VN_COM_TAM","weight_g":392,"calories_kcal":585,"protein_g":29.5,"fat_g":20.1,"carb_g":70.2}]}
```

Schema nằm tại `schemas/evaluation_sample.schema.json`. Chạy evaluation:

```powershell
python scripts/evaluate_pipeline.py data/eval/manifest.jsonl `
  --model runs/detect/vietfood67_yolo11s/weights/best.pt `
  --component-pass `
  --output outputs/evaluation.json
```

Report gồm precision/recall/F1 theo `food_id`, MAE/median error/MAPE cho gram, calories, protein, fat, carb và thống kê riêng từng món.

Tình trạng kỹ thuật, giới hạn và roadmap chi tiết nằm trong `MODEL_STATUS_AND_ROADMAP.md`.
