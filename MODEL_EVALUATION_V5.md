# Đánh giá detector v5 sau 5 epoch fine-tune

Ngày đánh giá: **30/09/2026**  
Run: `vietfood67_yolo11n_v5_ft_from_v4_5e`  
Checkpoint đánh giá: `weights/best.pt`

## Kết luận ngắn

V5 là checkpoint detector tốt nhất hiện có nếu ưu tiên precision và mAP. So với v4, mọi metric
chính đều tăng; so với v3 epoch 15, v5 gần như ngang mAP nhưng precision cao hơn và recall thấp
hơn nhẹ. Đường validation vẫn cải thiện ở epoch cuối và chưa có dấu hiệu overfit rõ.

V5 mới là **detector candidate**, chưa phải pipeline calories production-ready. Folder được cung
cấp không có `test_metrics.json` và `best.onnx`, nên kết quả dưới đây là validation, chưa phải
đánh giá test độc lập.

## So sánh metric validation

| Run | Precision | Recall | mAP50 | mAP50–95 |
|---|---:|---:|---:|---:|
| V4, epoch 10 | 0,75732 | 0,68201 | 0,75035 | 0,60228 |
| V3, epoch 15 | 0,77569 | **0,71064** | 0,77820 | 0,62540 |
| **V5, fine-tune epoch 5** | **0,78613** | 0,70297 | **0,77935** | **0,62579** |

Thay đổi của v5 so với v4:

- Precision: **+0,02881**.
- Recall: **+0,02096**.
- mAP50: **+0,02900**.
- mAP50–95: **+0,02351**.
- Validation classification loss giảm từ **0,96535** xuống **0,89591**.

So với v3 epoch 15, v5 tăng precision **0,01044**, nhưng recall giảm **0,00767**. Hai model gần
như hòa về mAP; v5 phù hợp hơn cho ứng dụng calories vì false positive có thể tạo thêm món và
làm tăng calories sai.

## Đọc đường cong và ảnh dự đoán

- Precision, recall, mAP50 và mAP50–95 tăng liên tục đến epoch cuối.
- Validation box/class/DFL loss giảm liên tục, chưa thấy khoảng cách train–validation mở rộng.
- Train loss tăng ở epoch 2 rồi mới giảm. `args.yaml` ghi `optimizer=auto`; learning rate thực tế
  trong `results.csv` cao hơn nhiều `lr0=0.001`. Đây là dấu hiệu Ultralytics auto optimizer đã
  ghi đè ý định fine-tune bảo thủ.
- F1 toàn bộ lớp đạt khoảng **0,74 tại confidence 0,384**. Vì vậy ngưỡng món chính mặc định được
  đổi từ 0,25 thành **0,38**; component pass vẫn dùng 0,15 trong crop có ràng buộc recipe.
- Confusion matrix có đường chéo rõ, nhưng lỗi với `background` vẫn xuất hiện trên nhiều lớp.
  Ảnh validation cho thấy model xử lý được box lồng nhau và nhiều instance, đồng thời vẫn còn
  một số dự đoán thừa/thiếu ở món giống nhau hoặc vật thể nhỏ.

## Artifact đã có và còn thiếu

Đã có:

- `best.pt`, `last.pt`, `epoch0.pt` đến `epoch4.pt`;
- `results.csv`, `results.png`;
- PR/P/R/F1 curve, confusion matrix;
- ảnh label và prediction của validation.

Còn thiếu trong folder được cung cấp:

- `test_metrics.json`;
- kết quả/plot trên `split=test`;
- `weights/best.onnx`.

Không cần train lại để tạo các file còn thiếu. Dùng `scripts/evaluate_detector.py` trên Kaggle với
`best.pt`, `vietfood67.yaml`, `--split test` và `--export-onnx`.

## Thay đổi code sau đánh giá

Phiên bản nguồn **0.5.1** áp dụng các sửa đổi sau:

1. Fine-tune mặc định dùng optimizer `SGD` rõ ràng để `lr0` không bị `optimizer=auto` ghi đè.
2. Thêm `--optimizer` để thí nghiệm có thể tái lập.
3. Ngưỡng dish detection mặc định đổi thành `0.38` theo đỉnh F1 của v5.
4. Thêm `scripts/evaluate_detector.py` để test/export checkpoint đã train mà không train lại.
5. Thêm folder v5 vào `.gitignore` để tránh commit nhầm weights và ảnh artifact.

## Quyết định tiếp theo

1. Chạy test độc lập và export ONNX trước; chưa fine-tune thêm ngay.
2. Nếu test giữ được mAP50–95 và recall, chọn v5 `best.pt` làm detector mặc định.
3. Đánh giá ảnh điện thoại thực tế, đặc biệt món phức hợp và thành phần nhỏ.
4. Đo riêng component precision/recall và sai số gram/calories trên dataset component-level;
   metric detector món không chứng minh calories chính xác.
