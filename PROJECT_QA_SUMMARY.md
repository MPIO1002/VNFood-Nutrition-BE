# Tổng hợp câu hỏi và câu trả lời của dự án CalcuCalo

Ngày tổng hợp: **26/09/2026**

Tài liệu này tóm tắt toàn bộ quá trình trao đổi về dự án CalcuCalo: xây dựng model, chuẩn bị VietFood67, train trên Kaggle, xử lý lỗi, đánh giá checkpoint v3 và kế hoạch v4. Nội dung được viết lại ngắn gọn, không phải bản chép nguyên văn.

> Khi câu trả lời cũ và mới khác nhau, ưu tiên hướng dẫn mới nhất trong tài liệu này. Lệnh Kaggle đầy đủ nằm trong `KAGGLE_TRAINING_GUIDE.md`; trạng thái model và roadmap nằm trong `MODEL_STATUS_AND_ROADMAP.md`.

---

## 1. Mục tiêu ban đầu của dự án

### Câu hỏi

Muốn xây dựng ứng dụng tương tự Cal AI cho món Việt, dùng Python và VietFood67 để:

- Nhận diện món ăn trong ảnh.
- Bóc tách vùng món ăn.
- Ước lượng khối lượng.
- Phân tích thành phần.
- Tính calories và macro.

### Trả lời đã thống nhất

Pipeline được định hướng như sau:

```text
Ảnh RGB
  → YOLO detect/segment món ăn
  → tạo mask bằng model segmentation, SAM hoặc GrabCut
  → hiệu chuẩn kích thước bằng đĩa/marker/cm-per-pixel
  → ước lượng khẩu phần và khoảng bất định
  → ghép recipe/component catalog
  → tính calories, protein, fat, carb
  → trả JSON hoặc API response
```

VietFood67 phù hợp để học **detection món ăn**, nhưng không đủ để học chính xác:

- Chiều sâu thật.
- Gram của từng thành phần.
- Instance mask của cơm, thịt, trứng trong cùng đĩa.
- Calories thực tế của một suất ăn.

Muốn làm các phần đó chính xác cần dataset bổ sung có component mask, cân gram, vật chuẩn và thông tin công thức.

---

## 2. JSON món ăn và phân tích nhiều thành phần

### Câu hỏi

Model có thể trả JSON dạng món ăn tổng cùng danh sách thành phần hay không, ví dụ cơm tấm gồm cơm, sườn và chả trứng?

### Trả lời

Pipeline đã được phát triển để hỗ trợ hai dạng JSON:

1. JSON gọn cho mobile với:
   - `food_id`
   - `name`
   - `base_portion_g`
   - `components`
2. JSON đầy đủ cho debug/evaluation với:
   - Bounding box và polygon.
   - Confidence.
   - Phương pháp ước lượng gram.
   - Khoảng bất định.
   - Thành phần nhìn thấy và thành phần suy ra từ catalog.
   - Calculation trace.

Phân tích component hiện có ba mức bằng chứng:

- `visual_match`: detector nhìn thấy component trong vùng món tổng.
- `visual_metric_estimate`: component được nhìn thấy và ảnh có tỷ lệ mét để ước lượng.
- `catalog_prior`: component được suy ra từ công thức chuẩn, không phải model thực sự nhìn thấy.

Điểm quan trọng: VietFood67 chủ yếu gắn bbox món/thực phẩm, vì vậy component của món phức hợp vẫn phần lớn dựa vào catalog cho đến khi có dataset component-level.

---

## 3. Model hiện có gì và đi theo hướng nào?

### Câu hỏi

Model hiện tại đang làm gì và đang đi theo hướng nào?

### Trả lời

Model là một baseline end-to-end gồm:

- YOLO nhận diện món ăn.
- Mask bằng segmentation/SAM/GrabCut.
- Ước lượng khẩu phần từ hình học hoặc serving prior.
- Recipe catalog cho món phức hợp.
- Tính calories và macro.
- FastAPI và giao diện web để thử ảnh.
- JSON Schema, evaluation và calculation trace.

Hướng phát triển là tách thành các bài toán rõ ràng:

1. Dish detector.
2. Component detector/segmenter.
3. Portion hoặc mass regressor.
4. Nutrition knowledge base.
5. Calibration và active learning.

Detector tốt không đồng nghĩa toàn pipeline calories đã chính xác.

---

## 4. Chiều sâu, góc chụp xấu và thành phần trong món

### Câu hỏi

Model đã tính chiều sâu chưa? Nếu ảnh chụp góc xấu thì sao? Model đã biết trong món có thành phần gì chưa?

### Trả lời

- Model **chưa đo chiều sâu thật từ một ảnh RGB đơn lẻ**.
- Portion hiện dùng diện tích mask, độ dày giả định, mật độ và serving prior.
- Nếu có `cm_per_pixel`, đường kính đĩa hoặc marker thì kết quả hình học tốt hơn.
- Ảnh không có tỷ lệ mét chỉ nên trả serving prior cùng cảnh báo.
- Góc chụp xấu được kiểm tra gián tiếp qua độ nét, độ sáng và chất lượng ảnh; chưa có mô hình pose/depth hoàn chỉnh.
- Thành phần nhìn thấy chỉ được xác nhận khi detector thực sự phát hiện component; thành phần còn lại đến từ catalog.

Để cải thiện cần:

- Ảnh top-down và ảnh nghiêng khoảng 45°.
- Marker ArUco hoặc kích thước đĩa/bát thật.
- Ground truth gram.
- Component masks.
- Có thể thêm depth sensor hoặc ảnh thứ hai.

---

## 5. Có cần tải dataset không?

### Câu hỏi

Muốn thử model thì có cần tải VietFood67 không và tải như thế nào?

### Trả lời

- Không cần dataset nếu chỉ chạy inference bằng checkpoint đã train.
- Cần dataset nếu muốn train, validation hoặc test.
- Có thể tải bằng giao diện Kaggle hoặc Kaggle API.
- Trên Kaggle Notebook nên dùng **Add Input** để gắn dataset trực tiếp; không cần tải tay về `/kaggle/working`.

