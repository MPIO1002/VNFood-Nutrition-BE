# Diary Photo-Grid API

Tài liệu này mô tả 2 API nhật ký bữa ăn theo lưới ảnh dùng cho màn hình **Nhật ký (Diary)** trong ứng dụng CaloViet.

> Hai API này chỉ trả dữ liệu **đọc** (GET). Việc tạo / sửa meal log dùng `POST /api/v1/meals`.

---

## 1. Tổng quan

| Method | Endpoint | Chức năng |
| --- | --- | --- |
| `GET` | `/api/v1/diary/weekly` | Lưới ảnh nhóm theo **tuần** trong khoảng ngày chỉ định |
| `GET` | `/api/v1/diary/monthly` | Lưới ảnh nhóm theo **tháng** trong khoảng ngày chỉ định |

Cả 2 endpoint yêu cầu JWT access token:

```http
Authorization: Bearer <access_token>
```

`user_id` lấy từ JWT — user không thể đọc nhật ký của user khác.

---

## 2. Thành phần triển khai

| File | Vai trò |
| --- | --- |
| `backend/src/calcucalo/api/diary.py` | Schema request/response và router |
| `backend/src/calcucalo/repositories/diary.py` | Query PostgreSQL (`meal_logs`) |
| `backend/tests/test_diary.py` | Test cases |

---

## 3. Quy tắc chung

### 3.1 Tham số ngày (`start_date`, `end_date`)

- Định dạng **YYYY-MM-DD** (ISO 8601).
- `end_date` phải >= `start_date`.
- Khoảng tối đa **366 ngày** (guard cho query lớn).
- Cả 2 đều **bắt buộc**.

Frontend thường tính:
```
# Tab Tuần — hiển thị tuần hiện tại
start_date = monday_of_current_week     # ví dụ 2026-11-02
end_date   = sunday_of_current_week     # ví dụ 2026-11-08

# Tab Tháng — hiển thị 2 tháng gần nhất
start_date = first_day_of_2_months_ago  # ví dụ 2026-10-01
end_date   = today                      # ví dụ 2026-11-04
```

### 3.2 Ngày không có bữa ăn

Ngày **không có bữa ăn** sẽ **không xuất hiện** trong mảng `days[]`.
Frontend dùng `date` trong mỗi phần tử để vẽ vị trí trên lưới.

> Lý do: returning `has_meals: false` không có giá trị — frontend chỉ cần render ô ảnh cho ngày CÓ bữa ăn.

### 3.3 `representative_image_url`

Là ảnh của bữa ăn **gần nhất trong ngày** có `image_url IS NOT NULL`.
Có thể là `null` nếu không có bữa ăn nào trong ngày đó có ảnh.

### 3.4 `avg_daily_kcal`

Tính trung bình **chỉ trên các ngày có bữa ăn**, không chia đều toàn kỳ.

### 3.5 Summary footer

| Trường | Ý nghĩa |
| --- | --- |
| `streak_days` | Số ngày liên tiếp có log tính từ **hôm nay** về trước (all-time, không giới hạn trong khoảng) |
| `total_meals_logged` | Tổng bữa ăn từ trước đến nay — dùng hiển thị "Locket Calo" |
| `avg_daily_kcal` | Trung bình kcal/ngày trong khoảng [start, end], chỉ tính ngày có ăn |
| `avg_daily_protein_g` | Trung bình protein (g) tương tự |
| `avg_daily_fat_g` | Trung bình chất béo (g) tương tự |
| `avg_daily_carb_g` | Trung bình tinh bột (g) tương tự |

---

## 4. GET /api/v1/diary/weekly

### Request

```http
GET /api/v1/diary/weekly?start_date=2026-10-27&end_date=2026-11-02
Authorization: Bearer <access_token>
```

| Param | Kiểu | Bắt buộc | Mô tả |
| --- | --- | --- | --- |
| `start_date` | string (YYYY-MM-DD) | Có | Ngày bắt đầu |
| `end_date` | string (YYYY-MM-DD) | Có | Ngày kết thúc (inclusive) |

### Cách nhóm tuần

- Tuần bắt đầu từ **Thứ Hai** (Mon-Sun theo chuẩn ISO).
- Nếu `start_date` hoặc `end_date` không khớp đúng thứ Hai / Chủ Nhật, tuần biên sẽ hiển thị **ngày hiệu lực** (clamped vào khoảng yêu cầu).
- `week_label` dùng ngày hiệu lực: `"Tuần 27/10 – 01/11/2026"`.

Nhãn thứ trong tuần (`day_label`) theo tiếng Việt:

| Thứ | `day_label` |
| --- | --- |
| Thứ Hai | T2 |
| Thứ Ba | T3 |
| Thứ Tư | T4 |
| Thứ Năm | T5 |
| Thứ Sáu | T6 |
| Thứ Bảy | T7 |
| Chủ Nhật | CN |

### Response `200 OK`

