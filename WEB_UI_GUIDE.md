# Hướng dẫn chạy và sử dụng giao diện CalcuCalo

Giao diện web này dùng để thử nhanh model trên ảnh món ăn, xem model nhận diện gì,
kiểm tra cách hệ thống ước lượng khối lượng và đọc kết quả dinh dưỡng/JSON. Toàn bộ
giao diện và API chạy trên máy của bạn; không cần tải ảnh lên dịch vụ bên ngoài.

> Kết quả calories và khối lượng là **ước tính**. Một ảnh RGB đơn không đo trực tiếp
> được chiều sâu món ăn. Khi không có vật chuẩn, hệ thống phải dùng khẩu phần mẫu.

## 1. Chuẩn bị

- Python 3.10 trở lên.
- Một model Ultralytics `.pt` hoặc ONNX `.onnx`.
- Với model hiện tại, file khuyên dùng là
  `vietfood67_yolo11n_v4_no_mosaic_10e/weights/best.pt` cho đến khi v5 được đánh giá xong.

Mở PowerShell tại thư mục dự án:

```powershell
cd D:\Model\CalcuCalo
python -m pip install -e ".[all]"
```

Lệnh cài đặt chỉ cần chạy lần đầu, hoặc chạy lại khi `pyproject.toml` thay đổi.

## 2. Khởi động giao diện trên Windows

### Cách rõ ràng nhất: chỉ định model

```powershell
cd D:\Model\CalcuCalo
$env:CALCUCALO_MODEL = "D:\Model\CalcuCalo\vietfood67_yolo11n_v4_no_mosaic_10e\weights\best.pt"
python -m uvicorn calcucalo.api:app --host 127.0.0.1 --port 8000
```

Sau khi thấy dòng `Uvicorn running`, mở:

- Giao diện: <http://127.0.0.1:8000>
- Trạng thái: <http://127.0.0.1:8000/health>
- Thông tin model: <http://127.0.0.1:8000/api/v1/model/info>
- Tài liệu API: <http://127.0.0.1:8000/docs>

Nhấn `Ctrl+C` trong PowerShell để dừng server.

### Dùng CPU hoặc GPU

Mặc định hệ thống tự chọn thiết bị. Có thể đặt thủ công trước khi chạy server:

```powershell
# CPU
$env:CALCUCALO_DEVICE = "cpu"

# GPU CUDA đầu tiên
$env:CALCUCALO_DEVICE = "0"
```

Nếu PyTorch trên máy là bản CPU thì phải dùng `cpu`. Không nhập `{DEVICE}` theo
nghĩa đen; đó chỉ là chỗ giữ chỗ trong các ví dụ notebook.

### Linux/macOS

```bash
cd /duong-dan/CalcuCalo
python -m pip install -e '.[all]'
export CALCUCALO_MODEL='/duong-dan/CalcuCalo/vietfood67_yolo11n_v4_no_mosaic_10e/weights/best.pt'
python -m uvicorn calcucalo.api:app --host 127.0.0.1 --port 8000
```

## 3. Quy trình thử một ảnh

1. Kiểm tra thanh trạng thái model ở đầu trang. Nút phân tích chỉ bật khi model đã
   được nạp và ảnh hợp lệ đã được chọn.
2. Chọn ảnh JPG, PNG hoặc WebP, tối đa 15 MB. Nên chụp đủ sáng, rõ nét, trọn đĩa
   và gần vuông góc từ trên xuống.
3. Chọn cách hiệu chuẩn:
   - **Không hiệu chuẩn:** dễ thử nhất, nhưng gram chủ yếu dựa vào khẩu phần mẫu.
   - **Đĩa tròn:** nhập đường kính thật của đĩa theo cm. Đĩa cần hiện rõ viền.
   - **Tỷ lệ cm/px:** dùng khi bạn đã tự đo được tỷ lệ chính xác.
4. Bấm **Phân tích món ăn** và chờ kết quả.
5. Nếu biết khối lượng thật, sửa số gram trong bảng thành phần rồi bấm
   **Tính lại theo gram đã sửa**.
6. Dùng **Sao chép JSON** hoặc **Tải JSON** nếu cần tích hợp frontend/mobile.

Lần dự đoán đầu tiên thường chậm hơn vì model phải khởi tạo. Với CPU, mỗi ảnh có
thể mất nhiều thời gian hơn đáng kể so với GPU.

## 4. Cách đọc kết quả đúng

Giao diện tách kết quả thành ba lớp để tránh hiểu nhầm:

1. **Model nhìn thấy:** tên lớp, bounding box và confidence của detector.
2. **Hệ thống ước lượng:** gram và khoảng gram. Nếu có tỷ lệ mét, hệ thống dùng
   diện tích ảnh cùng độ dày/mật độ giả định; nếu không, dùng khẩu phần mẫu.
3. **Catalog tính toán:** calories, protein, fat và carb được tính từ số gram và
   dữ liệu dinh dưỡng trên 100 g.

Component pass được bật mặc định trong API. Với món phức hợp, hệ thống crop vùng món có thêm
padding, chạy lượt detect thứ hai ở độ phân giải cao hơn và giữ nhiều vùng rời của cùng một
nguyên liệu. Giao diện hiển thị cả số **loại thành phần** và số **vùng nhìn thấy**. Khi không có
tỷ lệ mét, việc nhìn thấy thành phần không đồng nghĩa model đã đo được gram; gram vẫn lấy từ
công thức mẫu và giao diện sẽ hiển thị đúng cơ sở tính này.

Các nhãn cơ sở thành phần:

| Nhãn giao diện | Ý nghĩa |
|---|---|
| Model nhìn thấy | Thành phần có bằng chứng trực tiếp từ detector |
| Nhìn thấy + có tỷ lệ mét | Có bằng chứng ảnh và hiệu chuẩn kích thước |
| Công thức mẫu | Thành phần không được thấy trực tiếp, được lấy từ recipe catalog |
| Gram do người dùng sửa | Khối lượng đã được bạn nhập lại |

Confidence cao chỉ có nghĩa detector tự tin về **nhãn/vùng ảnh**; nó không đảm bảo
khối lượng và calories chính xác. Hãy xem thêm chất lượng ảnh, khoảng gram, cảnh
báo và cơ sở tính của từng thành phần.

## 5. Chọn ảnh test tốt

Nên dùng:

- một món hoặc một đĩa chính trong ảnh;
- ánh sáng đều, không bị cháy sáng hoặc quá tối;
- ảnh nét, món không bị che khuất;
- camera gần hướng từ trên xuống;
- có đĩa/vật chuẩn với kích thước biết trước nếu cần ước lượng gram tốt hơn.

Nên thử thêm các ca khó để đánh giá model: góc xiên, nhiều món, món bị che, hộp
đựng khác nhau, ánh sáng nhà hàng và món có hình thức gần giống nhau. Không đánh
giá model chỉ bằng ảnh thuộc tập train.

## 6. Kiểm tra nhanh bằng API

PowerShell:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
Invoke-RestMethod http://127.0.0.1:8000/api/v1/model/info
```

Gửi một ảnh và lưu JSON:

```powershell
curl.exe -X POST "http://127.0.0.1:8000/api/v1/food/analyze" `
  -F "image=@D:\duong-dan\mon-an.jpg" `
  -F "response_format=full" `
  -o analysis.json
```

## 7. Lỗi thường gặp

### `Model chưa sẵn sàng`

Kiểm tra đường dẫn model:

```powershell
Test-Path $env:CALCUCALO_MODEL
```

Nếu trả về `False`, đặt lại `CALCUCALO_MODEL` bằng đường dẫn tuyệt đối rồi khởi
động lại server.

### `No module named calcucalo`

Đảm bảo đang đứng trong thư mục dự án và cài editable bằng đúng Python:

```powershell
python -m pip install -e ".[all]"
python -c "import calcucalo; print(calcucalo.__version__)"
```

### Cổng 8000 đang được dùng

Đổi cổng:

```powershell
python -m uvicorn calcucalo.api:app --host 127.0.0.1 --port 8001
```

Sau đó mở <http://127.0.0.1:8001>.

### Kết quả có món nhưng calories không hợp lý

- Kiểm tra model có nhận đúng tên món không.
- Kiểm tra thành phần nào là `Công thức mẫu` thay vì được model nhìn thấy.
- Kiểm tra khoảng gram và cảnh báo góc chụp/chiều sâu.
- Nhập lại gram thực tế rồi tính lại.
- Đối chiếu dữ liệu dinh dưỡng trong catalog trước khi dùng cho mục đích thực tế.

## 8. Code giao diện mới có cần train lại không?

Không. Thay đổi HTML/CSS/JavaScript, API hiển thị hoặc tài liệu không làm thay đổi
trọng số `best.pt`, nên chỉ cần khởi động lại server và tải lại trang. Chỉ train lại
khi thay dataset/nhãn, kiến trúc, cấu hình huấn luyện hoặc muốn cải thiện chất
lượng detector.