Dataset Kaggle có tên `vietfood68`, nhưng cấu hình dự án thường gọi VietFood67 vì có 67 nhóm thực phẩm/món và thêm class `Con nguoi`, tổng cộng 68 class ID.

---

## 6. Lỗi `kaggle is not recognized`

### Câu hỏi

PowerShell báo không nhận lệnh `kaggle auth login`.

### Trả lời

Nguyên nhân là Kaggle CLI chưa được cài hoặc chưa nằm trong PATH. Có thể:

- Cài package Kaggle bằng đúng Python.
- Chạy qua `python -m kaggle` nếu command entry point không có trong PATH.
- Hoặc bỏ qua CLI và tải dataset bằng giao diện web/Kaggle Notebook.

Với dự án này, cách đơn giản nhất là Add Input trong Kaggle Notebook.

---

## 7. Lỗi không tìm thấy cấu trúc YOLO

### Câu hỏi

`prepare-dataset` báo không tìm thấy `train/images` hoặc `images/train`.

### Trả lời

Đường dẫn truyền vào đang ở sai cấp thư mục. Root đúng phải chứa trực tiếp một trong hai dạng:

```text
images/train
images/valid
labels/train
labels/valid
```

hoặc:

```text
train/images
train/labels
valid/images
valid/labels
```

Trên Kaggle, dataset hiện tại thường nằm tại:

```text
/kaggle/input/datasets/thomasnguyen6868/vietfood68/dataset
```

Nên dùng đoạn code tự tìm `images/train` thay vì viết cứng đường dẫn mount.

---

## 8. Dataset hoặc code thay đổi có phải train lại từ đầu?

### Câu hỏi

Nếu dataset update hoặc code thay đổi thì có phải chạy lại toàn bộ không?

### Trả lời

Không phải thay đổi nào cũng yêu cầu train lại:

| Thay đổi | Xử lý |
|---|---|
| UI, API, JSON, logging | Không cần train lại |
| Nutrition catalog | Không cần train detector lại |
| Thêm dữ liệu cùng class map | Có thể fine-tune/resume, nhưng cần đánh giá lại |
| Đổi class ID hoặc số lớp | Phải remap dữ liệu và thường train/fine-tune lại |
| Đổi model architecture | Train run mới |
| Đổi augmentation để làm thí nghiệm | Nên train run mới để so sánh công bằng |
| Sửa bug preprocessing ảnh | Cần đánh giá lại; có thể phải train lại nếu input distribution đổi |

Resume chỉ phù hợp khi tiếp tục đúng cùng một experiment với cấu hình tương thích.

---

## 9. Máy local chỉ có PyTorch CPU

### Câu hỏi

`torch.cuda.is_available()` trả `False`; train local có lâu không và Kaggle khác gì?

### Trả lời

Máy local đang dùng bản PyTorch CPU, nên train toàn bộ VietFood67 sẽ rất chậm. Kaggle có GPU T4/P100 và thường nhanh hơn nhiều.

Khuyến nghị:

- Dùng máy local cho code, test nhỏ và inference CPU.
- Dùng Kaggle GPU cho train chính.
- Hai GPU chỉ hữu ích khi Ultralytics khởi tạo multi-GPU thành công.

---

## 10. Thiết lập Accelerator trên Kaggle

### Câu hỏi

Không thấy Accelerator ở đâu.

### Trả lời

Mở **Session options** ở panel bên phải và chọn GPU. Nếu tùy chọn bị khóa, Kaggle có thể yêu cầu xác minh số điện thoại hoặc danh tính.

Sau khi đổi Accelerator, Kaggle có thể tạo session mới và làm mất file chưa được sao lưu trong `/kaggle/working`.

---

## 11. Lỗi `ModuleNotFoundError: calcucalo`

### Câu hỏi

Đã `pip install -e` nhưng notebook vẫn không import được `calcucalo`.

### Trả lời

Nguyên nhân thường là kernel chưa nhận editable install hoặc đang dùng Python khác. Cách ổn định:

```python
import sys

SRC_PATH = "/kaggle/working/CalcuCalo/src"
if SRC_PATH not in sys.path:
    sys.path.insert(0, SRC_PATH)

import calcucalo
```

Nên cài bằng đúng kernel:

```python
import sys
!{sys.executable} -m pip install -e "/kaggle/working/CalcuCalo[inference]"
```

Không cần Factory Reset chỉ vì lỗi import.

---

## 12. Restart và Factory Reset trên Kaggle

### Câu hỏi

Reset ở đâu và có nên dùng không?

### Trả lời

- Restart kernel/session làm mất biến Python và có thể làm mất file tạm tùy loại session.
- Factory Reset là thao tác mạnh hơn và không cần cho lỗi import thông thường.
- Không restart, refresh hoặc đổi Accelerator khi đang train hoặc khi chưa sao lưu checkpoint.

---

## 13. Các cell Kaggle có liên quan nhau không?

### Câu hỏi

Các cell có phụ thuộc nhau không và cần chạy theo thứ tự nào?

### Trả lời

Có. Thứ tự cơ bản:

1. Kiểm tra GPU và đặt `DEVICE`.
2. Clone/pull source.
3. Cài package.
4. Thêm `src` vào `sys.path` và kiểm tra import.
5. Tìm `DATASET_ROOT`.
6. Tạo `vietfood67.yaml`.
7. Smoke test, có thể bỏ qua nếu đã chạy thành công trước đó.
8. Train chính.
9. Kiểm tra checkpoint và metric.
10. Export ONNX.
11. Test inference.
12. Đóng gói artifact.
13. Tải ZIP hoặc Save Version có Output.

Trong cùng session, nếu biến và file còn nguyên thì không cần chạy lại mọi cell.

---

## 14. Cách xác định đúng `DATASET_ROOT`

### Câu hỏi

Folder hiển thị `dataset/images/train`, `dataset/images/valid`, `dataset/labels/...` có đúng không?

### Trả lời

Đúng. Root cần dùng là folder `dataset`, không phải folder dataset cha và cũng không phải `images`.

