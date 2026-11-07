# Progress Stats API

Tài liệu này mô tả 2 API thống kê tiến độ ăn uống theo **tuần** và **tháng** dùng cho tab **Phân tích (Analysis)** trong ứng dụng CaloViet.

> Hai API này tổng hợp dữ liệu từ `meal_logs` — chỉ đọc (GET). Meal log được tạo qua `POST /api/v1/meals`.

---

## 1. Tổng quan

| Method | Endpoint | Chức năng |
| --- | --- | --- |
| `GET` | `/api/v1/progress/weekly` | Thống kê calo & macro nhóm theo **tuần** trong khoảng ngày |
| `GET` | `/api/v1/progress/monthly` | Thống kê calo & macro nhóm theo **tháng** trong khoảng ngày |

Cả 2 endpoint yêu cầu JWT access token:

```http
Authorization: Bearer <access_token>
```

---

## 2. Thành phần triển khai

| File | Vai trò |
| --- | --- |
| `backend/src/calcucalo/api/profile_progress.py` | Schema request/response và router |
| `backend/src/calcucalo/repositories/user_profile.py` | Query `meal_logs` và tính toán |

---

## 3. Quy tắc chung

### 3.1 Tham số ngày (`start_date`, `end_date`)

- Định dạng **YYYY-MM-DD** (ISO 8601).
- `end_date` phải >= `start_date`.
- Khoảng tối đa **366 ngày**.
- Cả 2 đều **bắt buộc**.

Frontend thường tính:
```
# Tab Tuần — tuần hiện tại
start_date = monday_of_current_week     # ví dụ 2026-11-02
end_date   = today                      # ví dụ 2026-11-07

# Tab Tháng — 3 tháng gần nhất
start_date = first_day_of_3_months_ago  # ví dụ 2026-09-01
end_date   = today                      # ví dụ 2026-11-07
```

### 3.2 Nhóm tuần (Weekly)

- Tuần bắt đầu từ **Thứ Hai** (Mon–Sun theo chuẩn ISO).
- Tuần biên (không bắt đầu từ Mon hoặc không kết thúc Sun) vẫn được trả về — `week_start` / `week_end` clamped vào khoảng yêu cầu.
- Tuần **không có bữa ăn** vẫn được trả về với tất cả giá trị là 0.

### 3.3 Nhóm tháng (Monthly)

- Nhóm theo **tháng lịch** (calendar month).
- `days_in_month`: tổng số ngày trong tháng (28/29/30/31) — dùng để tính `target_monthly_kcal`.
- Tháng biên: nếu `start_date` không phải ngày 1, tháng đó chỉ tính từ `start_date` trở đi.

### 3.4 `adherence_pct`

Tỷ lệ % hoàn thành so với mục tiêu calo của user (lưu trong `users.target_calories`).

```
adherence_pct = (total_calories / target_weekly_kcal) * 100
```

Giới hạn tối đa là 200% để tránh giá trị bất thường. Trả về `null` nếu user chưa tính TDEE.

### 3.5 `avg_daily_calories`

Tính trên **số ngày CÓ bữa ăn** (`days_logged`), không chia đều toàn kỳ.

---

## 4. GET /api/v1/progress/weekly

### Request

```http
GET /api/v1/progress/weekly?start_date=2026-10-27&end_date=2026-11-07
Authorization: Bearer <access_token>
```

| Param | Kiểu | Bắt buộc | Mô tả |
| --- | --- | --- | --- |
| `start_date` | string (YYYY-MM-DD) | Có | Ngày bắt đầu (inclusive) |
| `end_date` | string (YYYY-MM-DD) | Có | Ngày kết thúc (inclusive) |

### Response `200 OK`

```json
{
  "user_id": 7,
  "start_date": "2026-10-27",
  "end_date": "2026-11-07",
  "data": [
    {
      "week_label": "27/10 – 02/11/2026",
      "week_start": "2026-10-27",
      "week_end": "2026-11-02",
      "meal_count": 14,
      "days_logged": 5,
      "total_calories": 9280.0,
      "avg_daily_calories": 1856.0,
      "target_weekly_kcal": 14420.0,
      "adherence_pct": 64.4,
      "total_protein_g": 480.5,
      "total_fat_g": 230.0,
      "total_carb_g": 1150.0
    },
    {
      "week_label": "03/11 – 07/11/2026",
      "week_start": "2026-11-03",
      "week_end": "2026-11-07",
      "meal_count": 10,
      "days_logged": 4,
      "total_calories": 7420.0,
      "avg_daily_calories": 1855.0,
      "target_weekly_kcal": 14420.0,
      "adherence_pct": 51.5,
      "total_protein_g": 350.0,
      "total_fat_g": 190.0,
      "total_carb_g": 870.0
    }
  ]
}
```

#### Giải thích trường response

