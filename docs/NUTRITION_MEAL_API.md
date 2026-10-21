# Nutrition & Meal Log API

Tài liệu này mô tả API ước tính BMI, RMR, TDEE, mục tiêu năng lượng mỗi ngày và
nhật ký bữa ăn của VNFood Nutrition Backend.

> Các kết quả chuyển hóa là ước tính cho người trưởng thành nhìn chung khỏe
> mạnh, không phải chẩn đoán hoặc đơn dinh dưỡng. API chủ động từ chối các hồ
> sơ không phù hợp thay vì trả về một con số có vẻ chính xác nhưng không an toàn.

## 1. Các endpoint hiện có

| Method | Endpoint | Chức năng |
| --- | --- | --- |
| `POST` | `/api/v1/nutrition/calculate` | Ước tính BMI/RMR/TDEE, kcal mục tiêu và cập nhật hồ sơ user |
| `POST` | `/api/v1/meals` | Tạo meal log bằng kcal từ catalog hoặc kcal nhập thủ công |
| `GET` | `/api/v1/meals/daily?date=YYYY-MM-DD` | Lấy bữa ăn, tổng kcal và kcal còn lại trong ngày |

Tất cả endpoint trên đều yêu cầu JWT access token:

```http
Authorization: Bearer <access_token>
```

`user_id` lấy từ JWT và không nhận từ request body. User không thể dùng body để
ghi hoặc đọc nhật ký của user khác.

## 2. Thành phần triển khai

- `backend/src/calcucalo/api/nutrition_meals.py`: schema request/response và router.
- `backend/src/calcucalo/services/metabolism.py`: công thức và các quy tắc an toàn.
- `backend/src/calcucalo/repositories/nutrition_tracking.py`: truy vấn PostgreSQL.
- `backend/migrations/0004_nutrition_meal_apis.sql`: bảng/index/constraint meal log.
- `backend/migrations/0005_harden_nutrition_calculations.sql`: trường phân biệt giới
  tính dùng cho công thức và nguồn kcal của meal log.
- `backend/tests/test_metabolism.py`: test công thức, ngưỡng BMI và biên an toàn.
- `backend/tests/test_nutrition_meals_api.py`: test contract API.
- `backend/scripts/smoke_test_nutrition_meals.py`: test JWT + API + Neon thật và tự cleanup.

## 3. Công thức và giới hạn

### 3.1 BMI

```text
BMI = weight_kg / (height_m ^ 2)
```

API trả đồng thời hai cách phân loại:

| BMI | `bmi_category_general` | `bmi_category_asian` |
| ---: | --- | --- |
| `< 18.5` | `underweight` | `underweight` |
| `18.5–22.9` | `healthy_weight` | `healthy_weight` |
| `23.0–24.9` | `healthy_weight` | `overweight` |
| `25.0–27.4` | `overweight` | `overweight` |
| `27.5–29.9` | `overweight` | `obesity` |
| `>= 30` | `obesity` | `obesity` |

Phân loại BMI chỉ là công cụ sàng lọc, không tự nó chẩn đoán sức khỏe hoặc tỷ lệ
mỡ cơ thể.

### 3.2 RMR — Mifflin–St Jeor

```text
Male:   RMR = 10 × weight_kg + 6.25 × height_cm - 5 × age + 5
Female: RMR = 10 × weight_kg + 6.25 × height_cm - 5 × age - 161
```

Output dùng tên `estimated_rmr_kcal_per_day`, không gọi là BMR, vì Mifflin–St
Jeor được xây dựng để ước tính năng lượng tiêu hao lúc nghỉ. Giá trị được làm
tròn đến kcal nguyên để tránh tạo cảm giác chính xác giả.

### 3.3 TDEE và mức vận động

```text
estimated_tdee = estimated_rmr × activity_factor
```

| `activity_level` | Hướng dẫn chọn | Hệ số |
| --- | --- | ---: |
| `sedentary` | Chủ yếu ngồi, rất ít hoặc không tập có chủ đích | 1.2 |
| `light` | Vận động nhẹ khoảng 1–3 ngày/tuần | 1.375 |
| `moderate` | Vận động vừa khoảng 3–5 ngày/tuần | 1.55 |
| `active` | Vận động nặng khoảng 6–7 ngày/tuần | 1.725 |
| `very_active` | Lao động thể lực nặng hoặc tập nặng nhiều lần/ngày | 1.9 |

