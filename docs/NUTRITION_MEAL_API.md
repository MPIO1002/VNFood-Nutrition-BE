# Nutrition & Meal Log API

Tài liệu này mô tả API tính BMI/BMR/TDEE, mục tiêu năng lượng mỗi ngày và nhật ký bữa ăn của VNFood Nutrition Backend.

## 1. Trạng thái hiện tại

Backend cung cấp ba endpoint có JWT bảo vệ:

| Method | Endpoint | Chức năng |
| --- | --- | --- |
| `POST` | `/api/v1/nutrition/calculate` | Tính BMI, BMR, TDEE, kcal mục tiêu và cập nhật hồ sơ user |
| `POST` | `/api/v1/meals` | Tạo một meal log cho user đang đăng nhập |
| `GET` | `/api/v1/meals/daily?date=YYYY-MM-DD` | Lấy các bữa ăn và tổng kcal của một ngày |

Các thành phần chính:

- `backend/src/calcucalo/api/nutrition_meals.py`: request/response model và API router.
- `backend/src/calcucalo/services/metabolism.py`: công thức BMI/BMR/TDEE thuần, không phụ thuộc database.
- `backend/src/calcucalo/repositories/nutrition_tracking.py`: truy vấn bảng `users`, `meal_logs`, `dishes`.
- `backend/migrations/0004_nutrition_meal_apis.sql`: migration idempotent, không xóa dữ liệu.
- `backend/tests/test_metabolism.py`: unit test công thức.
- `backend/tests/test_nutrition_meals_api.py`: test contract API bằng repository giả.
- `backend/scripts/smoke_test_nutrition_meals.py`: smoke test end-to-end với Neon thật.

## 2. Xác thực

Tất cả endpoint trong tài liệu này yêu cầu access token:

```http
Authorization: Bearer <access_token>
```

`user_id` luôn lấy từ JWT. Client không được truyền `user_id`, nhờ đó không thể tạo hoặc đọc meal log của user khác.

## 3. Công thức

### BMI

```text
BMI = cân_nặng_kg / (chiều_cao_mét ^ 2)
```

Phân loại được trả về bằng mã ổn định:

| BMI | `bmi_category` |
| --- | --- |
| `< 18.5` | `underweight` |
| `18.5 - 24.9` | `normal` |
| `25.0 - 29.9` | `overweight` |
| `>= 30` | `obesity` |

### BMR — Mifflin–St Jeor

```text
Nam: BMR = 10 × weight_kg + 6.25 × height_cm - 5 × age + 5
Nữ:  BMR = 10 × weight_kg + 6.25 × height_cm - 5 × age - 161
```

### TDEE

```text
TDEE = BMR × hệ_số_vận_động
```

| `activity_level` | Ý nghĩa | Hệ số |
| --- | --- | ---: |
| `sedentary` | Ít hoặc không vận động | 1.2 |
| `light` | Vận động nhẹ | 1.375 |
| `moderate` | Vận động vừa | 1.55 |
| `active` | Vận động nhiều | 1.725 |
| `very_active` | Vận động rất nhiều | 1.9 |

### Mục tiêu kcal/ngày

| `goal` | Điều chỉnh từ TDEE |
| --- | ---: |
| `lose_weight` | `-500 kcal` |
| `maintain_weight` | `0 kcal` |
| `gain_weight` | `+500 kcal` |

Kết quả là ước tính phục vụ phần mềm theo dõi dinh dưỡng, không thay thế tư vấn y khoa.

## 4. Tính BMI/BMR/TDEE và kcal mục tiêu

### Request

```http
POST /api/v1/nutrition/calculate
Content-Type: application/json
Authorization: Bearer <access_token>
```

```json
{
  "gender": "male",
  "age": 30,
  "height_cm": 175,
  "weight_kg": 70,
  "activity_level": "moderate",
  "goal": "maintain_weight"
}
```

| Trường | Kiểu | Bắt buộc | Validation |
| --- | --- | --- | --- |
| `gender` | string | Có | `male` hoặc `female` |
| `age` | integer | Có | 18–120 |
| `height_cm` | number | Có | `> 100` và `<= 250` |
| `weight_kg` | number | Có | `> 25` và `<= 400` |
| `activity_level` | string | Có | Một trong năm mức ở bảng trên |
| `goal` | string | Có | `lose_weight`, `maintain_weight`, `gain_weight` |

