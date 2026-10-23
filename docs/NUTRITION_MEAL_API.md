# Nutrition & Meal Log API

Tài liệu này mô tả API ước tính BMI, RMR, TDEE, mục tiêu năng lượng mỗi ngày và
nhật ký bữa ăn của VNFood Nutrition Backend.

> Các kết quả chuyển hóa là ước tính cho người trưởng thành nhìn chung khỏe
> mạnh, không phải chẩn đoán hoặc đơn dinh dưỡng. API chủ động từ chối các hồ
> sơ không phù hợp thay vì trả về một con số có vẻ chính xác nhưng không an toàn.

## 1. Các endpoint hiện có

| Method | Endpoint | Chức năng |
| --- | --- | --- |
| `POST` | `/api/v1/nutrition/calculate` | Ước tính BMI/RMR/TDEE, kcal mục tiêu, macros mục tiêu và cập nhật hồ sơ user |
| `POST` | `/api/v1/meals` | Tạo meal log bằng kcal/macros từ catalog hoặc nhập thủ công |
| `GET` | `/api/v1/meals/daily?date=YYYY-MM-DD` | Lấy bữa ăn, tổng calo & macros nạp vào và số còn lại trong ngày |

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

### 3.4 Mục tiêu, số cân mong muốn (`weight_change_kg`) và lộ trình thời gian

Người dùng có thể chọn:
1. **Mục tiêu (`goal`)**:
   - `lose_weight`: Giảm cân
   - `gain_weight`: Tăng cân
   - `maintain_weight`: Giữ dáng / duy trì cân nặng
2. **Số cân muốn giảm hoặc tăng (`weight_change_kg`)**:
   - Nhập số kg mong muốn (ví dụ muốn giảm 5 kg $\rightarrow$ `weight_change_kg: 5.0`).
   - Với `maintain_weight`, trường này bỏ trống hoặc gửi `0`.
3. **Tốc độ thực hiện (`goal_pace`)**:
   - `standard`: Điều chỉnh $\pm 500\text{ kcal/ngày}$, tương đương tốc độ an toàn $\approx 0.5\text{ kg/tuần}$ (`weekly_pace_kg: 0.5`).
   - `gradual` (hoặc bỏ trống khi giảm/tăng cân): Điều chỉnh $\pm 250\text{ kcal/ngày}$, tương đương tốc độ nhẹ nhàng $\approx 0.25\text{ kg/tuần}$ (`weekly_pace_kg: 0.25`).
   - Bắt buộc bỏ trống khi `goal` là `maintain_weight`.

#### Cơ chế tính toán thời gian và chỉ số mục tiêu:
- **Chuẩn y học năng lượng:** $1\text{ kg}$ khối lượng mỡ cơ thể tương đương khoảng $7.700\text{ kcal}$.
- **Tổng năng lượng cần thay đổi:**
  $$\text{Total Kcal} = \text{weight\_change\_kg} \times 7700\text{ kcal}$$
- **Thời gian dự kiến đạt mục tiêu:**
  $$\text{estimated\_days} = \frac{\text{Total Kcal}}{|\text{daily\_calorie\_adjustment}|}$$
  $$\text{estimated\_weeks} = \frac{\text{estimated\_days}}{7}$$
  $$\text{target\_date} = \text{Hôm nay} + \text{estimated\_days}\quad (\text{định dạng } YYYY-MM-DD)$$
- **Cân nặng và BMI đích:**
  - `target_weight_kg`: Cân nặng mục tiêu sau khi giảm/tăng.
  - `target_bmi`: Chỉ số BMI dự kiến khi đạt cân nặng mục tiêu.

#### Quy tắc an toàn bắt buộc:
1. **Chặn giảm cân quá đà gây suy dinh dưỡng:**
   - Nếu `goal == "lose_weight"`, API kiểm tra `target_bmi`. Nếu `target_bmi < 18.5` (ngưỡng nhẹ cân/suy dinh dưỡng) hoặc `target_weight_kg <= 20 kg`, API lập tức trả lỗi `422` kèm thông báo cảnh báo an toàn tiếng Việt.
2. **Sàn calo tối thiểu mỗi ngày:**
   - Nữ: không ăn dưới `1200 kcal/ngày`.
   - Nam: không ăn dưới `1500 kcal/ngày`.
   - Ngưỡng sàn tuyệt đối: không dưới `1000 kcal/ngày`.
   Nếu mức thâm hụt khiến calo chạm sàn, API sẽ tự động giới hạn thâm hụt, bật cờ `target_was_safety_limited = true` và tính toán lại số ngày dựa trên thâm hụt thực tế khả thi.

