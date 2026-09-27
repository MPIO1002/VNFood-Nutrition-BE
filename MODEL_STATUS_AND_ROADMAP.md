# Báo cáo trạng thái model CalcuCalo Vision

Phiên bản mới nhất: **0.5.0**

Ngày cập nhật báo cáo gần nhất: **27/09/2026**

## Danh sách phiên bản

| Phiên bản | Ngày báo cáo | Trạng thái | Nội dung nổi bật |
|---|---|---|---|
| [0.5.0](#phiên-bản-050--hiện-tại) | 27/09/2026 | Hiện tại | Component pass độ phân giải cao, multi-instance, audit nhãn, fine-tune an toàn và test tự động |
| [0.4.0](#phiên-bản-040--lưu-trữ) | 26/09/2026 | Lưu trữ | Web UI, kiểm tra ảnh, readiness theo tiến độ train và cấu hình thí nghiệm detector |
| [0.3.0](#phiên-bản-030--lưu-trữ) | 26/09/2026 | Lưu trữ + hậu kiểm | Calculation trace và checkpoint VietFood67 15/20 epoch |
| [0.2.0](#phiên-bản-020--lưu-trữ) | 21/09/2026 | Lưu trữ | Baseline end-to-end đầu tiên cho detection, portion và nutrition |

Quy ước cập nhật: phiên bản mới luôn được thêm lên trên; nội dung phiên bản cũ được giữ lại bên dưới để có thể đối chiếu thay đổi theo thời gian.

---

## Phiên bản 0.5.0 — hiện tại

Ngày cập nhật: 27/09/2026<br>
Phiên bản mã nguồn: 0.5.0

### 1. Đầu vào của v5

Run `vietfood67_yolo11n_v4_no_mosaic_10e` đã hoàn thành đủ 10/10 epoch trên
100% dữ liệu, đúng 68 lớp và không dùng mosaic. Validation cuối đạt precision
**0,7573**, recall **0,6820**, mAP50 **0,7504** và mAP50–95 **0,6023**.

So với v3 tại cùng epoch 10, v4 tăng lần lượt khoảng 1,10; 3,40; 2,86 và
3,40 điểm phần trăm. Tuy nhiên v4 epoch 10 vẫn chưa vượt v3 epoch 15. Các đường
validation loss vẫn giảm và mAP vẫn tăng ở epoch cuối, nên có cơ sở chạy thêm một
phase fine-tune ngắn 5 epoch.

### 2. Thay đổi trong code v5

- Thêm `calcucalo audit-dataset` để thống kê class balance, box nhỏ, nhãn trùng,
  label không có ảnh, box lỗi và các cặp nhãn khác lớp lồng nhau.
- Mở rộng `scripts/train_detector.py` với `--fine-tune`. Chế độ này tải trọng số
  đã học nhưng tạo optimizer/schedule mới với learning rate bảo thủ.
- Chặn nhầm lẫn giữa `--resume` và checkpoint đã train xong. Checkpoint v4 đã
  hoàn tất 10/10 và bị Ultralytics strip optimizer, vì vậy không thể exact-resume.
- Kiểm tra số lớp của checkpoint và YAML trước khi fine-tune/resume để tránh lệch
  class map.
- Thêm cấu hình learning rate, warmup, multi-scale và `exist_ok` trên CLI.
- Thêm `--test-after-training`: tự đánh giá `best.pt` trên `split=test`, lưu plot
  và `test_metrics.json`.
- Giữ `--export-onnx` để export model được chọn sau phase mới.
- Bật component pass mặc định cho CLI/API; có thể tắt rõ ràng bằng `--no-component-pass`.
- Tách cấu hình component detector khỏi dish detector: mặc định `confidence=0.15`, `imgsz=960`
  và crop có vùng đệm 8% để tăng khả năng giữ thành phần nhỏ ở sát mép món.
- Thêm NMS theo ingredient thay vì chỉ giữ một detection tốt nhất. Nhiều miếng rời của cùng
  nguyên liệu được giữ và `visual_instance_count` được xuất trong full JSON.
- Khi ảnh có tỷ lệ mét và có nhiều instance cùng nguyên liệu, cộng khối lượng hình học của các
  instance trước khi tính calories/macro. Khi không có tỷ lệ mét, vẫn dùng gram theo recipe prior
  và chỉ coi detection là bằng chứng thị giác, không giả vờ đã đo được gram.
- API model info trả cả cấu hình component detector để dễ kiểm tra model đang chạy thực tế.

### 3. Cách hiểu “epoch 10 đến 15”

V4 là run đã hoàn tất và checkpoint không còn optimizer state. Vì vậy v5 không
thể tiếp tục chính xác optimizer ở epoch 11 bằng `resume=True`. Cách an toàn là:

1. Dùng `v4/weights/best.pt` làm trọng số khởi tạo.
2. Chạy `--fine-tune --epochs 5` với learning rate thấp hơn.
3. Run v5 sẽ hiển thị epoch 1–5, nhưng về ý nghĩa đây là 5 epoch tối ưu bổ sung
   sau 10 epoch của v4.

Không được dùng lại tên run v4 hoặc ghi đè folder v4. Cần giữ cả hai để so sánh.

### 4. Mục tiêu của v5

| Điểm yếu v4 | Xử lý trong v5 |
|---|---|
| Không biết nhãn nào trùng/box nhỏ | Sinh báo cáo audit JSON trước train |
| Dễ dùng nhầm `resume` với run hoàn tất | Tách chế độ `--fine-tune`, chặn checkpoint hoàn tất |
| Có thể lệch class map khi đổi checkpoint | So sánh số lớp model với YAML trước train |
| Vật thể nhỏ còn bị bỏ sót | Audit theo class; hỗ trợ thử `imgsz=768` ở experiment riêng |
| Component pass chỉ giữ một box mỗi nguyên liệu | NMS theo ingredient và giữ nhiều instance rời |
| Thành phần nhỏ dùng cùng ngưỡng/độ phân giải với món chính | Component detector riêng, mặc định conf 0,15 và imgsz 960 |
| Crop món sát bounding box dễ cắt topping ở mép | Thêm padding cấu hình được, mặc định 8% |
| Dễ hiểu nhầm detection thành gram đã đo | Chỉ cộng gram instance khi có metric scale; nếu không vẫn ghi recipe prior |
| Chỉ nhìn validation rồi kết luận | Tự chạy test split và lưu metric machine-readable |
| Khó tái lập phase fine-tune | Ghi rõ lr0, lrf, warmup, seed và tên run mới |

V5 chưa tự sửa nhãn sai trong dataset. Audit chỉ chỉ ra vị trí/vấn đề tổng hợp;
việc sửa label cần được thực hiện trong một version dataset mới để không âm thầm
thay đổi dữ liệu gốc.

### 5. Tiêu chí chọn model sau v5

- So sánh v3, v4 và v5 trên cùng test split, cùng `imgsz=640`.
- Ưu tiên mAP50–95 và recall, đồng thời xem AP từng lớp và ảnh dự đoán.
- Nếu v5 không tăng hoặc bắt đầu tăng validation loss, giữ `best.pt` của v4/v3.
- Sau khi chọn detector, vẫn phải đánh giá ảnh điện thoại, sai số gram và calories;
  detector candidate không đồng nghĩa toàn pipeline production-ready.

Chi tiết cell Kaggle nằm trong chương **22** của `KAGGLE_TRAINING_GUIDE.md`.

---

## Phiên bản 0.4.0 — lưu trữ

Ngày cập nhật: 26/09/2026<br>
Phiên bản mã nguồn: 0.4.0

### Thay đổi so với 0.3.0

- Thêm giao diện web responsive chạy trực tiếp cùng FastAPI, không cần Node.js/React.
- Cho phép upload hoặc kéo thả ảnh, chọn cách hiệu chuẩn, phủ bounding box, xem calories/macro/component và JSON đầy đủ.
- Cho phép sửa gram từng component trên giao diện rồi gọi lại pipeline để tính dinh dưỡng.
- Tự tìm `best.onnx`/`best.pt` trong `models/`, root hoặc cấu trúc run `*/weights/`; vẫn ưu tiên biến `CALCUCALO_MODEL`.
- Thêm endpoint `GET /api/v1/model/info` để đọc class, tham số train, metric và đánh giá readiness của checkpoint.
- Thêm kiểm tra độ phân giải, độ nét và độ sáng của ảnh; kết quả nằm trong `image_quality` và cảnh báo người dùng chụp lại khi cần.
- Cho phép cấu hình `confidence`, IoU và kích thước inference bằng biến môi trường.
- Đọc số epoch đã hoàn thành trực tiếp từ checkpoint và trả trạng thái `training_incomplete` nếu run bị dừng trước kế hoạch.
- Bổ sung tham số `--fraction`, `--mosaic`, `--close-mosaic` và `--save-period` cho `scripts/train_detector.py` để cấu hình và tái lập thí nghiệm detector v4.

### 1. Model hiện tại làm được gì

Pipeline vẫn đi theo hướng **detection → segmentation/mask → hiệu chuẩn → ước lượng khẩu phần → recipe/component → calories và macro**. Phiên bản này bổ sung lớp kiểm soát đầu vào và giao diện để kiểm thử toàn bộ pipeline, thay vì thay đổi kiến trúc detector.

Checkpoint mới tại `vietfood67_yolo11n_v1/weights/best.pt` được nhận diện đúng 68 lớp và đã dùng 100% tập train. Tuy nhiên metadata cho thấy run mới hoàn thành **15/20 epoch**, nên v4 đánh dấu nó là `training_incomplete`, chưa coi là detector candidate. Ở epoch 15, validation đạt precision **0,7757**, recall **0,7106**, mAP50 **0,7782** và mAP50–95 **0,6254**; đây là kết quả phát triển tốt nhưng chưa phải đánh giá cuối cùng.

### 2. Các cải thiện đã áp dụng sau rà soát

| Điểm yếu phát hiện | Cập nhật trong 0.4.0 | Tác dụng |
|---|---|---|
| Người dùng khó thử model | Web UI tích hợp FastAPI | Upload ảnh và xem kết quả ngay trên trình duyệt |
| Ảnh mờ/tối/góc xấu dễ tạo kết quả thiếu tin cậy | `quality.py` chấm quality và trả hướng dẫn | Chặn kỳ vọng sai, hướng người dùng chụp lại |
| Không rõ API đang nạp checkpoint nào | Auto-discovery + model info | Hiện file, backend, số lớp, metric và cấu hình train |
| Checkpoint dừng giữa chừng vẫn có mAP cao và bị gọi là candidate | Đọc `completed_epochs`/`planned_epochs` từ `.pt` | Trả `training_incomplete` cho checkpoint v3 đang ở 15/20 epoch |
| Detector tốt có thể bị hiểu là toàn hệ thống đã production | Tách `detector_candidate` khỏi `production_ready` | Chỉ detector được đánh dấu candidate; pipeline vẫn cần đánh giá gram/calories |
| Ngưỡng inference bị cố định | Biến môi trường confidence/IoU/image size | Dễ hiệu chỉnh trên validation set mà không sửa code |
| Script train khó kiểm soát augmentation | Thêm tùy chọn mosaic/fraction/checkpoint period | Cho phép chạy thí nghiệm v4 có cấu hình rõ ràng và tái lập được |

### 3. Việc cần làm tiếp theo

1. Resume chính checkpoint v3 từ epoch 15 đến hết epoch 20; không đổi augmentation hoặc learning-rate giữa một lần resume.
2. Chạy đánh giá riêng trên `split=test` với `plots=True`, lưu confusion matrix, PR/F1 curve, AP từng lớp và ảnh dự đoán. Folder hiện tại chưa có các artifact này nên chưa thể kết luận lớp nào tốt hoặc yếu.
3. Chỉ sau bước 2 mới chép checkpoint được chọn vào `models/best.pt` hoặc `models/best.onnx`; trước đó nên cấu hình rõ `CALCUCALO_MODEL` để tránh nạp nhầm model cũ.
4. Chạy một thí nghiệm v4 độc lập với `mosaic=0.0`. Nhiều ảnh nguồn đã là collage 2×2; thêm YOLO mosaic tạo “collage của collage”, làm vật thể nhỏ và lệch phân phối so với ảnh điện thoại. So sánh v4 với v3 trên cùng test set, seed và 20 epoch trước khi quyết định.
5. Chưa bỏ lớp 27 `Con nguoi` trực tiếp khỏi YAML hiện tại vì sẽ làm lệch toàn bộ class ID phía sau. Nếu tạo model chỉ có thực phẩm, phải sinh dataset/YAML 67 lớp đã remap và cập nhật class map đồng bộ.
6. Chọn confidence theo precision–recall trên validation/test, sau đó kiểm tra thêm bằng ảnh điện thoại thật, ảnh một món không ghép và góc chụp xấu.
7. Thu thập ảnh có cân gram, marker và component mask để chạy `evaluate_pipeline.py`; mAP detector không đo độ chính xác khối lượng hoặc calories.
8. Chỉ đặt `production_ready=true` sau khi detector, portion và nutrition đều đạt tiêu chí trên tập đánh giá độc lập.

### 4. Cấu hình thí nghiệm detector v4 đề xuất

Ưu tiên hoàn tất và đánh giá v3 trước. Sau đó chạy v4 thành một run mới từ cùng pretrained checkpoint để phép so sánh có ý nghĩa:

```powershell
python scripts/train_detector.py `
  --data configs/vietfood67.yaml `
  --model yolo11n.pt `
  --epochs 20 `
  --image-size 640 `
  --batch 32 `
  --device 0,1 `
  --workers 4 `
  --patience 20 `
  --mosaic 0.0 `
  --close-mosaic 0 `
  --save-period 1 `
  --name vietfood67_yolo11n_v4_no_mosaic
```

Không nên đồng thời đổi sang YOLO11s, tăng epoch và đổi augmentation trong cùng lần thử đầu tiên, vì khi đó không xác định được thay đổi nào tạo ra cải thiện. Nếu v4 không mosaic tốt hơn v3 trên test và ảnh thật, bước kế tiếp mới so sánh YOLO11s.

### 5. Cách chạy giao diện

```powershell
pip install -e ".[all]"
$env:CALCUCALO_MODEL = "vietfood67_yolo11n_v1/weights/best.pt"
uvicorn calcucalo.api:app --host 127.0.0.1 --port 8000
```

Mở `http://127.0.0.1:8000`. Metadata model nằm ở `http://127.0.0.1:8000/api/v1/model/info`.

---

## Phiên bản 0.3.0 — lưu trữ

Ngày cập nhật: 21/09/2026  
Phiên bản mã nguồn: 0.3.0

### Thay đổi so với 0.2.0

- Thêm calculation trace cho calibration, portion và phép tính dinh dưỡng từng component.
- Cho phép người dùng override gram của component và tính lại calories/macro.
- Thêm JSON Schema cho nutrition response và evaluation manifest.
- Thêm công cụ kiểm tra catalog và đánh giá end-to-end bằng precision/recall/F1, MAE và MAPE.
- Giữ nguyên JSON contract gọn dành cho mobile.

### 1. Kết luận ngắn

Hệ thống hiện là một **baseline chạy được từ đầu đến cuối**, gồm nhận diện món, tạo mask, ước lượng khẩu phần, phân rã món phức hợp theo công thức và xuất JSON dinh dưỡng. Hệ thống phù hợp để làm MVP, thu thập dữ liệu và kiểm thử API.

Hệ thống **chưa phải model dinh dưỡng đã được kiểm định**. VietFood67 chỉ cung cấp bounding box, không cung cấp mask thành phần, độ sâu, khối lượng thật hay công thức của từng đĩa. Vì vậy không được hiểu các thành phần ẩn dưới nước dùng hoặc nước sốt là đã được model nhìn thấy. Code phân biệt rõ:

- `visual_match`: có detection thành phần nằm trong vùng món tổng.
- `visual_metric_estimate`: thành phần được phát hiện và ảnh có tỷ lệ mét để ước lượng khối lượng.
- `catalog_prior`: thành phần suy ra từ công thức chuẩn, chưa được nhìn thấy trực tiếp.

### 1.1. Hậu kiểm checkpoint detector được train cho v3

Ngày hậu kiểm: 26/09/2026<br>
Nguồn artifact: `vietfood67_yolo11n_v1/`

#### Cấu hình đã xác minh

| Thuộc tính | Giá trị |
|---|---:|
| Kiến trúc | YOLO11n detect |
| Số lớp | 68 |
| Dữ liệu sử dụng | 100% (`fraction=1.0`) |
| Kích thước ảnh | 640 |
| Batch | 32 |
| GPU | `0,1` |
| Kế hoạch | 20 epoch |
| Đã hoàn thành | **15 epoch** |
| Augmentation | `mosaic=1.0`, `close_mosaic=10` |
| Seed/deterministic | `42` / `true` |

Checkpoint `best.pt`, `last.pt` và `epoch14.pt` có cùng SHA-256 và cùng metric, cho thấy epoch 15 là epoch tốt nhất hiện có. Optimizer vẫn còn trong checkpoint nên có thể resume tiếp đến epoch 20.

#### Kết quả validation

| Chỉ số | Epoch 1 | Epoch 7 | Epoch 15 | Thay đổi epoch 1 → 15 |
|---|---:|---:|---:|---:|
| Precision | 0,4613 | 0,7284 | **0,7757** | +0,3144 |
| Recall | 0,3751 | 0,6193 | **0,7106** | +0,3355 |
| mAP50 | 0,3637 | 0,6961 | **0,7782** | +0,4145 |
| mAP50–95 | 0,2609 | 0,5446 | **0,6254** | +0,3645 |
| Train box loss | 0,8635 | 0,7257 | **0,6337** | −0,2298 |
| Validation box loss | 0,9982 | 0,8096 | **0,7447** | −0,2535 |

Tổng thời gian của hai session train được ghi trong `results.csv` khoảng **7 giờ 05 phút**, trung bình khoảng **28,4 phút/epoch**. Các metric vẫn tăng và train/validation loss vẫn giảm ở epoch 15, nên chưa có bằng chứng model đã hội tụ hoặc overfit. Chênh lệch precision–recall còn khoảng 6,5 điểm phần trăm; model vẫn bỏ sót nhiều hơn mức nó dự đoán sai.

#### Điểm tốt

- Detector đã học đủ 68 class ID trên toàn bộ tập train, không còn là smoke test 1%.
- mAP50–95 tăng liên tục từ 0,2609 lên 0,6254; chưa xuất hiện suy giảm validation ở các epoch cuối đã lưu.
- Sau khi mosaic được đóng ở giai đoạn cuối, metric tiếp tục cải thiện; đây là tín hiệu đáng để kiểm chứng bằng thí nghiệm v4 không mosaic, nhưng chưa đủ để khẳng định quan hệ nhân quả.
- Checkpoint có đầy đủ optimizer state để tiếp tục train, không phải chạy lại từ đầu.

#### Điểm chưa đủ và rủi ro

- Run mới dừng ở 15/20 epoch. Không gọi đây là kết quả cuối hoặc detector candidate cho đến khi hoàn tất và đánh giá lại.
- Folder không có `results.png`, confusion matrix, PR/F1 curve, `val_batch*_pred.jpg` hoặc báo cáo AP từng lớp. Vì vậy mAP tổng chưa cho biết món nào đang yếu.
- `labels.jpg` cho thấy mất cân bằng lớp đáng kể; class 27 `Con nguoi` là lớp lớn nhất và không phải thực phẩm. Pipeline đã loại class này khỏi kết quả dinh dưỡng, nhưng detector vẫn phải dùng năng lực để học nó.
- Phân bố tâm bbox tạo bốn cụm rõ ở bốn góc. Kiểm tra ảnh batch xác nhận nhiều ảnh nguồn vốn đã là collage 2×2; dùng thêm `mosaic=1.0` có thể làm vật thể quá nhỏ và khác ảnh chụp một món thực tế.
- Đây chỉ là metric detection trên validation của VietFood67. Nó không đánh giá mask thành phần, chiều sâu, gram, calories hoặc khả năng tổng quát trên ảnh điện thoại ngoài dataset.

#### Kết luận cho v3

Checkpoint hiện tại là **development checkpoint tốt nhưng chưa hoàn tất**. Nó đủ để thử inference và tiếp tục train, nhưng chưa đủ bằng chứng để phát hành. Quyết định giữ model cần dựa trên epoch 20, test split độc lập, AP từng lớp và một bộ ảnh điện thoại thật.

### 2. Những gì model đã có

| Khối | Trạng thái | Cách hoạt động |
|---|---|---|
| Tiền xử lý ảnh | Đã có | Đọc JPG/PNG/WebP, sửa EXIF orientation, chuẩn hóa RGB |
| Nhận diện món | Đã có | YOLO `.pt` qua Ultralytics hoặc `.onnx` qua ONNX Runtime |
| Checkpoint detector v3 | Đang train | YOLO11n, đúng 68 lớp, 100% dữ liệu, hiện hoàn thành 15/20 epoch |
| Model chạy thử cũ | Lưu trữ | Checkpoint YOLOv10m công khai, 58 lớp của bản dữ liệu cũ |
| Cấu hình VietFood67 | Đã có | Đủ 68 class ID, gồm 67 món và lớp người |
| Train model mới | Đã có code | Validator dataset, train YOLO11, resume, export ONNX |
| Bóc tách món | Đã có | Mask từ YOLO-seg; nếu là detection model thì dùng SAM 2 hoặc GrabCut |
| Polygon cho mobile | Đã có | Chuyển binary mask thành polygon JSON gọn |
| Ước lượng khối lượng | Đã có baseline | Diện tích mask × độ dày × khối lượng riêng khi có tỷ lệ mét |
| Ảnh không có vật chuẩn | Đã có fallback | Dùng khẩu phần cơ sở và trả khoảng bất định thấp |
| Món dạng nước | Đã xử lý an toàn | Không biến diện tích mặt nước thành thể tích giả; dùng prior |
| Phân rã món phức hợp | Đã có | Recipe catalog cho đủ 67 lớp món ăn |
| Component second pass | Đã có | Crop món phức hợp rồi detect lại; hỗ trợ checkpoint component riêng |
| Ghép detection con | Đã có | Detection `Com`, `Thit nuong`, `Cha/Trung` nằm trong `Com tam` được ghép thành component |
| Tính macro | Đã có | Tính calories, protein, fat, carb theo gram của từng component |
| JSON mobile | Đã có | Contract gọn `food_id/name/base_portion_g/components` |
| JSON nghiên cứu | Đã có | Thêm bbox, mask, confidence, estimated totals, basis và warnings |
| Calculation trace | Đã có | Trả công thức, đầu vào, giá trị trung gian, giới hạn, sai số và output cho calibration/portion/macro |
| User correction | Đã có | Override gram từng component và tính lại tổng macro |
| API | Đã có | FastAPI `POST /api/v1/food/analyze` |
| Contract validation | Đã có | JSON Schema cho nutrition response và evaluation manifest |
| Catalog QA | Đã có | Kiểm tra coverage, duplicate ID, calories/macro và tổng gram |
| End-to-end evaluation | Đã có | Precision/recall/F1 và MAE/MAPE cho weight/calories/macros |
| Test tự động | Đã có | Công thức portion, catalog, coverage 67 lớp, component grouping và schema |

### 3. Kiến trúc hiện tại

```text
Ảnh RGB
  └─ YOLO detect/segment
      ├─ nhãn món tổng: Com tam
      ├─ crop món tổng và chạy component pass ở độ phân giải cao hơn
      ├─ nhãn con nếu model thấy: Com, Thit nuong, Cha, Trung
      └─ bounding boxes / masks
          └─ SAM 2 hoặc GrabCut nếu chưa có mask
              └─ hiệu chuẩn cm/pixel bằng đĩa hoặc client camera
                  └─ ước lượng khối lượng + khoảng sai số
                      └─ recipe catalog
                          ├─ ghép component có bằng chứng thị giác
                          ├─ bổ sung component bị che bằng catalog prior
                          └─ tính calories và macro
                              └─ JSON full hoặc nutrition
```

Các file quan trọng:

- `src/calcucalo/detector.py`: YOLO ONNX/Ultralytics.
- `src/calcucalo/segmenter.py`: SAM 2, GrabCut và bbox fallback.
- `src/calcucalo/calibration.py`: tỷ lệ ảnh từ đường kính đĩa.
- `src/calcucalo/portion.py`: khối lượng và uncertainty.
- `src/calcucalo/nutrition.py`: recipe decomposition và macro.
- `configs/food_catalog.json`: ingredient/recipe knowledge base.
- `src/calcucalo/analyzer.py`: ghép toàn bộ pipeline.
- `src/calcucalo/api.py`: API cho mobile/backend.

### 4. JSON hiện hỗ trợ

#### Contract gọn cho mobile

```json
{
  "food_id": "VN_COM_TAM",
  "name": "Cơm tấm sườn bì chả",
  "base_portion_g": 380,
  "components": [
    {
      "name": "Cơm tấm",
      "default_g": 200,
      "cal_per_100g": 130,
      "protein": 2.7,
      "fat": 0.3,
      "carb": 28.2
    },
    {
      "name": "Sườn nướng",
      "default_g": 100,
      "cal_per_100g": 240,
      "protein": 20.0,
      "fat": 17.0,
      "carb": 1.0
    },
    {
      "name": "Chả trứng",
      "default_g": 50,
      "cal_per_100g": 160,
      "protein": 11.0,
      "fat": 11.0,
      "carb": 4.0
    }
  ]
}
```

CLI:

```powershell
calcucalo analyze image.jpg --model model.onnx --json-format nutrition
```

Thêm `--component-pass` để bật lượt detect thứ hai trong crop món; dùng `--component-model` khi đã có checkpoint component chuyên biệt.

API:

```text
POST /api/v1/food/analyze
image=@image.jpg
response_format=nutrition
```

#### JSON full cho debug và active learning

`response_format=full` còn chứa:

- `bbox_xyxy`, `mask_polygons`, detection confidence.
- `weight_g`, khoảng khối lượng, phương pháp và giả định.
- `estimated_components`, `estimated_totals`.
- `analysis_basis`, `visual_components_matched`, `data_quality`.
- `component_of` để tránh tính một thành phần hai lần.
- `user_override` khi gram đến từ thanh chỉnh của người dùng; giá trị này ưu tiên hơn model và catalog.
- warnings khi ảnh thiếu tỷ lệ hoặc catalog thiếu dữ liệu.

### 5. Mức chính xác hiện tại

Đã có số liệu validation cho detector v3 ở epoch 15: precision **0,7757**, recall **0,7106**, mAP50 **0,7782** và mAP50–95 **0,6254**. Đây là metric detection trên VietFood67, không phải “độ chính xác calories” của toàn pipeline.

Vẫn chưa có đủ bằng chứng để công bố một con số accuracy end-to-end vì:

1. Run detector chưa hoàn thành 20 epoch và chưa có báo cáo riêng trên test split.
2. Chưa có AP từng lớp, confusion matrix và bộ ảnh điện thoại ngoài VietFood67 để đo domain shift.
3. Chưa có test set chứa khối lượng cân thật và component mask.
4. Giá trị trong `food_catalog.json` hiện là **seed estimate cho phát triển phần mềm**. Chúng chưa được chuyên gia dinh dưỡng duyệt và không nên dùng cho quyết định y tế.

Các unit test chứng minh contract và thuật toán chạy đúng theo thiết kế; chúng không chứng minh model nhận diện đúng ngoài đời.

### 6. Những điểm cần cải thiện và cách cải thiện

#### P0 — Hoàn tất và kiểm định checkpoint VietFood67 68 lớp

Tiến độ: đã thay smoke test bằng checkpoint YOLO11n học trên 100% dữ liệu, nhưng mới đạt 15/20 epoch.

1. Resume `last.pt` đến hết epoch 20 và giữ nguyên cấu hình của run.
2. Kiểm tra trùng ảnh giữa train/val/test bằng perceptual hash; ảnh gần trùng làm mAP bị ảo.
3. Báo cáo AP theo từng lớp, confusion matrix và lỗi theo góc chụp/quán ăn, không chỉ báo cáo mAP chung.
4. Export ONNX và so sánh output `.pt`/`.onnx` trên cùng bộ golden images.
5. Sau baseline YOLO11n, so sánh lần lượt no-mosaic rồi YOLO11s; không đổi cả hai biến trong cùng thí nghiệm.

Lệnh resume trên Kaggle:

```python
from ultralytics import YOLO

model = YOLO("/kaggle/working/runs/detect/vietfood67_yolo11n_v1/weights/last.pt")
model.train(resume=True)
```

#### P1 — Tạo dataset component-level

VietFood67 không đủ để biết phần nào của cơm tấm là cơm, sườn, bì hay chả. Cần bổ sung dataset riêng:

- Mỗi ảnh có `dish_label` và instance mask cho từng component nhìn thấy.
- Thành phần bị che có cờ `occluded=true`; không ép annotator vẽ phần không thấy.
- Nhãn ghi phương pháp nấu: luộc, nướng, chiên, xào; ghi da/mỡ/sốt riêng.
- Mỗi ảnh có recipe variant, quán/nguồn, camera, góc chụp và ánh sáng.
- Khởi đầu bằng 15 món phổ biến, khoảng 300–500 ảnh/món; ưu tiên cơm tấm, phở, bún bò, bún chả, bánh mì và bún đậu.

Có thể dùng SAM 2 tạo pseudo-mask từ box/điểm rồi cho người gán nhãn sửa lại. Không dùng pseudo-mask chưa kiểm tra làm ground truth cuối cùng.

#### P2 — Thu ground truth khối lượng

Mỗi sample cần:

- Khối lượng từng component trước khi ăn bằng cân bếp.
- Ảnh top-down và ảnh nghiêng 45°.
- Marker ArUco/thẻ chuẩn hoặc kích thước đĩa/bát thật.
- Đường kính và chiều cao bát cho món nước.
- Khối lượng còn lại sau ăn nếu ứng dụng cần tính lượng thực sự đã ăn.

Sau đó train regressor theo component với feature: mask area metric, perimeter, depth statistics, class embedding, camera angle, vessel geometry và cooking method. So sánh với baseline area × thickness × density; chỉ giữ model phức tạp nếu giảm MAE trên test set độc lập.

#### P3 — Segmentation chuyên biệt

Kiến trúc đề xuất:

1. Dish detector tìm món tổng.
2. Crop vùng món và chạy component segmentation model.
3. Dùng SAM 2 làm annotator/pseudo-label, không làm nguồn class name.
4. Train YOLO11-seg hoặc Mask2Former trên mask đã được người kiểm tra.
5. Với món lẫn mạnh như cơm chiên, dùng semantic segmentation theo nhóm nguyên liệu thay vì ép instance cho từng hạt/thành phần nhỏ.

#### P4 — Depth và thể tích đúng metric

Monocular depth chỉ cho depth tương đối nếu không có hiệu chuẩn. Để chuyển sang centimet:

- Phương án tốt cho mobile: ARCore/ARKit depth hoặc LiDAR nếu thiết bị hỗ trợ.
- Phương án phổ thông: hai ảnh có hướng dẫn góc chụp + marker kích thước biết trước.
- Phương án rẻ nhất: top-down + đường kính đĩa + prior độ dày đã fit từ dữ liệu cân thật.
- Món nước phải dùng hình học bát và mực nước; không dùng diện tích mặt thoáng đơn lẻ.

#### P5 — Chuẩn hóa nutrition knowledge base

`configs/food_catalog.json` hiện là seed. Quy trình production nên là:

1. Import nguyên liệu cơ sở từ **Bảng thành phần thực phẩm Việt Nam** của Viện Dinh dưỡng.
2. Lưu ID nguồn, phiên bản, edible portion và đơn vị cho từng ingredient.
3. Recipe phải có raw weight, cooked weight và hệ số yield/retention sau nấu.
4. Tách dầu hấp thụ, nước sốt, nước dùng và topping thành component riêng.
5. Mỗi thay đổi recipe tạo version; meal log cũ giữ version đã dùng lúc tính.
6. Chuyên gia dinh dưỡng review trước khi đổi `data_quality` thành `validated`.

Nguồn chính thức tham khảo: [Bảng thành phần thực phẩm Việt Nam – Viện Dinh dưỡng](https://chuyentrang.viendinhduong.vn/viewfilenew/vi/thu-vien-sach-chuyen-nganh/189/1.html).

#### P6 — Calibration confidence và active learning

- Calibrate confidence bằng temperature scaling/isotonic regression trên validation set.
- Khi confidence thấp hoặc top-2 gần nhau, yêu cầu người dùng chọn món.
- Cho phép sửa component và gram ngay trên mask.
- Lưu ảnh, prediction, correction, model version và catalog version vào hàng chờ review.
- Sampling ưu tiên lỗi confidence cao nhưng người dùng sửa, lớp hiếm và môi trường mới.

### 7. Bộ chỉ số bắt buộc trước production

| Bài toán | Chỉ số |
|---|---|
| Dish detection | mAP50-95, precision, recall và AP từng lớp |
| Component detection | Precision/recall/F1 từng component |
| Segmentation | Mask mAP50-95 và IoU/Dice |
| Khối lượng | MAE gram, median absolute error, MAPE theo món |
| Calories | MAE kcal và phần trăm bữa nằm trong ±10%, ±20% |
| Macro | MAE protein/fat/carb theo bữa |
| Confidence | ECE, reliability diagram, coverage-error curve |
| Runtime | p50/p95 latency, RAM/VRAM, model size trên thiết bị mục tiêu |

Test set phải tách theo **quán/người chuẩn bị và thời điểm**, không chỉ random theo ảnh. Nếu cùng một đĩa hoặc chuỗi ảnh gần nhau xuất hiện ở cả train và test, kết quả sẽ quá lạc quan.

Công cụ đã có sẵn:

```powershell
python scripts\validate_catalog.py --output outputs\catalog_validation.json
python scripts\evaluate_pipeline.py data\eval\manifest.jsonl `
  --model runs\detect\vietfood67_yolo11s\weights\best.pt `
  --component-pass `
  --output outputs\evaluation.json
```

Schema của từng dòng ground truth nằm tại `schemas/evaluation_sample.schema.json`.

### 8. Thứ tự triển khai khuyến nghị

1. Train và đánh giá detector VietFood67 đủ 68 lớp.
2. Chọn 6 món MVP, thu ảnh có cân thật và component mask.
3. Thẩm định ingredient database và recipe với chuyên gia dinh dưỡng.
4. Train component segmentation cho 6 món.
5. Fit mass regressor và đo calorie MAE end-to-end.
6. Chạy pilot, thu correction, active learning.
7. Mở rộng dần sang 15 rồi 30 món; không mở đủ 67 món trước khi có ground truth chất lượng.

### 9. Giấy phép và quyền riêng tư

- VietFood67 ghi giấy phép CC BY-NC-SA 4.0 và hạn chế sử dụng thương mại; cần xác minh với tác giả trước khi thương mại hóa.
- Metadata checkpoint ONNX tham khảo ghi AGPL-3.0.
- Ảnh bữa ăn có thể chứa khuôn mặt, vị trí hoặc dữ liệu sức khỏe. Cần xóa EXIF, làm mờ người và có cơ chế consent/retention rõ ràng trước khi lưu để active learning.

Tham khảo: [VietFood67 trên Kaggle](https://www.kaggle.com/datasets/thomasnguyen6868/vietfood68), [FoodDetector của tác giả dataset](https://github.com/nvhnam/FoodDetector), [Ultralytics SAM 2](https://docs.ultralytics.com/models/sam-2/), [Ultralytics YOLO11](https://docs.ultralytics.com/models/yolo11/).

---

## Phiên bản 0.2.0 — lưu trữ

Ngày cập nhật: 21/09/2026

Phiên bản mã nguồn: 0.2.0

> Nội dung dưới đây được giữ nguyên từ báo cáo v0.2.0 trong commit `6523d2d` (`v1`). Chỉ cấp heading được điều chỉnh để nằm đúng trong cấu trúc lịch sử phiên bản.

### 1. Kết luận ngắn

Hệ thống hiện là một **baseline chạy được từ đầu đến cuối**, gồm nhận diện món, tạo mask, ước lượng khẩu phần, phân rã món phức hợp theo công thức và xuất JSON dinh dưỡng. Hệ thống phù hợp để làm MVP, thu thập dữ liệu và kiểm thử API.

Hệ thống **chưa phải model dinh dưỡng đã được kiểm định**. VietFood67 chỉ cung cấp bounding box, không cung cấp mask thành phần, độ sâu, khối lượng thật hay công thức của từng đĩa. Vì vậy không được hiểu các thành phần ẩn dưới nước dùng hoặc nước sốt là đã được model nhìn thấy. Code phân biệt rõ:

- `visual_match`: có detection thành phần nằm trong vùng món tổng.
- `visual_metric_estimate`: thành phần được phát hiện và ảnh có tỷ lệ mét để ước lượng khối lượng.
- `catalog_prior`: thành phần suy ra từ công thức chuẩn, chưa được nhìn thấy trực tiếp.

### 2. Những gì model đã có

| Khối | Trạng thái | Cách hoạt động |
|---|---|---|
| Tiền xử lý ảnh | Đã có | Đọc JPG/PNG/WebP, sửa EXIF orientation, chuẩn hóa RGB |
| Nhận diện món | Đã có | YOLO `.pt` qua Ultralytics hoặc `.onnx` qua ONNX Runtime |
| Model chạy thử | Đã có | Checkpoint YOLOv10m công khai, 58 lớp của bản dữ liệu cũ |
| Cấu hình VietFood67 | Đã có | Đủ 68 class ID, gồm 67 món và lớp người |
| Train model mới | Đã có code | Validator dataset, train YOLO11, resume, export ONNX |
| Bóc tách món | Đã có | Mask từ YOLO-seg; nếu là detection model thì dùng SAM 2 hoặc GrabCut |
| Polygon cho mobile | Đã có | Chuyển binary mask thành polygon JSON gọn |
| Ước lượng khối lượng | Đã có baseline | Diện tích mask × độ dày × khối lượng riêng khi có tỷ lệ mét |
| Ảnh không có vật chuẩn | Đã có fallback | Dùng khẩu phần cơ sở và trả khoảng bất định thấp |
| Món dạng nước | Đã xử lý an toàn | Không biến diện tích mặt nước thành thể tích giả; dùng prior |
| Phân rã món phức hợp | Đã có | Recipe catalog cho đủ 67 lớp món ăn |
| Component second pass | Đã có | Crop món phức hợp rồi detect lại; hỗ trợ checkpoint component riêng |
| Ghép detection con | Đã có | Detection `Com`, `Thit nuong`, `Cha/Trung` nằm trong `Com tam` được ghép thành component |
| Tính macro | Đã có | Tính calories, protein, fat, carb theo gram của từng component |
| JSON mobile | Đã có | Contract gọn `food_id/name/base_portion_g/components` |
| JSON nghiên cứu | Đã có | Thêm bbox, mask, confidence, estimated totals, basis và warnings |
| API | Đã có | FastAPI `POST /api/v1/food/analyze` |
| Test tự động | Đã có | Công thức portion, catalog, coverage 67 lớp, component grouping và schema |

### 3. Kiến trúc hiện tại

```text
Ảnh RGB
  └─ YOLO detect/segment
      ├─ nhãn món tổng: Com tam
      ├─ crop món tổng và chạy component pass ở độ phân giải cao hơn
      ├─ nhãn con nếu model thấy: Com, Thit nuong, Cha, Trung
      └─ bounding boxes / masks
          └─ SAM 2 hoặc GrabCut nếu chưa có mask
              └─ hiệu chuẩn cm/pixel bằng đĩa hoặc client camera
                  └─ ước lượng khối lượng + khoảng sai số
                      └─ recipe catalog
                          ├─ ghép component có bằng chứng thị giác
                          ├─ bổ sung component bị che bằng catalog prior
                          └─ tính calories và macro
                              └─ JSON full hoặc nutrition
```

Các file quan trọng:

- `src/calcucalo/detector.py`: YOLO ONNX/Ultralytics.
- `src/calcucalo/segmenter.py`: SAM 2, GrabCut và bbox fallback.
- `src/calcucalo/calibration.py`: tỷ lệ ảnh từ đường kính đĩa.
- `src/calcucalo/portion.py`: khối lượng và uncertainty.
- `src/calcucalo/nutrition.py`: recipe decomposition và macro.
- `configs/food_catalog.json`: ingredient/recipe knowledge base.
- `src/calcucalo/analyzer.py`: ghép toàn bộ pipeline.
- `src/calcucalo/api.py`: API cho mobile/backend.

### 4. JSON hiện hỗ trợ

#### Contract gọn cho mobile

```json
{
  "food_id": "VN_COM_TAM",
  "name": "Cơm tấm sườn bì chả",
  "base_portion_g": 380,
  "components": [
    {
      "name": "Cơm tấm",
      "default_g": 200,
      "cal_per_100g": 130,
      "protein": 2.7,
      "fat": 0.3,
      "carb": 28.2
    },
    {
      "name": "Sườn nướng",
      "default_g": 100,
      "cal_per_100g": 240,
      "protein": 20.0,
      "fat": 17.0,
      "carb": 1.0
    },
    {
      "name": "Chả trứng",
      "default_g": 50,
      "cal_per_100g": 160,
      "protein": 11.0,
      "fat": 11.0,
      "carb": 4.0
    }
  ]
}
```

CLI:

```powershell
calcucalo analyze image.jpg --model model.onnx --json-format nutrition
```

Thêm `--component-pass` để bật lượt detect thứ hai trong crop món; dùng `--component-model` khi đã có checkpoint component chuyên biệt.

API:

```text
POST /api/v1/food/analyze
image=@image.jpg
response_format=nutrition
```

#### JSON full cho debug và active learning

`response_format=full` còn chứa:

- `bbox_xyxy`, `mask_polygons`, detection confidence.
- `weight_g`, khoảng khối lượng, phương pháp và giả định.
- `estimated_components`, `estimated_totals`.
- `analysis_basis`, `visual_components_matched`, `data_quality`.
- `component_of` để tránh tính một thành phần hai lần.
- warnings khi ảnh thiếu tỷ lệ hoặc catalog thiếu dữ liệu.

### 5. Mức chính xác hiện tại

Chưa có đủ bằng chứng để công bố một con số accuracy end-to-end cho mã nguồn này:

1. Checkpoint ONNX công khai đang dùng để smoke test chỉ có 58 lớp, không phải checkpoint 68 lớp mới được train bởi dự án này.
2. Chưa tải và train toàn bộ VietFood67 trong workspace hiện tại.
3. Chưa có test set chứa khối lượng cân thật và component mask.
4. Giá trị trong `food_catalog.json` hiện là **seed estimate cho phát triển phần mềm**. Chúng chưa được chuyên gia dinh dưỡng duyệt và không nên dùng cho quyết định y tế.

Các unit test chứng minh contract và thuật toán chạy đúng theo thiết kế; chúng không chứng minh model nhận diện đúng ngoài đời.

### 6. Những điểm cần cải thiện và cách cải thiện

#### P0 — Train checkpoint VietFood67 đủ 68 lớp

Mục tiêu: thay checkpoint demo 58 lớp.

1. Tải VietFood67 và chạy validator để tìm ảnh thiếu nhãn, class ID sai và tọa độ ngoài `[0,1]`.
2. Kiểm tra trùng ảnh giữa train/val/test bằng perceptual hash; ảnh gần trùng làm mAP bị ảo.
3. Train lần lượt YOLO11n và YOLO11s; chỉ dùng YOLO11m khi GPU và latency cho phép.
4. Báo cáo AP theo từng lớp, confusion matrix và lỗi theo góc chụp/quán ăn, không chỉ báo cáo mAP chung.
5. Export ONNX và so sánh output `.pt`/`.onnx` trên cùng bộ golden images.

Lệnh khởi đầu:

```powershell
calcucalo prepare-dataset data\raw\vietfood67
python scripts\train_detector.py --data configs\vietfood67.yaml --model yolo11s.pt --epochs 150 --device 0 --export-onnx
```

#### P1 — Tạo dataset component-level

VietFood67 không đủ để biết phần nào của cơm tấm là cơm, sườn, bì hay chả. Cần bổ sung dataset riêng:

- Mỗi ảnh có `dish_label` và instance mask cho từng component nhìn thấy.
- Thành phần bị che có cờ `occluded=true`; không ép annotator vẽ phần không thấy.
- Nhãn ghi phương pháp nấu: luộc, nướng, chiên, xào; ghi da/mỡ/sốt riêng.
- Mỗi ảnh có recipe variant, quán/nguồn, camera, góc chụp và ánh sáng.
- Khởi đầu bằng 15 món phổ biến, khoảng 300–500 ảnh/món; ưu tiên cơm tấm, phở, bún bò, bún chả, bánh mì và bún đậu.

Có thể dùng SAM 2 tạo pseudo-mask từ box/điểm rồi cho người gán nhãn sửa lại. Không dùng pseudo-mask chưa kiểm tra làm ground truth cuối cùng.

#### P2 — Thu ground truth khối lượng

Mỗi sample cần:

- Khối lượng từng component trước khi ăn bằng cân bếp.
- Ảnh top-down và ảnh nghiêng 45°.
- Marker ArUco/thẻ chuẩn hoặc kích thước đĩa/bát thật.
- Đường kính và chiều cao bát cho món nước.
- Khối lượng còn lại sau ăn nếu ứng dụng cần tính lượng thực sự đã ăn.

Sau đó train regressor theo component với feature: mask area metric, perimeter, depth statistics, class embedding, camera angle, vessel geometry và cooking method. So sánh với baseline area × thickness × density; chỉ giữ model phức tạp nếu giảm MAE trên test set độc lập.

#### P3 — Segmentation chuyên biệt

Kiến trúc đề xuất:

1. Dish detector tìm món tổng.
2. Crop vùng món và chạy component segmentation model.
3. Dùng SAM 2 làm annotator/pseudo-label, không làm nguồn class name.
4. Train YOLO11-seg hoặc Mask2Former trên mask đã được người kiểm tra.
5. Với món lẫn mạnh như cơm chiên, dùng semantic segmentation theo nhóm nguyên liệu thay vì ép instance cho từng hạt/thành phần nhỏ.

#### P4 — Depth và thể tích đúng metric

Monocular depth chỉ cho depth tương đối nếu không có hiệu chuẩn. Để chuyển sang centimet:

- Phương án tốt cho mobile: ARCore/ARKit depth hoặc LiDAR nếu thiết bị hỗ trợ.
- Phương án phổ thông: hai ảnh có hướng dẫn góc chụp + marker kích thước biết trước.
- Phương án rẻ nhất: top-down + đường kính đĩa + prior độ dày đã fit từ dữ liệu cân thật.
- Món nước phải dùng hình học bát và mực nước; không dùng diện tích mặt thoáng đơn lẻ.

#### P5 — Chuẩn hóa nutrition knowledge base

`configs/food_catalog.json` hiện là seed. Quy trình production nên là:

1. Import nguyên liệu cơ sở từ **Bảng thành phần thực phẩm Việt Nam** của Viện Dinh dưỡng.
2. Lưu ID nguồn, phiên bản, edible portion và đơn vị cho từng ingredient.
3. Recipe phải có raw weight, cooked weight và hệ số yield/retention sau nấu.
4. Tách dầu hấp thụ, nước sốt, nước dùng và topping thành component riêng.
5. Mỗi thay đổi recipe tạo version; meal log cũ giữ version đã dùng lúc tính.
6. Chuyên gia dinh dưỡng review trước khi đổi `data_quality` thành `validated`.

Nguồn chính thức tham khảo: [Bảng thành phần thực phẩm Việt Nam – Viện Dinh dưỡng](https://chuyentrang.viendinhduong.vn/viewfilenew/vi/thu-vien-sach-chuyen-nganh/189/1.html).

#### P6 — Calibration confidence và active learning

- Calibrate confidence bằng temperature scaling/isotonic regression trên validation set.
- Khi confidence thấp hoặc top-2 gần nhau, yêu cầu người dùng chọn món.
- Cho phép sửa component và gram ngay trên mask.
- Lưu ảnh, prediction, correction, model version và catalog version vào hàng chờ review.
- Sampling ưu tiên lỗi confidence cao nhưng người dùng sửa, lớp hiếm và môi trường mới.

### 7. Bộ chỉ số bắt buộc trước production

| Bài toán | Chỉ số |
|---|---|
| Dish detection | mAP50-95, precision, recall và AP từng lớp |
| Component detection | Precision/recall/F1 từng component |
| Segmentation | Mask mAP50-95 và IoU/Dice |
| Khối lượng | MAE gram, median absolute error, MAPE theo món |
| Calories | MAE kcal và phần trăm bữa nằm trong ±10%, ±20% |
| Macro | MAE protein/fat/carb theo bữa |
| Confidence | ECE, reliability diagram, coverage-error curve |
| Runtime | p50/p95 latency, RAM/VRAM, model size trên thiết bị mục tiêu |

Test set phải tách theo **quán/người chuẩn bị và thời điểm**, không chỉ random theo ảnh. Nếu cùng một đĩa hoặc chuỗi ảnh gần nhau xuất hiện ở cả train và test, kết quả sẽ quá lạc quan.

### 8. Thứ tự triển khai khuyến nghị

1. Train và đánh giá detector VietFood67 đủ 68 lớp.
2. Chọn 6 món MVP, thu ảnh có cân thật và component mask.
3. Thẩm định ingredient database và recipe với chuyên gia dinh dưỡng.
4. Train component segmentation cho 6 món.
5. Fit mass regressor và đo calorie MAE end-to-end.
6. Chạy pilot, thu correction, active learning.
7. Mở rộng dần sang 15 rồi 30 món; không mở đủ 67 món trước khi có ground truth chất lượng.

### 9. Giấy phép và quyền riêng tư

- VietFood67 ghi giấy phép CC BY-NC-SA 4.0 và hạn chế sử dụng thương mại; cần xác minh với tác giả trước khi thương mại hóa.
- Metadata checkpoint ONNX tham khảo ghi AGPL-3.0.
- Ảnh bữa ăn có thể chứa khuôn mặt, vị trí hoặc dữ liệu sức khỏe. Cần xóa EXIF, làm mờ người và có cơ chế consent/retention rõ ràng trước khi lưu để active learning.

Tham khảo: [VietFood67 trên Kaggle](https://www.kaggle.com/datasets/thomasnguyen6868/vietfood68), [FoodDetector của tác giả dataset](https://github.com/nvhnam/FoodDetector), [Ultralytics SAM 2](https://docs.ultralytics.com/models/sam-2/), [Ultralytics YOLO11](https://docs.ultralytics.com/models/yolo11/).