### Response `200 OK`

```json
{
  "user_id": 7,
  "gender": "male",
  "age": 30,
  "height_cm": 175.0,
  "weight_kg": 70.0,
  "activity_level": "moderate",
  "goal": "maintain_weight",
  "bmi": 22.9,
  "bmi_category": "normal",
  "bmr_kcal_per_day": 1648.8,
  "activity_factor": 1.55,
  "tdee_kcal_per_day": 2555.6,
  "goal_adjustment_kcal": 0.0,
  "target_kcal_per_day": 2555.6
}
```

Sau khi tính, backend cập nhật các cột hồ sơ trong `users`: `gender`, `age`, `height`, `weight`, `activity_level`, `goal`, `bmi`, `tdee`, `target_calories`.

## 5. Tạo Meal Log

### Request

```http
POST /api/v1/meals
Content-Type: application/json
Authorization: Bearer <access_token>
```

```json
{
  "dish_id": 27,
  "meal_type": "lunch",
  "quantity": 1,
  "total_calories": 620,
  "image_url": "https://example.com/meals/com-tam.jpg",
  "consumed_at": "2026-10-21T12:30:00+07:00"
}
```

| Trường | Kiểu | Bắt buộc | Ý nghĩa |
| --- | --- | --- | --- |
| `dish_id` | integer/null | Không | ID trong `dishes`; trả `404` nếu ID không tồn tại |
| `meal_type` | string | Có | Tên bữa ăn, tối đa 50 ký tự |
| `quantity` | number | Không | Số khẩu phần, mặc định `1`, phải `> 0` |
| `total_calories` | number | Có | Tổng kcal của toàn bộ lượng đã ghi, không phải kcal mỗi khẩu phần |
| `image_url` | string/null | Không | URL ảnh, tối đa 2048 ký tự |
| `consumed_at` | datetime/null | Không | Thời điểm ăn; nếu thiếu dùng thời gian hiện tại tại Asia/Bangkok |

Datetime có timezone được đổi sang Asia/Bangkok trước khi lưu. Datetime không timezone được hiểu là giờ địa phương Asia/Bangkok.

### Response `201 Created`

```json
{
  "id": 101,
  "user_id": 7,
  "dish_id": 27,
  "dish_name": "Cơm tấm",
  "meal_type": "lunch",
  "quantity": 1.0,
  "total_calories": 620.0,
  "image_url": "https://example.com/meals/com-tam.jpg",
  "consumed_at": "2026-10-21T12:30:00",
  "created_at": "2026-10-21T12:31:00",
  "updated_at": "2026-10-21T12:31:00"
}
```

## 6. Lấy bữa ăn theo ngày

### Request

```http
GET /api/v1/meals/daily?date=2026-10-21
Authorization: Bearer <access_token>
```

`date` không bắt buộc. Nếu bỏ qua, backend dùng ngày hiện tại theo `Asia/Bangkok`.

### Response `200 OK`

```json
{
  "date": "2026-10-21",
  "timezone": "Asia/Bangkok",
  "meal_count": 1,
  "total_calories": 620.0,
  "target_kcal_per_day": 2555.6,
  "remaining_kcal": 1935.6,
  "meals": [
    {
      "id": 101,
      "user_id": 7,
      "dish_id": 27,
      "dish_name": "Cơm tấm",
      "meal_type": "lunch",
      "quantity": 1.0,
      "total_calories": 620.0,
      "image_url": null,
      "consumed_at": "2026-10-21T12:30:00",
      "created_at": "2026-10-21T12:31:00",
      "updated_at": "2026-10-21T12:31:00"
    }
  ]
}
```

`remaining_kcal = target_kcal_per_day - total_calories`. Giá trị có thể âm nếu tổng kcal đã vượt mục tiêu. Nếu user chưa gọi API tính dinh dưỡng, `target_kcal_per_day` và `remaining_kcal` là `null`.

## 7. Database

```text
users
 ├── auth_refresh_tokens
 └── meal_logs
      └── dishes (dish_id có thể null)
```