### 3.5 Phân bổ đa lượng mục tiêu (Macronutrients: Protein, Carb, Fat)

Từ mức calo mục tiêu mỗi ngày (`target_kcal_per_day`), backend tự động tính toán số gram đạm, tinh bột, chất béo khuyến nghị theo `goal` (quy đổi $1\text{g Pro} = 4\text{ kcal}$, $1\text{g Carb} = 4\text{ kcal}$, $1\text{g Fat} = 9\text{ kcal}$):

| Mục tiêu (`goal`) | Tỉ lệ năng lượng (Carb / Pro / Fat) | Ý nghĩa dinh dưỡng |
| --- | :---: | --- |
| `lose_weight` | **40% Carb / 35% Protein / 25% Fat** | Tăng đạm để hạn chế mất cơ, tạo cảm giác no lâu khi giảm mỡ |
| `maintain_weight` | **50% Carb / 25% Protein / 25% Fat** | Tỉ lệ cân bằng cho người duy trì cân nặng và sinh hoạt bình thường |
| `gain_weight` | **55% Carb / 25% Protein / 20% Fat** | Tăng tinh bột để cung cấp calo và nạp năng lượng tập luyện |

Frontend có thể dùng trực tiếp 3 giá trị `target_protein_g`, `target_carb_g`, `target_fat_g` để vẽ các thanh chỉ số mục tiêu dinh dưỡng.

### 3.6 Những hồ sơ API không hỗ trợ

Ba cờ sau mặc định là `false`. Frontend nên hỏi người dùng rõ ràng; nếu một cờ
là `true`, API trả `422` và không lưu kết quả:

- `pregnant_or_breastfeeding`
- `competitive_athlete`
- `metabolism_affecting_condition`

Trường cuối bao gồm bệnh lý hoặc thuốc có ảnh hưởng đáng kể đến chuyển hóa.
Các trường hợp này cần đánh giá chuyên môn hoặc công thức chuyên biệt.

Mifflin–St Jeor gốc nghiên cứu người 19–78 tuổi. API vẫn nhận người trưởng
thành từ 18–120 tuổi, nhưng thêm warning nếu tuổi ngoài khoảng nghiên cứu.

## 4. API tính dinh dưỡng và kế hoạch cân nặng

### Request

```http
POST /api/v1/nutrition/calculate
Content-Type: application/json
Authorization: Bearer <access_token>
```

#### Ví dụ Body: Người dùng muốn giảm 5 kg
```json
{
  "sex_for_equation": "male",
  "age": 30,
  "height_cm": 175,
  "weight_kg": 70,
  "activity_level": "moderate",
  "goal": "lose_weight",
  "weight_change_kg": 5.0,
  "goal_pace": "standard",
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
| `activity_level` | string | Có | Một trong năm mức ở trên (`sedentary`, `light`, `moderate`, `active`, `very_active`) |
| `goal` | string | Có | `lose_weight`, `maintain_weight`, `gain_weight` |
| `weight_change_kg` | number/null | Không | Số kg muốn giảm hoặc tăng (`0–100`). Bỏ qua hoặc `0` khi `maintain_weight` |
| `goal_pace` | string/null | Không | `gradual` hoặc `standard`; bắt buộc bỏ qua với `maintain_weight` |
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
  "goal": "lose_weight",
  "bmi": 22.9,
  "current_weight_kg": 70.0,
  "weight_change_kg": 5.0,
  "target_weight_kg": 65.0,
  "current_bmi": 22.9,
  "target_bmi": 21.2,
  "bmi_category_general": "healthy_weight",
  "bmi_category_asian": "healthy_weight",
  "estimated_rmr_kcal_per_day": 1649.0,
  "activity_factor": 1.55,
  "estimated_tdee_kcal_per_day": 2556.0,
  "goal_pace": "standard",
  "requested_goal_adjustment_kcal": -500.0,
  "applied_goal_adjustment_kcal": -500.0,
  "daily_calorie_adjustment": -500.0,
  "minimum_target_kcal": 1500.0,
  "target_was_safety_limited": false,
  "target_kcal_per_day": 2056.0,
  "target_protein_g": 179.9,
  "target_carb_g": 205.6,
  "target_fat_g": 57.1,
  "weekly_pace_kg": 0.5,
  "estimated_days": 77,
  "estimated_weeks": 11.0,
  "target_date": "2026-10-18",
  "summary_message": "Để giảm 5 kg an toàn, bạn nên nạp 2,056 kcal/ngày. Bạn dự kiến sẽ đạt 65 kg sau khoảng 11 tuần (vào ngày 18/10/2026).",
  "formula_name": "mifflin_st_jeor_1990",
  "is_estimate": true,
  "warnings": [
    "RMR and TDEE are estimates and may differ from measured energy expenditure.",
    "Recalculate after a meaningful weight or activity change."
  ]
}
```