```json
{
  "user_id": 7,
  "start_date": "2026-10-27",
  "end_date": "2026-11-02",
  "streak_days": 14,
  "total_meals_logged": 301,
  "avg_daily_kcal": 1890.5,
  "avg_daily_protein_g": 124.0,
  "avg_daily_fat_g": 52.0,
  "avg_daily_carb_g": 218.0,
  "data": [
    {
      "week_label": "Tuần 27/10 – 01/11/2026",
      "week_start": "2026-10-27",
      "week_end": "2026-11-01",
      "days_logged": 3,
      "total_kcal": 5600.0,
      "avg_daily_kcal": 1866.7,
      "days": [
        {
          "date": "2026-10-28",
          "meal_count": 2,
          "total_kcal": 1850.0,
          "representative_image_url": "https://res.cloudinary.com/.../meal.jpg",
          "day_label": "T3"
        },
        {
          "date": "2026-10-30",
          "meal_count": 3,
          "total_kcal": 2050.0,
          "representative_image_url": null,
          "day_label": "T6"
        },
        {
          "date": "2026-11-01",
          "meal_count": 1,
          "total_kcal": 1700.0,
          "representative_image_url": "https://res.cloudinary.com/.../meal2.jpg",
          "day_label": "CN"
        }
      ]
    },
    {
      "week_label": "Tuần 02/11 – 02/11/2026",
      "week_start": "2026-11-02",
      "week_end": "2026-11-02",
      "days_logged": 0,
      "total_kcal": 0.0,
      "avg_daily_kcal": 0.0,
      "days": []
    }
  ]
}
```

#### Hướng dẫn render lưới tuần cho Frontend

1. Lặp qua `data[]` — mỗi phần tử là 1 tuần.
2. Với mỗi tuần, tạo lưới 7 ô (T2–CN).
3. Với mỗi ô, tìm phần tử trong `days[]` có `date` khớp.
   - Nếu tìm thấy: hiển thị `representative_image_url` (hoặc icon placeholder nếu null).
   - Nếu không tìm thấy: ô trống / mờ.
4. Header tuần: `week_label` + `avg_daily_kcal` kcal/ngày.

---

## 5. GET /api/v1/diary/monthly

### Request

```http
GET /api/v1/diary/monthly?start_date=2026-10-01&end_date=2026-11-04
Authorization: Bearer <access_token>
```

| Param | Kiểu | Bắt buộc | Mô tả |
| --- | --- | --- | --- |
| `start_date` | string (YYYY-MM-DD) | Có | Ngày bắt đầu |
| `end_date` | string (YYYY-MM-DD) | Có | Ngày kết thúc (inclusive) |

### Cách nhóm tháng

- Nhóm theo **tháng lịch** (calendar month).
- `days_in_month`: tổng số ngày trong tháng (28/29/30/31) — dùng để vẽ lưới đúng vị trí.
- Tháng biên: nếu `start_date` không phải ngày 1, chỉ trả dữ liệu từ `start_date` trở đi trong tháng đó.
- `month_label`: dạng `"tháng 10 2026"`.

### Response `200 OK`

```json
{
  "user_id": 7,
  "start_date": "2026-10-01",
  "end_date": "2026-11-04",
  "streak_days": 14,
  "total_meals_logged": 301,
  "avg_daily_kcal": 1890.5,
  "avg_daily_protein_g": 124.0,
  "avg_daily_fat_g": 52.0,
  "avg_daily_carb_g": 218.0,
  "data": [
    {
      "month_label": "tháng 10 2026",
      "month_start": "2026-10-01",
      "days_in_month": 31,
      "days_logged": 18,
      "total_kcal": 33480.0,
      "avg_daily_kcal": 1860.0,
      "days": [
        {
          "date": "2026-10-01",
          "meal_count": 3,
          "total_kcal": 1920.0,
          "representative_image_url": "https://res.cloudinary.com/.../meal.jpg"
        },
        {
          "date": "2026-10-05",
          "meal_count": 2,
          "total_kcal": 1750.0,
          "representative_image_url": null
        }
      ]
    },
    {
      "month_label": "tháng 11 2026",
      "month_start": "2026-11-01",
      "days_in_month": 30,
      "days_logged": 4,
      "total_kcal": 7560.0,
      "avg_daily_kcal": 1890.0,
      "days": [
        {
          "date": "2026-11-01",
          "meal_count": 2,
          "total_kcal": 1800.0,
          "representative_image_url": "https://res.cloudinary.com/.../meal3.jpg"
        }
      ]
    }
  ]
}
```

#### Hướng dẫn render lưới tháng cho Frontend

1. Lặp qua `data[]` — mỗi phần tử là 1 tháng.
2. Dùng `days_in_month` để tạo lưới đủ ô (28–31 ô).
3. Với mỗi ô ngày, tìm phần tử trong `days[]` có `date` khớp.
   - Tìm thấy: hiển thị `representative_image_url`.
   - Không tìm thấy: ô trống.
4. Header tháng: `month_label` + `avg_daily_kcal` kcal/ngày (hoặc TDEE từ profile).

---

## 6. Response lỗi

| HTTP | Tình huống |
| --- | --- |
| `401 Unauthorized` | Thiếu hoặc hết hạn JWT |
| `422 Unprocessable Entity` | `start_date`/`end_date` sai định dạng; `end_date < start_date`; khoảng > 366 ngày |
| `503 Service Unavailable` | Lỗi kết nối database |

Ví dụ `422` khi format sai:
```json
{
  "detail": "'start_date' phải có dạng YYYY-MM-DD, nhận được: '04-11-2026'"
}
```

Ví dụ `422` khi khoảng đảo ngược:
```json
{
  "detail": "'end_date' phải >= 'start_date'."
}
```

---

## 7. Ví dụ gọi API (cURL)

### Weekly — tuần hiện tại

```bash
curl -X GET \
  "https://api.example.com/api/v1/diary/weekly?start_date=2026-11-03&end_date=2026-11-09" \
  -H "Authorization: Bearer <token>"
```

### Monthly — 2 tháng gần nhất

```bash
curl -X GET \
  "https://api.example.com/api/v1/diary/monthly?start_date=2026-10-01&end_date=2026-11-04" \
  -H "Authorization: Bearer <token>"
```