Code tự tìm đã xác nhận:

```text
/kaggle/input/datasets/thomasnguyen6868/vietfood68/dataset
```

Sau đó dùng root này để tạo `/kaggle/working/vietfood67.yaml`.

---

## 15. Quên `--export-onnx` sau khi train

### Câu hỏi

Quên thêm `--export-onnx` thì có phải train lại không?

### Trả lời

Không. Chỉ cần export từ `best.pt`:

```python
from ultralytics import YOLO

model = YOLO("/kaggle/working/runs/detect/<run>/weights/best.pt")
onnx_path = model.export(format="onnx", dynamic=True, simplify=True)
print(onnx_path)
```

Export là bước hậu xử lý, không phải bước train.

---

## 16. Nên train bao nhiêu epoch?

### Câu hỏi

10 epoch có đủ không, có cần nhiều hơn không và có thể train 10 thay vì 15 không?

### Trả lời

- 1 epoch trên 1% dữ liệu chỉ là smoke test.
- 10 epoch là baseline nhanh hợp lý.
- 15 epoch đã đủ để chốt model v3 làm baseline.
- Không có số epoch cố định bảo đảm tốt; cần nhìn validation metric và loss.
- v4 có thể train 10 epoch để thử nhanh.
- So sánh 10 epoch v4 với 15 epoch v3 không hoàn toàn công bằng, nhưng đủ để quyết định có đáng train v4 thêm hay không.

---

## 17. Đánh giá checkpoint smoke test 1%

### Câu hỏi

Hai file `best.pt` và `last.pt` train trên 1% dataset đạt gì và còn thiếu gì?

### Trả lời

Checkpoint 1% chỉ chứng minh:

- Dataset đọc được.
- YOLO train được.
- Checkpoint được lưu.
- Pipeline inference chạy được.

Nó không chứng minh model đủ chính xác. Cần train toàn bộ dataset, đánh giá mAP/AP từng lớp và kiểm tra ảnh thực tế.

Kết quả này đã được ghi riêng trong `MODEL_EVALUATION_1_PERCENT.md`.

---

## 18. Lỗi sau khi train: `'dict' object has no attribute 'save_dir'`

### Câu hỏi

Train đã in metric nhưng script kết thúc bằng lỗi `results.save_dir`.

### Trả lời

Train thực tế đã hoàn thành; lỗi nằm ở wrapper lấy đường dẫn output sau khi multi-GPU trả về `dict`.

Code đã được sửa để lấy `save_dir` từ:

1. `results.save_dir` nếu có.
2. `model.trainer.save_dir` nếu kiểu trả về khác.

Nếu checkpoint đã tồn tại thì không cần train lại chỉ vì lỗi hậu xử lý này.

---

## 19. Không tìm thấy `best.pt` dù vừa train

### Câu hỏi

Đường dẫn `/kaggle/working/runs/.../weights/best.pt` báo không tồn tại.

### Trả lời

Nguyên nhân thường là:

- Session đã đổi hoặc restart.
- Đang ở version/output view thay vì draft session cũ.
- Run được lưu ở đường dẫn khác.
- `/kaggle/working` của session trước đã mất.

Tìm checkpoint bằng:

```python
!find /kaggle -type f -name "best.pt" 2>/dev/null
```

Nếu session đã reset và chưa tải/save output thì không thể phục hồi từ bộ nhớ tạm.

---

## 20. Tại sao refresh/restart làm mất output?

### Câu hỏi

Đã chọn `Files only` nhưng refresh hoặc session mới vẫn mất file.

### Trả lời

`Files only` là persistence best-effort, không phải backup đảm bảo. `/kaggle/working` có thể mất khi:

- Session crash hoặc bị thu hồi.
- Đổi accelerator/environment.
- Factory Reset.
- Chuyển sang phiên chạy sạch của Save & Run All.

Luôn giữ ít nhất một bản:

- ZIP tải về máy.
- Output của Saved Version.
- Kaggle Dataset/Model chứa checkpoint.

---

## 21. `Save Version` chạy lại và báo lỗi `device={device}`

### Câu hỏi

Chạy tương tác được nhưng Save & Run All lại báo `Invalid CUDA device={device}`.

### Trả lời

Trong notebook có placeholder `{DEVICE}` hoặc `{device}` chưa được tạo ở session sạch. Save & Run All chạy từ đầu nên mọi biến phải được tạo trước cell train.

Cell đầu phải có:

```python
import torch

DEVICE = "0,1" if torch.cuda.device_count() >= 2 else "0"
print(DEVICE)
```

Sau đó dùng đúng `{DEVICE}` trong IPython command. Không viết literal `device={device}` nếu biến `device` chưa tồn tại.

---

## 22. Quick Save nên lưu Output hay không?

### Câu hỏi

Trong tùy chọn Save Output của Quick Save nên chọn gì?

### Trả lời

Nếu đang có checkpoint/kết quả cần giữ, chọn:

```text
Always save output when creating a Quick Save
```

hoặc lưu output cho version hiện tại. Tuy nhiên sau khi train vẫn nên tải ZIP về máy vì đây là bản sao an toàn và dễ sử dụng nhất.

---

## 23. Đánh giá kết quả detector v3

### Câu hỏi

Đọc folder `vietfood67_yolo11n_v1` và đánh giá model v3.

### Trả lời

Artifact xác nhận:

| Thuộc tính | Giá trị |
|---|---:|
| Model | YOLO11n detect |
| Số lớp | 68 |
| Dữ liệu | 100% |
| Kế hoạch | 20 epoch |
| Hoàn thành | 15 epoch |
| Image size | 640 |
| Batch | 32 |
| GPU | T4 ×2 |
| Mosaic | 1.0, đóng ở giai đoạn cuối |

Metric epoch 15:

| Metric | Giá trị |
|---|---:|
| Precision | 0,7757 |
| Recall | 0,7106 |
| mAP50 | 0,7782 |
| mAP50–95 | 0,6254 |

Kết luận:

- Đây là development checkpoint tốt và có thể dùng làm baseline v3.
- Metric vẫn tăng, loss vẫn giảm; chưa thấy overfitting rõ.
- Thiếu confusion matrix, PR/F1 curve, AP từng class và test report.
- `labels.jpg` cho thấy mất cân bằng class.
- Dataset chứa nhiều ảnh collage 2×2; YOLO mosaic có thể tạo “collage của collage”.
- Detection metric không đo accuracy của gram/calories.

Kết quả đã được ghi vào phần v3 của `MODEL_STATUS_AND_ROADMAP.md`.

---

## 24. V4 cần thay đổi gì?

### Câu hỏi

Sau khi đánh giá v3, v4 nên thay đổi code/model như thế nào?

### Trả lời

Các thay đổi đã thực hiện:

- API đọc `completed_epochs` và `planned_epochs` từ checkpoint.
- Checkpoint 15/20 được đánh dấu `training_incomplete`, không gọi nhầm là candidate.
- Tự tìm checkpoint trong `*/weights/best.pt`.
- Script train hỗ trợ:
  - `--fraction`
  - `--mosaic`
  - `--close-mosaic`
  - `--save-period`
- Bổ sung test cho model readiness và metadata.
- Toàn bộ test đã đạt 24/24 tại thời điểm cập nhật.

Thí nghiệm detector v4 được đề xuất:

- Giữ YOLO11n.
- Giữ image size, batch, seed và dataset.
- Đổi một biến chính: `mosaic=0.0`.
- Train run mới để so sánh rõ với v3.

---

## 25. Có cần hoàn thành v3 đến 20 epoch không?

### Câu hỏi

Ban đầu chỉ cần 10 epoch, hiện v3 đã có 15 epoch thì có cần chạy tiếp không?

### Trả lời

Không bắt buộc. Có thể chốt epoch 15 làm baseline v3 vì:

- Đã vượt mục tiêu baseline 10 epoch.
- Metric khá tốt.
- Có checkpoint dùng được.

Nếu ưu tiên nghiên cứu chặt chẽ, có thể hoàn thành 20 epoch. Nếu ưu tiên thời gian, giữ v3 epoch 15 và chuyển sang thí nghiệm v4.

---

## 26. Push code v4 rồi train mới hay resume v3?

### Câu hỏi

Sau khi push code v4 lên GitHub, Kaggle nên train lại hay tiếp tục v3?

### Trả lời mới nhất

- Push code v4 lên GitHub.
- Pull/clone code v4 trên Kaggle.
- Giữ v3 epoch 15 làm baseline.
- Train **run v4 mới từ `yolo11n.pt`**, không resume v3, vì v4 đổi mosaic.
- Có thể train v4 10 epoch để tiết kiệm thời gian.

Nếu chỉ dùng các thay đổi Web/API của code v4 thì không cần train lại; v4 có thể dùng trực tiếp checkpoint v3.

---

## 27. Những file không nên push lên GitHub

### Câu hỏi

Push code v4 cần lưu ý gì?

### Trả lời

Không nên dùng `git add .` khi folder kết quả chứa toàn bộ epoch. Nên ignore:

```gitignore
/best.pt
/last.pt
/vietfood67.yaml
/vietfood67_yolo11n_v1/
```

Nên stage có chọn lọc source, test và tài liệu; checkpoint/dataset nên lưu bằng Kaggle Output, Kaggle Model/Dataset hoặc storage riêng.

---

## 28. Khi GitHub có version code mới thì chạy lại cell nào?

### Câu hỏi

Cần thứ tự lệnh nào khi code có version mới và không cần chạy lại lệnh nào?

### Trả lời

Một chương riêng đã được thêm vào `KAGGLE_TRAINING_GUIDE.md`:

1. `git pull --ff-only`.
2. Cài lại editable package.
3. Kiểm tra version trong Python process mới.
4. Kiểm tra `DEVICE`, `DATASET_ROOT` và YAML.
5. Train run mới hoặc resume tùy loại thay đổi.

Trong cùng session, không cần:

- Add Input lại.
- Tải dataset lại.
- Smoke test lại nếu đã thành công.
- Tạo YAML lại nếu vẫn hợp lệ.
- Restart/Factory Reset.
- Xóa run cũ.

---

## 29. Kaggle dừng ở bước quét dataset

### Câu hỏi

Output đứng ở các dòng `duplicate labels removed`, `cache directory is not writable` và `val: Scanning` thì có phải lỗi không?

### Trả lời

Các dòng này thường không phải lỗi:

- Ultralytics tự loại nhãn trùng trong bộ nhớ.
- `/kaggle/input` chỉ đọc nên không ghi cache được.
- Trước epoch đầu tiên, Ultralytics phải quét train/validation và khởi tạo multi-GPU.

Nếu cell vẫn chạy, cần chờ đến khi xuất hiện:

```text
Epoch    GPU_mem    box_loss    cls_loss    dfl_loss
1/10
```

Không refresh hoặc chạy cell train lần hai khi cell cũ vẫn hoạt động.

---

## 30. Run tồn tại nhưng không có `last.pt` và `results.csv`

### Câu hỏi

Kết quả kiểm tra cho thấy run tồn tại nhưng không có checkpoint hoặc metric.

### Trả lời

Điều này nghĩa là tiến trình dừng trước khi hoàn thành epoch đầu tiên. Không có trạng thái để resume.

Cách xử lý:

- Không chạy `resume`.
- Không cần clone, cài package hoặc tạo YAML lại nếu session còn nguyên.
- Chạy lại train bằng tên run mới để không trộn artifact.
- Nếu multi-GPU tiếp tục dừng, thử `device=0` và gửi traceback cuối output.

---

## 31. Khác nhau giữa script dự án và `yolo detect train`

### Câu hỏi

Hai lệnh sau khác gì nhau?

- `python scripts/train_detector.py ...`
- `yolo detect train ...`

### Trả lời

Cả hai đều gọi Ultralytics YOLO. Khác biệt:

| Script dự án | Ultralytics CLI |
|---|---|
| Wrapper của CalcuCalo | Lệnh trực tiếp của Ultralytics |
| Dùng `--image-size` | Dùng `imgsz` |
| Hỗ trợ export ONNX bằng flag | Export riêng |
| Tự đặt seed/deterministic/plots | Phải truyền trực tiếp |
| Hỗ trợ tham số v4 đã bổ sung | Hỗ trợ qua cú pháp `key=value` |
| Dùng đúng Python với `sys.executable` | Dùng executable `yolo` trong PATH |

Hai lệnh chỉ gần tương đương khi truyền cùng toàn bộ tham số. Nếu CLI không có:

```text
mosaic=0.0
close_mosaic=0
```

thì nó vẫn dùng mosaic mặc định và không phải experiment v4 dự kiến.

Lệnh CLI được ưu tiên khi cần chẩn đoán multi-GPU trên Kaggle vì luồng chạy đơn giản hơn.

---

## 32. Lệnh train v4 hiện được khuyến nghị

```python
RUN_NAME = "vietfood67_yolo11n_v4_no_mosaic_10e_retry1"
```

```python
!yolo detect train \
  data=/kaggle/working/vietfood67.yaml \
  model=yolo11n.pt \
  epochs=10 \
  imgsz=640 \
  batch=32 \
  device={DEVICE} \
  workers=4 \
  patience=10 \
  seed=42 \
  deterministic=True \
  plots=True \
  save_period=1 \
  fraction=1.0 \
  mosaic=0.0 \
  close_mosaic=0 \
  project=/kaggle/working/runs/detect \
  name={RUN_NAME} \
  exist_ok=True
```

Sau epoch đầu tiên phải xuất hiện:

```text
/kaggle/working/runs/detect/<RUN_NAME>/weights/last.pt
```

Nếu `last.pt` tồn tại và session bị gián đoạn, resume bằng:

```python
from pathlib import Path

LAST_PT = Path("/kaggle/working/runs/detect") / RUN_NAME / "weights" / "last.pt"
assert LAST_PT.is_file()

!yolo detect train resume model={LAST_PT}
```

---

## 33. Trạng thái hiện tại và việc cần làm tiếp theo

### Đã có

- Source code v4 cho Web/API/readiness và image quality.
- Detector v3 YOLO11n epoch 15 làm baseline.
- Metric validation v3 đã được ghi vào roadmap.
- Hướng dẫn Kaggle đầy đủ và chương cập nhật code version.
- Script train hỗ trợ cấu hình v4.

### Đang làm

- Train run v4 YOLO11n 10 epoch với `mosaic=0.0`.

### Sau khi v4 train xong

1. Giữ `best.pt`, `last.pt`, `results.csv`, plots và `args.yaml`.
2. Chạy test split và lấy AP từng lớp/confusion matrix.
3. So sánh v3 và v4 trên cùng test set.
4. Kiểm tra thêm ảnh điện thoại không phải collage.
5. Chọn model tốt hơn rồi export ONNX.
6. Chưa gọi pipeline là production-ready cho đến khi có ground truth gram/calories.

---

## 34. Danh sách tài liệu và code quan trọng

| File | Vai trò |
|---|---|
| `README.md` | Tổng quan dự án và cách sử dụng |
| `KAGGLE_TRAINING_GUIDE.md` | Quy trình Kaggle từ đầu đến cuối |
| `MODEL_STATUS_AND_ROADMAP.md` | Trạng thái từng version và kế hoạch cải thiện |
| `MODEL_EVALUATION_1_PERCENT.md` | Đánh giá smoke test 1% |
| `scripts/train_detector.py` | Wrapper train detector |
| `src/calcucalo/detector.py` | Backend Ultralytics/ONNX và metadata model |
| `src/calcucalo/analyzer.py` | Ghép detection, mask, portion và nutrition |
| `src/calcucalo/api.py` | FastAPI, Web UI và model readiness |
| `src/calcucalo/evaluation.py` | Evaluation end-to-end |
| `configs/vietfood67_classes.yaml` | Class map 68 lớp |
| `configs/food_catalog.json` | Recipe và nutrition prior |

---

## 35. Nguyên tắc cuối cùng

- Không đánh đồng mAP detector với độ chính xác calories.
- Không đánh đồng thành phần từ catalog với thành phần model thực sự nhìn thấy.
- Không để checkpoint quan trọng chỉ tồn tại trong `/kaggle/working`.
- Không resume khi đã đổi kiến trúc, class map hoặc augmentation cần so sánh.
- Không ghi đè run cũ; luôn đặt `RUN_NAME` mới cho experiment mới.
- Chỉ thay đổi một biến chính mỗi experiment để biết điều gì tạo ra cải thiện.
- Luôn đánh giá trên test độc lập và ảnh điện thoại thực tế trước khi chọn model.

---

## 36. Các câu hỏi ngắn khác đã được xử lý

### Làm gì ở bước đăng nhập và xác minh Kaggle?

Phải đăng nhập tài khoản Kaggle trước khi sửa/chạy notebook. Nếu GPU/TPU bị khóa, hoàn thành xác minh số điện thoại hoặc danh tính trong tài khoản. Sau đó mở Session options để chọn Accelerator.

### Đã bổ sung sơ đồ cấu trúc thư mục chưa?

README đã được mở rộng với cây thư mục và mô tả vai trò của source, config, schema, script, test, data, model và output.

### File báo cáo version nên sắp xếp như thế nào?

Version mới nhất được đặt ở đầu `MODEL_STATUS_AND_ROADMAP.md`; nội dung version cũ được giữ nguyên bên dưới để theo dõi lịch sử và đối chiếu thay đổi.

### “Gấp đôi dữ liệu train” có phải nhân đôi dataset không?

Không. Nếu giữ nguyên dataset nhưng tăng từ 10 lên 20 epoch thì model nhìn lại dữ liệu khoảng gấp đôi và thời gian gần gấp đôi; số ảnh gốc không tăng. Nhân bản ảnh không tạo thêm thông tin và có thể làm model overfit.

### Vì sao bước tìm dataset hoặc chuẩn bị dataset lâu?