| Trường | Ý nghĩa |
| --- | --- |
| `week_label` | Nhãn tuần dạng "DD/MM – DD/MM/YYYY" (ngày hiệu lực) |
| `week_start` | Ngày bắt đầu hiệu lực của tuần (ISO date) |
| `week_end` | Ngày kết thúc hiệu lực của tuần (ISO date) |
| `meal_count` | Số bữa ăn đã log trong tuần |
| `days_logged` | Số ngày (trong tuần) có ít nhất 1 bữa ăn |
| `total_calories` | Tổng calo nạp vào trong tuần |
| `avg_daily_calories` | Trung bình calo/ngày (chỉ tính ngày CÓ ăn) |
| `target_weekly_kcal` | Mục tiêu calo 7 ngày = `target_calories × 7`; `null` nếu chưa tính TDEE |
| `adherence_pct` | % hoàn thành mục tiêu (tối đa 200%); `null` nếu chưa có target |
| `total_protein_g` | Tổng protein (g) |
| `total_fat_g` | Tổng chất béo (g) |
| `total_carb_g` | Tổng tinh bột (g) |

---

## 5. GET /api/v1/progress/monthly

### Request

```http
GET /api/v1/progress/monthly?start_date=2026-09-01&end_date=2026-11-07
Authorization: Bearer <access_token>
```

| Param | Kiểu | Bắt buộc | Mô tả |
| --- | --- | --- | --- |
| `start_date` | string (YYYY-MM-DD) | Có | Ngày bắt đầu (inclusive) |
| `end_date` | string (YYYY-MM-DD) | Có | Ngày kết thúc (inclusive) |

### Response `200 OK`

```json
{
  "user_id": 7,
  "start_date": "2026-09-01",
  "end_date": "2026-11-07",
  "data": [
    {
      "month_label": "2026-09",
      "month_start": "2026-09-01",
      "days_in_month": 30,
      "meal_count": 52,
      "days_logged": 20,
      "total_calories": 37400.0,
      "avg_daily_calories": 1870.0,
      "target_monthly_kcal": 61800.0,
      "adherence_pct": 60.5,
      "total_protein_g": 1650.0,
      "total_fat_g": 820.0,
      "total_carb_g": 4280.0
    },
    {
      "month_label": "2026-10",
      "month_start": "2026-10-01",
      "days_in_month": 31,
      "meal_count": 68,
      "days_logged": 25,
      "total_calories": 46500.0,
      "avg_daily_calories": 1860.0,
      "target_monthly_kcal": 63860.0,
      "adherence_pct": 72.8,
      "total_protein_g": 2100.0,
      "total_fat_g": 1050.0,
      "total_carb_g": 5520.0
    },
    {
      "month_label": "2026-11",
      "month_start": "2026-11-01",
      "days_in_month": 30,
      "meal_count": 18,
      "days_logged": 7,
      "total_calories": 12950.0,
      "avg_daily_calories": 1850.0,
      "target_monthly_kcal": 61800.0,
      "adherence_pct": 20.9,
      "total_protein_g": 580.0,
      "total_fat_g": 290.0,
      "total_carb_g": 1540.0
    }
  ]
}
```

#### Giải thích trường response

| Trường | Ý nghĩa |
| --- | --- |
| `month_label` | Nhãn tháng dạng "YYYY-MM" |
| `month_start` | Ngày đầu tiên hiệu lực trong tháng (ISO date) |
| `days_in_month` | Tổng số ngày trong tháng (28–31) — dùng tính `target_monthly_kcal` |
| `meal_count` | Số bữa ăn đã log trong tháng |
| `days_logged` | Số ngày có ít nhất 1 bữa ăn |
| `total_calories` | Tổng calo nạp vào trong tháng |
| `avg_daily_calories` | Trung bình calo/ngày (chỉ tính ngày CÓ ăn) |
| `target_monthly_kcal` | Mục tiêu calo = `target_calories × days_in_month`; `null` nếu chưa tính TDEE |
| `adherence_pct` | % hoàn thành mục tiêu (tối đa 200%); `null` nếu chưa có target |
| `total_protein_g` | Tổng protein (g) |
| `total_fat_g` | Tổng chất béo (g) |
| `total_carb_g` | Tổng tinh bột (g) |

---

## 6. Response lỗi

| HTTP | Tình huống |
| --- | --- |
| `401 Unauthorized` | Thiếu hoặc hết hạn JWT |
| `404 Not Found` | User không tồn tại trong DB |
| `422 Unprocessable Entity` | `start_date`/`end_date` sai định dạng; `end_date < start_date`; khoảng > 366 ngày |
| `503 Service Unavailable` | Lỗi kết nối database |

Ví dụ `422`:
```json
{ "detail": "'end_date' must be >= 'start_date'." }
```

---

## 7. Ví dụ gọi API (cURL)

### Weekly — 2 tuần gần nhất

```bash
curl -X GET \
  "https://api.example.com/api/v1/progress/weekly?start_date=2026-10-26&end_date=2026-11-07" \
  -H "Authorization: Bearer <token>"
```

### Monthly — 3 tháng gần nhất

```bash
curl -X GET \
  "https://api.example.com/api/v1/progress/monthly?start_date=2026-09-01&end_date=2026-11-07" \
  -H "Authorization: Bearer <token>"
```