#### Hướng dẫn hiển thị kết quả cho Frontend (FE Checklist):
1. **Thông tin cân nặng & BMI:**
   - Cân nặng hiện tại: `current_weight_kg` kg (BMI: `current_bmi`).
   - Cân nặng đích: `target_weight_kg` kg (BMI dự kiến: `target_bmi`).
   - Thể trạng hiện tại: `bmi_category_asian` (Chuẩn người châu Á: `<18.5` thiếu cân, `18.5-22.9` bình thường, `23.0-27.4` thừa cân, `>=27.5` béo phì).
2. **Kế hoạch calo & macros mỗi ngày:**
   - Năng lượng nạp vào: `target_kcal_per_day` kcal/ngày (được điều chỉnh `daily_calorie_adjustment` kcal so với TDEE).
   - Macros mục tiêu: Đạm `target_protein_g` g, Tinh bột `target_carb_g` g, Chất béo `target_fat_g` g.
3. **Lộ trình và thời gian dự kiến:**
   - Tốc độ: `weekly_pace_kg` kg/tuần (thường là 0.5 kg/tuần với standard, 0.25 kg/tuần với gradual).
   - Thời gian cần thiết: `estimated_days` ngày ($\approx$ `estimated_weeks` tuần).
   - Ngày dự kiến hoàn thành: `target_date` (hiển thị cho user dạng ngày/tháng/năm).
4. **Lời khuyên tổng quan:**
   - Frontend có thể in thẳng `summary_message` lên banner/thẻ thông báo kế hoạch.

Backend lưu các chỉ số cơ bản vào bảng `users`.

### Response an toàn `422`

API không lưu kết quả và từ chối nếu:

- Chọn giảm cân khi BMI hiện tại `<18.5`.
- Mục tiêu giảm cân khiến BMI tụt xuống `<18.5` (nguy cơ suy dinh dưỡng).
- Cân nặng mục tiêu quá thấp ($\le 20\text{ kg}$).
- Không thể tạo thâm hụt phía trên sàn an toàn.
- Kết quả năng lượng nằm ngoài phạm vi hỗ trợ.
- Hồ sơ thuộc một trong ba nhóm đặc biệt.
- `goal_pace` hoặc `weight_change_kg` không phù hợp với `goal` (ví dụ `maintain_weight` nhưng truyền `weight_change_kg > 0`).

Ví dụ lỗi do giảm cân quá mức an toàn:

```json
{
  "detail": {
    "code": "unsupported_nutrition_target",
    "message": "Mục tiêu giảm 10 kg sẽ khiến BMI đạt 16.3 (dưới ngưỡng an toàn 18.5)."
  }
}
```

## 5. API tạo Meal Log

### Chế độ catalog — backend tự tính kcal và macros

Không gửi `total_calories`:

```json
{
  "dish_id": 27,
  "meal_type": "lunch",
  "quantity": 1.5,
  "consumed_at": "2026-10-21T12:30:00+07:00"
}
```

Backend tính kcal và số gram protein, fat, carb một khẩu phần từ database nguyên liệu:

```text
catalog_calories_per_serving = SUM(ingredients.calories × dish_ingredients.quantity / 100)
catalog_protein_per_serving  = SUM(ingredients.protein  × dish_ingredients.quantity / 100)
catalog_fat_per_serving      = SUM(ingredients.fat      × dish_ingredients.quantity / 100)
catalog_carb_per_serving     = SUM(ingredients.carb     × dish_ingredients.quantity / 100)

total_calories = catalog_calories_per_serving × quantity
protein_g      = catalog_protein_per_serving  × quantity
fat_g          = catalog_fat_per_serving      × quantity
carb_g         = catalog_carb_per_serving     × quantity
```

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
  "protein_g": 25.0,
  "fat_g": 15.0,
  "carb_g": 85.0,
  "image_url": "https://example.com/meals/com-tam.jpg",
  "consumed_at": "2026-10-21T12:30:00+07:00"
}
```

Khi có `total_calories`, backend giữ đúng giá trị client cung cấp và trả
`calorie_source="manual"`. Cách này dành cho kết quả đã được phân tích từ ảnh (AI model),
nhãn dinh dưỡng hoặc nhập tay. Nếu gửi cả `dish_id` và `total_calories`, chế độ
thủ công được ưu tiên. Các trường `protein_g`, `fat_g`, `carb_g` là tùy chọn; nếu bỏ trống và có `dish_id`, backend sẽ tự động lấy từ catalog.

Nếu không gửi `dish_id`, bắt buộc phải gửi `total_calories`.

### Các trường request

| Trường | Kiểu | Bắt buộc | Ý nghĩa |
| --- | --- | --- | --- |
| `dish_id` | integer/null | Có điều kiện | ID trong `dishes`; `404` nếu không tồn tại |
| `meal_type` | string | Có | 1–50 ký tự (`breakfast`, `lunch`, `dinner`, `snack`...) |
| `quantity` | number | Không | Số khẩu phần, mặc định `1`, `>0`, `<=100` |
| `total_calories` | number/null | Có điều kiện | Kcal tổng thủ công, `0–20000` |
| `protein_g` | number/null | Không | Gram đạm, `0–1000`. Bỏ qua để backend tự tính theo catalog |
| `fat_g` | number/null | Không | Gram chất béo, `0–1000`. Bỏ qua để backend tự tính theo catalog |
| `carb_g` | number/null | Không | Gram tinh bột, `0–1000`. Bỏ qua để backend tự tính theo catalog |
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
  "protein_g": 37.5,
  "fat_g": 22.5,
  "carb_g": 127.5,
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

`date` không bắt buộc; nếu bỏ qua, backend dùng ngày hiện tại tại Asia/Bangkok (định dạng `YYYY-MM-DD`).

### Response `200 OK`

```json
{
  "date": "2026-10-21",
  "timezone": "Asia/Bangkok",
  "meal_count": 1,
  "total_calories": 930.0,
  "target_kcal_per_day": 2556.0,
  "remaining_kcal": 1626.0,
  "total_protein_g": 37.5,
  "total_fat_g": 22.5,
  "total_carb_g": 127.5,
  "target_protein_g": 159.8,
  "target_fat_g": 71.0,
  "target_carb_g": 319.5,
  "remaining_protein_g": 122.3,
  "remaining_fat_g": 48.5,
  "remaining_carb_g": 192.0,
  "calorie_source_counts": {
    "dish_catalog": 1,
    "manual": 0
  },
  "meals": [
    {
      "id": 101,
      "user_id": 7,
      "dish_id": 27,
      "dish_name": "Cơm tấm",
      "meal_type": "lunch",
      "quantity": 1.5,
      "total_calories": 930.0,
      "protein_g": 37.5,
      "fat_g": 22.5,
      "carb_g": 127.5,
      "calorie_source": "dish_catalog",
      "catalog_calories_per_serving": 620.0,
      "image_url": null,
      "consumed_at": "2026-10-21T12:30:00",
      "created_at": "2026-10-21T12:31:00",
      "updated_at": "2026-10-21T12:31:00"
    }
  ]
}
```

### Hướng dẫn hiển thị cho Frontend:
1. **Calo:**
   - Đã nạp: `total_calories`
   - Mục tiêu: `target_kcal_per_day`
   - Còn lại: `remaining_kcal = target_kcal_per_day - total_calories` (có thể âm nếu ăn vượt mục tiêu).
2. **Macros (Protein, Fat, Carb):**
   - Đã nạp: `total_protein_g`, `total_fat_g`, `total_carb_g`
   - Mục tiêu ngày: `target_protein_g`, `target_fat_g`, `target_carb_g`
   - Lượng còn lại: `remaining_protein_g`, `remaining_fat_g`, `remaining_carb_g` (có thể âm).
   - Tỉ lệ phần trăm tiến độ thanh bar: $\text{Progress} = \frac{\text{total}}{\text{target}} \times 100\%$.
3. Nếu người dùng chưa từng gọi API `/nutrition/calculate`, các trường `target_...` và `remaining_...` sẽ trả về `null`.
4. `calorie_source_counts` giúp frontend thống kê bao nhiêu meal được tính từ catalog và bao nhiêu meal là số liệu thủ công / AI.

## 7. Database và migration

```text
users
 ├── auth_refresh_tokens
 └── meal_logs (thêm protein_g, fat_g, carb_g)
      └── dishes
           └── dish_ingredients
                └── ingredients (calories, protein, fat, carb)
```

- Xóa user sẽ xóa meal log qua `ON DELETE CASCADE`.
- Xóa dish chỉ đặt `meal_logs.dish_id=NULL`; lịch sử bữa ăn vẫn còn.
- Meal catalog lưu cả `calorie_source` và kcal/khẩu phần tại thời điểm tạo để
  không bị thay đổi ngược nếu công thức món được cập nhật sau này.
- Migration `0004`, `0005`, `0006` đều idempotent và không xóa dữ liệu nghiệp vụ.

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