Các mức trên là quy ước gần đúng. Hai người chọn cùng một mức vẫn có thể có
TDEE thực tế khác nhau.

### 3.4 Mục tiêu và tốc độ

`goal_pace` chỉ dùng với `lose_weight` hoặc `gain_weight`:

| `goal` | `goal_pace` | Điều chỉnh yêu cầu |
| --- | --- | ---: |
| `lose_weight` | `gradual` hoặc bỏ trống | `-250 kcal/ngày` |
| `lose_weight` | `standard` | `-500 kcal/ngày` |
| `maintain_weight` | Phải bỏ trống | `0 kcal/ngày` |
| `gain_weight` | `gradual` hoặc bỏ trống | `+250 kcal/ngày` |
| `gain_weight` | `standard` | `+500 kcal/ngày` |

Khi giảm cân, API áp dụng sàn lập kế hoạch:

| `sex_for_equation` | Sàn target khi giảm cân |
| --- | ---: |
| `female` | `1200 kcal/ngày` |
| `male` | `1500 kcal/ngày` |

Nếu mức giảm được yêu cầu đi qua sàn, API giảm độ lớn của thâm hụt và trả
`target_was_safety_limited=true`. Nếu TDEE ước tính không còn đủ khoảng để tạo
thâm hụt phía trên sàn, API trả `422` thay vì đề xuất mức ăn không phù hợp.

API cũng không trả bất kỳ target nào dưới ngưỡng tuyệt đối `1000 kcal/ngày`.

### 3.5 Những hồ sơ API không hỗ trợ

Ba cờ sau mặc định là `false`. Frontend nên hỏi người dùng rõ ràng; nếu một cờ
là `true`, API trả `422` và không lưu kết quả:

- `pregnant_or_breastfeeding`
- `competitive_athlete`
- `metabolism_affecting_condition`

Trường cuối bao gồm bệnh lý hoặc thuốc có ảnh hưởng đáng kể đến chuyển hóa.
Các trường hợp này cần đánh giá chuyên môn hoặc công thức chuyên biệt.

Mifflin–St Jeor gốc nghiên cứu người 19–78 tuổi. API vẫn nhận người trưởng
thành từ 18–120 tuổi, nhưng thêm warning nếu tuổi ngoài khoảng nghiên cứu.

## 4. API tính dinh dưỡng

### Request

```http
POST /api/v1/nutrition/calculate
Content-Type: application/json
Authorization: Bearer <access_token>
```

```json
{
  "sex_for_equation": "male",
  "age": 30,
  "height_cm": 175,
  "weight_kg": 70,
  "activity_level": "moderate",
  "goal": "maintain_weight",
  "pregnant_or_breastfeeding": false,
  "competitive_athlete": false,
  "metabolism_affecting_condition": false
}
```

| Trường | Kiểu | Bắt buộc | Quy tắc |
| --- | --- | --- | --- |
| `sex_for_equation` | string | Có | `male` hoặc `female`; dùng chọn hằng số công thức |
| `age` | integer | Có | 18–120 |
| `height_cm` | number | Có | `>100` và `<=250` |
| `weight_kg` | number | Có | `>25` và `<=400` |
| `activity_level` | string | Có | Một trong năm mức ở trên |
| `goal` | string | Có | `lose_weight`, `maintain_weight`, `gain_weight` |
| `goal_pace` | string/null | Không | `gradual` hoặc `standard`; bỏ với maintain |
| `pregnant_or_breastfeeding` | boolean | Không | Mặc định `false`; `true` bị từ chối |
| `competitive_athlete` | boolean | Không | Mặc định `false`; `true` bị từ chối |
| `metabolism_affecting_condition` | boolean | Không | Mặc định `false`; `true` bị từ chối |

Tên input cũ `gender` vẫn được chấp nhận như alias để client cũ không hỏng, nhưng
client mới phải dùng `sex_for_equation`.

### Response `200 OK`