Tìm đệ quy bằng `rglob` trên `/kaggle/input` và quét hàng chục nghìn label qua mounted storage có thể mất thời gian. Chỉ cần làm một lần trong session nếu `DATASET_ROOT` và YAML vẫn còn.

### Có thể bỏ bước tạo YAML rồi train luôn không?

Không nên. YOLO cần file YAML có `path`, `train`, `val`, `test` và class map. Biến `DATASET_ROOT` chỉ cần trong Python để tạo YAML; sau khi `/kaggle/working/vietfood67.yaml` đã hợp lệ, lệnh train chỉ cần đường dẫn YAML.

### Nếu bỏ smoke test thì bước sau cần gì?

Có thể bỏ smoke test. Train chính vẫn cần:

- GPU/`DEVICE` hợp lệ.
- Source và dependency đã cài.
- Dataset đã Add Input.
- `vietfood67.yaml` hợp lệ.

Không cần checkpoint smoke test.

### Cảnh báo duplicate label có làm hỏng dataset không?

Ultralytics loại duplicate label trong bộ nhớ và tiếp tục. Đây là dấu hiệu dataset cần QA, nhưng không phải lỗi khiến train bắt buộc dừng. Nên thống kê và làm sạch label trong một phiên bản dataset sau.

### `best.pt` và `last.pt` khác nhau thế nào?

- `best.pt`: epoch có fitness validation tốt nhất, ưu tiên inference/export.
- `last.pt`: trạng thái epoch mới nhất, ưu tiên resume.
- Khi epoch cuối cũng là epoch tốt nhất, hai file có thể giống nhau.

### Có nên đưa mọi checkpoint epoch lên GitHub không?

Không. GitHub nên chứa source, config và tài liệu. Artifact model nên được đóng ZIP hoặc lưu bằng Kaggle Output, Kaggle Model/Dataset, release storage hoặc model registry.

---

## 37. Nhật ký tất cả câu lệnh đã được hỏi hoặc chạy

Các lệnh dưới đây được chuẩn hóa lại từ nội dung đã gửi trong cuộc trao đổi. Những ký tự bị HTML escape, Markdown làm đậm hoặc xuống dòng sai đã được sửa để thể hiện đúng lệnh dự kiến.

### 37.1. Tóm tắt nhanh kết quả từng nhóm lệnh

| STT | Lệnh/mục đích | Kết quả đã quan sát | Kết luận hiện tại |
|---:|---|---|---|
| 1 | `kaggle auth login` trên Windows | PowerShell không nhận lệnh `kaggle` | Kaggle CLI chưa cài/chưa có trong PATH; dùng Add Input trên Notebook là đơn giản nhất |
| 2 | `prepare-dataset` trên máy local | Không tìm thấy cấu trúc YOLO | Đã truyền root cao hơn một cấp; cần trỏ tới folder `dataset` |
| 3 | Kiểm tra PyTorch/CUDA local | `2.14.0+cpu`, `CUDA: False` | Máy local chỉ dùng CPU |
| 4 | Clone và editable install trên Kaggle | Clone và build package thành công | Source có ở `/kaggle/working/CalcuCalo` |
| 5 | Import `calcucalo` sau cài đặt | `ModuleNotFoundError` | Kernel chưa thấy `src`; dùng đúng `sys.executable` và thêm `src` vào `sys.path` |
| 6 | Smoke test YOLO 1% | Chạy thành công, có checkpoint | Chỉ xác nhận pipeline, không dùng làm model chính |
| 7 | Train qua `scripts/train_detector.py --export-onnx` | Train chạy, nhưng wrapper cũ lỗi `results.save_dir` sau train | Checkpoint vẫn có; wrapper đã được sửa |
| 8 | Export ONNX thủ công | Không tìm thấy folder `weights` theo đường dẫn dự kiến | Session/path đã thay đổi hoặc output chưa còn |
| 9 | `find` checkpoint trong `/kaggle/working/runs` | Có lần báo folder không tồn tại | `/kaggle/working` của session trước đã mất |
| 10 | Tự tìm `DATASET_ROOT` | Tìm được root đúng của VietFood67 | Dùng root kết thúc bằng `/vietfood68/dataset` |
| 11 | Tạo `vietfood67.yaml` trên Kaggle | Lệnh dùng đường dẫn viết cứng từng thất bại | Dùng biến `DATASET_ROOT` đã dò được |
| 12 | Resume bằng `last.pt` | Checkpoint v3 tồn tại và còn optimizer | Có thể resume đúng experiment v3 |
| 13 | Train với literal `device={device}` | `Invalid CUDA device={device}` | Biến không được nội suy trong Save & Run All; phải tạo `DEVICE` trước |
| 14 | Kiểm tra file trong run v3 | Tìm thấy `epoch*.pt`, `best.pt`, `last.pt` | Run có thể resume và phân tích |
| 15 | Wrapper train v4 không mosaic | Tạo folder run nhưng dừng trước epoch đầu | Không có checkpoint để resume |
| 16 | Kiểm tra run v4 | `Run=True`, `last.pt=False`, `results.csv=False` | Phải chạy lại từ đầu với run name mới |
| 17 | So sánh wrapper và YOLO CLI | CLI được ưu tiên để chẩn đoán multi-GPU | Hai lệnh chỉ tương đương nếu truyền đủ cùng tham số |

### 37.2. Xác thực Kaggle CLI trên Windows

Lệnh đã chạy:

```powershell
kaggle auth login
```

Kết quả:

```text
kaggle : The term 'kaggle' is not recognized...
```

Ý nghĩa: executable `kaggle` chưa có trong PATH. Với workflow hiện tại không cần chạy lại lệnh này vì dataset được gắn bằng Add Input trong Kaggle Notebook.

### 37.3. Chuẩn bị dataset trên máy local

Lệnh đã chạy:

```powershell
python -m calcucalo.cli prepare-dataset `
  "data\raw\vietfood67" `
  --output "configs\vietfood67.yaml"
```

Kết quả:

```text
FileNotFoundError: Could not find YOLO train/val folders.
```

Folder thực tế có thêm cấp `dataset`, vì vậy dạng đúng là:

```powershell
python -m calcucalo.cli prepare-dataset `
  "data\raw\vietfood67\dataset" `
  --output "configs\vietfood67.yaml"
```

### 37.4. Kiểm tra PyTorch và CUDA trên máy local

Lệnh đã chạy, sau khi chuẩn hóa tên thuộc tính Python:

```powershell
python -c "import torch; print(torch.__version__); print('CUDA:', torch.cuda.is_available())"
```

Kết quả:

```text
2.14.0+cpu
CUDA: False
```

Kết luận: môi trường local không có CUDA PyTorch, nên train chính được chuyển lên Kaggle GPU.

### 37.5. Clone và cài dự án trên Kaggle

Các lệnh đã chạy:

```python
!git clone https://github.com/TheMinh04/CalculateCaloFromFood.git /kaggle/working/CalcuCalo
%cd /kaggle/working/CalcuCalo
!python -m pip install -q -e ".[inference]" onnx onnxslim
```

Kết quả:

- Git clone thành công.
- Editable wheel được build và cài thành công.
- Package distribution `calcucalo-vision` tồn tại.

Sau đó lệnh import:

```python
import calcucalo
import ultralytics

print("CalcuCalo:", calcucalo.__version__)
print("Ultralytics:", ultralytics.__version__)
```

từng trả:

```text
ModuleNotFoundError: No module named 'calcucalo'
```

Lệnh thay thế ổn định hơn:

```python
import sys

!{sys.executable} -m pip install -q \
  -e "/kaggle/working/CalcuCalo[inference]" \
  onnx \
  onnxslim

SRC_PATH = "/kaggle/working/CalcuCalo/src"
if SRC_PATH not in sys.path:
    sys.path.insert(0, SRC_PATH)

import calcucalo
import ultralytics
```

### 37.6. Kiểm tra GPU Kaggle

Nhóm lệnh đã sử dụng trong notebook:

```python
!nvidia-smi

import torch

print("CUDA:", torch.cuda.is_available())
print("Số GPU:", torch.cuda.device_count())

DEVICE = "0,1" if torch.cuda.device_count() >= 2 else "0"
print("Thiết bị sẽ dùng:", DEVICE)
```

Kết quả đã quan sát trong các session train:

- CUDA hoạt động.
- Kaggle cấp hai GPU T4.
- `DEVICE` đúng là `0,1`.

### 37.7. Tự tìm root dataset trên Kaggle

Đoạn lệnh đã chạy:

```python
from pathlib import Path

candidates = []

for images_train in Path("/kaggle/input").glob("**/images/train"):
    dataset_root = images_train.parent.parent
    if (dataset_root / "labels" / "train").is_dir():
        candidates.append(dataset_root)

print("Các dataset tìm thấy:")
for path in candidates:
    print(path)

assert candidates, "Không tìm thấy cấu trúc images/train + labels/train"

DATASET_ROOT = candidates[0]
print("Sử dụng:", DATASET_ROOT)
```

Kết quả:

```text
/kaggle/input/datasets/thomasnguyen6868/vietfood68/dataset
```

Một biến thể kiểm tra trực tiếp cũng đã được dùng:

```python
from pathlib import Path

DATASET_ROOT = Path(
    "/kaggle/input/datasets/thomasnguyen6868/vietfood68/dataset"
)

assert (DATASET_ROOT / "images" / "train").is_dir()
assert (DATASET_ROOT / "images" / "valid").is_dir()
assert (DATASET_ROOT / "labels" / "train").is_dir()
assert (DATASET_ROOT / "labels" / "valid").is_dir()

print("Dataset:", DATASET_ROOT)
```

Kết quả: các `assert` thành công, xác nhận root đúng.

### 37.8. Tạo YAML trên Kaggle

Lệnh từng dùng với đường dẫn chưa đúng:

```python
!PYTHONPATH=/kaggle/working/CalcuCalo/src \
python -m calcucalo.cli prepare-dataset \
  "/kaggle/input/vietfood68/dataset" \
  --output "/kaggle/working/vietfood67.yaml"
```

Kết quả: không tìm thấy layout vì đường dẫn mount thực tế có thêm `datasets/thomasnguyen6868`.

Cách đã được chuẩn hóa trong guide là truyền `DATASET_ROOT` bằng `subprocess.run`, tạo thành công:

```text
/kaggle/working/vietfood67.yaml
```

YAML có `train`, `val`, `test` và đủ 68 class ID.

### 37.9. Smoke test 1% dữ liệu

Lệnh đã chạy:

```python
!yolo detect train \
  data=/kaggle/working/vietfood67.yaml \
  model=yolo11n.pt \
  epochs=1 \
  imgsz=320 \
  batch=32 \
  device=0 \
  workers=4 \
  fraction=0.01 \
  val=False \
  project=/kaggle/working/runs/detect \
  name=smoke_test
```

Kết quả được báo cáo:

```text
Speed: 0.1ms preprocess, 3.8ms inference, 0.0ms loss, 0.2ms postprocess per image
```

Kết luận: GPU, dataset và YOLO chạy được. Checkpoint này không đủ để đánh giá độ chính xác.

### 37.10. Train model chính bằng wrapper cũ

Lệnh đã chạy/được hỏi:

```python
!python scripts/train_detector.py \
  --data "/kaggle/working/vietfood67.yaml" \
  --model "yolo11n.pt" \
  --epochs 10 \
  --image-size 640 \
  --batch 32 \
  --device "0,1" \
  --workers 4 \
  --project "/kaggle/working/runs/detect" \
  --name "vietfood67_yolo11n_v1" \
  --export-onnx
```

Kết quả:

- YOLO đã train và validation.
- Output được ghi vào run `vietfood67_yolo11n_v1`.
- Wrapper cũ lỗi sau train:

```text
AttributeError: 'dict' object has no attribute 'save_dir'
```

Lỗi không nằm trong quá trình học; code wrapper sau đó đã được sửa bằng `resolve_save_dir()`.

### 37.11. Export ONNX thủ công

Lệnh đã chạy:

```python
from ultralytics import YOLO

best_path = "/kaggle/working/runs/detect/vietfood67_yolo11n_v1/weights/best.pt"

model = YOLO(best_path)
onnx_path = model.export(
    format="onnx",
    dynamic=True,
    simplify=True,
)

print("ONNX:", onnx_path)
```

Kết quả liên quan:

```text
ls: cannot access '/kaggle/working/runs/detect/vietfood67_yolo11n_v1/weights': No such file or directory
```

Nguyên nhân: checkpoint không còn ở session/path đó. Bản thân cú pháp export là đúng và không cần train lại nếu `best.pt` tồn tại.

### 37.12. Các lệnh tìm checkpoint

Các lệnh đã chạy:

```python
!find /kaggle/working/runs -type f -name "best.pt"
```

Có lần trả:

```text
find: '/kaggle/working/runs': No such file or directory
```

Sau đó dùng phạm vi rộng hơn:

```python
!find /kaggle -type f -name "best.pt" 2>/dev/null
```

Và lệnh liệt kê artifact:

```python
!find /kaggle/working/runs -type f | head -100
```

Ở session còn dữ liệu, lệnh cuối đã tìm thấy:

- `epoch*.pt`
- `best.pt`
- `last.pt`
- `args.yaml`
- `results.csv`
- ảnh batch train

### 37.13. Resume model v3

Lệnh đã được hỏi và xác nhận có thể dùng khi `last.pt` còn tồn tại:

```python
from ultralytics import YOLO

model = YOLO(
    "/kaggle/working/runs/detect/vietfood67_yolo11n_v1/weights/last.pt"
)

model.train(resume=True)
```

Kết quả sau các session resume được lưu trong artifact v3:

- Hoàn thành đến epoch 15.
- Precision `0.77569`.
- Recall `0.71064`.
- mAP50 `0.77820`.
- mAP50–95 `0.62540`.

### 37.14. Lệnh train dùng placeholder sai trong Saved Version

Lệnh notebook từng chứa giá trị dạng:

```text
device={device}
```

Kết quả Save & Run All:

```text
ValueError: Invalid CUDA 'device={device}' requested.
torch.cuda.is_available(): True
torch.cuda.device_count(): 2
```

GPU vẫn hoạt động; lỗi là placeholder không được thay. Dạng đúng sau khi tạo biến là:

```python
device={DEVICE}
```

hoặc ghi trực tiếp:

```text
device=0,1
```

### 37.15. Lệnh wrapper train v4 không mosaic

Lệnh đã chạy/được so sánh:

```python
import sys

!{sys.executable} scripts/train_detector.py \
  --data "/kaggle/working/vietfood67.yaml" \
  --model "yolo11n.pt" \
  --epochs 10 \
  --image-size 640 \
  --batch 32 \
  --device {DEVICE} \
  --workers 4 \
  --patience 10 \
  --mosaic 0.0 \
  --close-mosaic 0 \
  --save-period 1 \
  --project "/kaggle/working/runs/detect" \
  --name {RUN_NAME}
```

Kết quả của lần chạy được kiểm tra sau đó:

```text
Run tồn tại: True
last.pt tồn tại: False
results.csv tồn tại: False
```

Kết luận: run dừng trong giai đoạn quét/khởi tạo trước khi hoàn tất epoch đầu tiên; không thể resume.

### 37.16. Lệnh YOLO CLI được đem ra so sánh

Lệnh đã gửi:

```python
!yolo detect train \
  data=/kaggle/working/vietfood67.yaml \
  model=yolo11n.pt \
  epochs=10 \
  imgsz=640 \
  batch=32 \
  device={DEVICE} \
  workers=4 \
  patience=10 \
  seed=42 \
  deterministic=True \
  plots=True \
  save_period=1 \
  project=/kaggle/working/runs/detect \
  name={RUN_NAME} \
  exist_ok=True
```

Kết luận khi so sánh: lệnh này **chưa phải cấu hình v4 không mosaic** vì thiếu:

```text
mosaic=0.0
close_mosaic=0
```

Nếu không thêm, Ultralytics dùng mặc định gần với experiment v3.

### 37.17. Lệnh CLI v4 đầy đủ hiện tại

Phiên bản đã được sửa đầy đủ:

```python
RUN_NAME = "vietfood67_yolo11n_v4_no_mosaic_10e_retry1"
```

```python
!yolo detect train \
  data=/kaggle/working/vietfood67.yaml \
  model=yolo11n.pt \
  epochs=10 \
  imgsz=640 \
  batch=32 \
  device={DEVICE} \
  workers=4 \
  patience=10 \
  seed=42 \
  deterministic=True \
  plots=True \
  save_period=1 \
  fraction=1.0 \
  mosaic=0.0 \
  close_mosaic=0 \
  project=/kaggle/working/runs/detect \
  name={RUN_NAME} \
  exist_ok=True
```

Trạng thái: đây là lệnh nên dùng cho lần retry v4. Sau khi epoch 1 kết thúc mới có `last.pt` để resume.

### 37.18. Lệnh kiểm tra run có resume được hay không

Lệnh kiểm tra đã được dùng:

```python
from pathlib import Path
import pandas as pd

RUN_NAME = "vietfood67_yolo11n_v4_no_mosaic_10e"
RUN_DIR = Path("/kaggle/working/runs/detect") / RUN_NAME
LAST_PT = RUN_DIR / "weights" / "last.pt"
RESULTS_CSV = RUN_DIR / "results.csv"

print("Run tồn tại:", RUN_DIR.exists())
print("last.pt tồn tại:", LAST_PT.exists())
print("results.csv tồn tại:", RESULTS_CSV.exists())

if RESULTS_CSV.exists():
    results = pd.read_csv(RESULTS_CSV)
    print("Số epoch đã hoàn thành:", len(results))
    display(results.tail())
```

Kết quả thực tế:

```text
Run tồn tại: True
last.pt tồn tại: False
results.csv tồn tại: False
```

Do đó không dùng:

```python
!yolo detect train resume model={LAST_PT}
```

cho run này. Phải chạy lại từ pretrained `yolo11n.pt` với tên retry mới.