- Xóa user sẽ xóa meal log qua `ON DELETE CASCADE`.
- Xóa dish chỉ đặt `meal_logs.dish_id = NULL`, lịch sử bữa ăn vẫn còn.
- Index `(user_id, consumed_at)` hỗ trợ truy vấn bữa ăn theo ngày.
- Migration `0004` không xóa dữ liệu hiện có.

Migration này đã được áp dụng lên Neon của môi trường phát triển ngày
`2026-10-21`. Với database mới hoặc database của thành viên khác, mở
`backend/migrations/0004_nutrition_meal_apis.sql` trong DBeaver, chọn đúng
connection/database rồi chạy toàn bộ script. Có thể chạy lại an toàn vì các
thao tác tạo cột, bảng, index và constraint đều kiểm tra sự tồn tại trước.

## 8. Cài đặt và chạy

Từ thư mục `backend/`, sau khi cấu hình `.env`:

```powershell
uvicorn calcucalo.api.app:app --reload --host 127.0.0.1 --port 8000
```

Swagger UI:

```text
http://127.0.0.1:8000/docs
```

### Kiểm tra thủ công bằng Swagger

1. Gọi `POST /api/v1/auth/register` để tạo tài khoản test hoặc
   `POST /api/v1/auth/login` với tài khoản đã có.
2. Sao chép `access_token` trong response.
3. Nhấn **Authorize** ở đầu trang Swagger, nhập access token rồi xác nhận.
4. Gọi `POST /api/v1/nutrition/calculate` trước để lưu mục tiêu kcal.
5. Gọi `POST /api/v1/meals` để ghi một bữa ăn.
6. Gọi `GET /api/v1/meals/daily` với cùng ngày để đối chiếu tổng kcal và kcal
   còn lại.

Chi tiết register/login/refresh/logout nằm tại [README JWT](README.md).

### Kiểm tra thủ công bằng PowerShell

Ví dụ dưới đây dùng tài khoản đã đăng ký:

```powershell
$loginBody = @{
    email = "user@example.com"
    password = "your-password"
} | ConvertTo-Json

$login = Invoke-RestMethod `
    -Method Post `
    -Uri "http://127.0.0.1:8000/api/v1/auth/login" `
    -ContentType "application/json" `
    -Body $loginBody

$headers = @{ Authorization = "Bearer $($login.access_token)" }

$nutritionBody = @{
    gender = "male"
    age = 30
    height_cm = 175
    weight_kg = 70
    activity_level = "moderate"
    goal = "maintain_weight"
} | ConvertTo-Json

Invoke-RestMethod `
    -Method Post `
    -Uri "http://127.0.0.1:8000/api/v1/nutrition/calculate" `
    -Headers $headers `
    -ContentType "application/json" `
    -Body $nutritionBody

$mealBody = @{
    dish_id = 27
    meal_type = "lunch"
    quantity = 1
    total_calories = 620
    consumed_at = "2026-10-21T12:30:00+07:00"
} | ConvertTo-Json

Invoke-RestMethod `
    -Method Post `
    -Uri "http://127.0.0.1:8000/api/v1/meals" `
    -Headers $headers `
    -ContentType "application/json" `
    -Body $mealBody

Invoke-RestMethod `
    -Method Get `
    -Uri "http://127.0.0.1:8000/api/v1/meals/daily?date=2026-10-21" `
    -Headers $headers
```

## 9. Test

Unit/API test không thay đổi Neon:

```powershell
python -m pytest tests/test_metabolism.py tests/test_nutrition_meals_api.py -q
```

Smoke test dùng Neon thật, tạo user và meal log ngẫu nhiên rồi tự xóa:

```powershell
python scripts/smoke_test_nutrition_meals.py
```

## 10. Mã phản hồi chính

| Status | Khi nào xảy ra |
| --- | --- |
| `200` | Tính toán hoặc lấy daily meals thành công |
| `201` | Tạo meal log thành công |
| `401` | Thiếu/sai/hết hạn access token |
| `404` | User hoặc `dish_id` không tồn tại |
| `422` | Request sai kiểu, ngoài phạm vi hoặc thiếu trường |
| `503` | Database tạm thời không truy cập được |