```json
{
  "user_id": 7,
  "sex_for_equation": "male",
  "age": 30,
  "height_cm": 175.0,
  "weight_kg": 70.0,
  "activity_level": "moderate",
  "goal": "maintain_weight",
  "bmi": 22.9,
  "bmi_category_general": "healthy_weight",
  "bmi_category_asian": "healthy_weight",
  "estimated_rmr_kcal_per_day": 1649.0,
  "activity_factor": 1.55,
  "estimated_tdee_kcal_per_day": 2556.0,
  "goal_pace": null,
  "requested_goal_adjustment_kcal": 0.0,
  "applied_goal_adjustment_kcal": 0.0,
  "minimum_target_kcal": 1000.0,
  "target_was_safety_limited": false,
  "target_kcal_per_day": 2556.0,
  "formula_name": "mifflin_st_jeor_1990",
  "is_estimate": true,
  "warnings": [
    "RMR and TDEE are estimates and may differ from measured energy expenditure.",
    "Recalculate after a meaningful weight or activity change."
  ]
}
```

Backend lưu `sex_for_equation`, tuổi, chiều cao, cân nặng, activity, goal, BMI,
TDEE và target vào `users`. Cột `gender` cũ vẫn được đồng bộ trong giai đoạn
tương thích ngược.

### Response an toàn `422`

API không lưu kết quả nếu:

- Chọn giảm cân khi BMI `<18.5`.
- Không thể tạo thâm hụt phía trên sàn an toàn.
- Kết quả năng lượng nằm ngoài phạm vi hỗ trợ.
- Hồ sơ thuộc một trong ba nhóm đặc biệt.
- `goal_pace` không phù hợp với `goal`.

Ví dụ:

```json
{
  "detail": {
    "code": "unsupported_nutrition_target",
    "message": "Weight-loss target is not available when BMI is below 18.5"
  }
}
```

## 5. API tạo Meal Log

### Chế độ catalog — backend tự tính kcal

Không gửi `total_calories`:

```json
{
  "dish_id": 27,
  "meal_type": "lunch",
  "quantity": 1.5,
  "consumed_at": "2026-10-21T12:30:00+07:00"
}
```

Backend tính kcal một khẩu phần từ database:

```text
catalog_calories_per_serving =
    SUM(ingredients.calories × dish_ingredients.quantity / 100)

total_calories = catalog_calories_per_serving × quantity
```

Trong đó `ingredients.calories` là kcal/100 g và
`dish_ingredients.quantity` là số gram nguyên liệu của một khẩu phần món.
Response có `calorie_source="dish_catalog"`.

Nếu món tồn tại nhưng chưa có dữ liệu nguyên liệu, API trả `422` và yêu cầu gửi
kcal thủ công.

### Chế độ thủ công

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

Khi có `total_calories`, backend giữ đúng giá trị client cung cấp và trả
`calorie_source="manual"`. Cách này dành cho kết quả đã được phân tích từ ảnh,
nhãn dinh dưỡng hoặc nhập tay. Nếu gửi cả `dish_id` và `total_calories`, chế độ
thủ công được ưu tiên nhưng response vẫn có thể trả kcal catalog để đối chiếu.

Nếu không gửi `dish_id`, bắt buộc phải gửi `total_calories`.

### Các trường request

| Trường | Kiểu | Bắt buộc | Ý nghĩa |
| --- | --- | --- | --- |
| `dish_id` | integer/null | Có điều kiện | ID trong `dishes`; `404` nếu không tồn tại |
| `meal_type` | string | Có | 1–50 ký tự |
| `quantity` | number | Không | Số khẩu phần, mặc định `1`, `>0`, `<=100` |
| `total_calories` | number/null | Có điều kiện | Kcal tổng thủ công, `0–20000` |
| `image_url` | string/null | Không | Tối đa 2048 ký tự |
| `consumed_at` | datetime/null | Không | Mặc định thời điểm hiện tại Asia/Bangkok |

Datetime có timezone được đổi sang Asia/Bangkok. Datetime không timezone được
hiểu là giờ địa phương Asia/Bangkok.

### Response `201 Created`

```json
{
  "id": 101,
  "user_id": 7,
  "dish_id": 27,
  "dish_name": "Cơm tấm",
  "meal_type": "lunch",
  "quantity": 1.5,
  "total_calories": 930.0,
  "calorie_source": "dish_catalog",
  "catalog_calories_per_serving": 620.0,
  "image_url": null,
  "consumed_at": "2026-10-21T12:30:00",
  "created_at": "2026-10-21T12:31:00",
  "updated_at": "2026-10-21T12:31:00"
}
```

## 6. API lấy bữa ăn theo ngày

```http
GET /api/v1/meals/daily?date=2026-10-21
Authorization: Bearer <access_token>
```

`date` không bắt buộc; nếu bỏ qua, backend dùng ngày hiện tại tại Asia/Bangkok.

```json
{
  "date": "2026-10-21",
  "timezone": "Asia/Bangkok",
  "meal_count": 1,
  "total_calories": 930.0,
  "target_kcal_per_day": 2556.0,
  "remaining_kcal": 1626.0,
  "calorie_source_counts": {
    "dish_catalog": 1,
    "manual": 0
  },
  "meals": []
}
```

`remaining_kcal = target_kcal_per_day - total_calories` và có thể âm. Nếu user
chưa tính mục tiêu dinh dưỡng, target và remaining là `null`.

`calorie_source_counts` giúp frontend phân biệt bao nhiêu meal được backend
tính từ catalog và bao nhiêu meal là số liệu thủ công.

## 7. Database và migration

```text
users
 ├── auth_refresh_tokens
 └── meal_logs
      └── dishes
           └── dish_ingredients
                └── ingredients
```

- Xóa user sẽ xóa meal log qua `ON DELETE CASCADE`.
- Xóa dish chỉ đặt `meal_logs.dish_id=NULL`; lịch sử bữa ăn vẫn còn.
- Meal catalog lưu cả `calorie_source` và kcal/khẩu phần tại thời điểm tạo để
  không bị thay đổi ngược nếu công thức món được cập nhật sau này.
- Migration `0004` và `0005` đều idempotent và không xóa dữ liệu nghiệp vụ.

Hai migration đã được áp dụng lên Neon dev. Với database khác, mở lần lượt các
file trong DBeaver và chạy toàn bộ script:

```text
backend/migrations/0004_nutrition_meal_apis.sql
backend/migrations/0005_harden_nutrition_calculations.sql
```

## 8. Chạy và test thủ công

Từ thư mục `backend/`:

```powershell
uvicorn calcucalo.api.app:app --reload --host 127.0.0.1 --port 8000
```

Mở Swagger:

```text
http://127.0.0.1:8000/docs
```

Thứ tự kiểm tra:

1. Register hoặc login tại `/api/v1/auth/*`.
2. Sao chép `access_token`.
3. Nhấn **Authorize** và nhập token.
4. Gọi `/api/v1/nutrition/calculate`.
5. Gọi `/api/v1/meals`, thử một lần có và một lần không có `total_calories`.
6. Gọi `/api/v1/meals/daily` để kiểm tra tổng và nguồn kcal.

Chi tiết JWT nằm tại [README JWT](README.md).

## 9. Automated test

Unit/API test không thay đổi Neon:

```powershell
python -m pytest tests/test_metabolism.py tests/test_nutrition_meals_api.py tests/test_auth.py -q
```

Smoke test dùng Neon thật, tạo user và meal tạm rồi tự xóa:

```powershell
python scripts/smoke_test_nutrition_meals.py
```

## 10. Mã phản hồi chính

| Status | Khi nào xảy ra |
| --- | --- |
| `200` | Tính toán hoặc lấy daily meals thành công |
| `201` | Tạo meal log thành công |
| `401` | Thiếu, sai hoặc hết hạn access token |
| `404` | User hoặc `dish_id` không tồn tại |
| `422` | Input sai, target không an toàn, hồ sơ không hỗ trợ hoặc thiếu nutrition catalog |
| `503` | Database tạm thời không truy cập được |

## 11. Tài liệu tham khảo

- Mifflin MD và cộng sự, *A new predictive equation for resting energy
  expenditure in healthy individuals* (1990):
  <https://pubmed.ncbi.nlm.nih.gov/2305711/>
- CDC, phân loại BMI người trưởng thành:
  <https://www.cdc.gov/bmi/adult-calculator/bmi-categories.html>
- CDC/WHO, các ngưỡng BMI dùng cho quần thể châu Á:
  <https://www.cdc.gov/mmwr/volumes/73/wr/mm7303a1.htm>
- NIDDK Body Weight Planner và cảnh báo intake dưới 1000 kcal/ngày:
  <https://www.niddk.nih.gov/bwp>
- NHLBI, hướng dẫn quản lý thừa cân và béo phì ở người trưởng thành:
  <https://www.nhlbi.nih.gov/sites/default/files/media/docs/obesity-evidence-review.pdf>
