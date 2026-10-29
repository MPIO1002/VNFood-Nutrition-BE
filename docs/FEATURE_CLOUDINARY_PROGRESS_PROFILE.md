# 📋 Changelog – branch `feature/cloudinary-progress-profile`

> **Commit:** `297eecc`  
> **Base branch:** `main`  
> **Ngày:** 28-10-2026  
> **Test:** 16 pass / 0 fail (suite mới); tổng suite cũ không bị ảnh hưởng

---

## ✅ Đã làm được gì

### 1. Tích hợp Cloudinary – Chuyển ảnh upload thành URL

**File mới:** [`cloudinary_upload.py`](file:///d:/Nam5_HK1/Seminar/VNFood-Nutrition-BE/backend/src/calcucalo/services/cloudinary_upload.py)

- Tự build **signed upload** đến Cloudinary API (không phụ thuộc SDK nặng)
- Dùng `httpx` để POST multipart lên `https://api.cloudinary.com/v1_1/{cloud_name}/image/upload`
- Trả về `secure_url` (HTTPS)
- `cloudinary_is_configured()` – kiểm tra env vars có đủ không (dùng trong `/health`)

**Endpoint mới:**

```
POST /api/v1/upload/image
Authorization: Bearer <access_token>
Content-Type: multipart/form-data
```

| Field | Loại | Giới hạn |
|---|---|---|
| `image` | file | JPEG, PNG, WebP, GIF, HEIC/HEIF; tối đa **10 MB** |

**Response 201:**
```json
{
  "url": "https://res.cloudinary.com/yourcloud/image/upload/calcucalo/photo_1234.jpg",
  "filename": "photo.jpg",
  "size_bytes": 204800,
  "content_type": "image/jpeg"
}
```

**Cấu hình `.env`:**
```dotenv
CLOUDINARY_CLOUD_NAME=your-cloud-name
CLOUDINARY_API_KEY=your-api-key
CLOUDINARY_API_SECRET=your-api-secret
# CLOUDINARY_FOLDER=calcucalo   # tùy chọn, default: calcucalo
```

---

### 2. API Thống kê Tiến trình (Progress Stats)

**File mới:** [`user_profile.py`](file:///d:/Nam5_HK1/Seminar/VNFood-Nutrition-BE/backend/src/calcucalo/repositories/user_profile.py)  
**File mới:** [`profile_progress.py`](file:///d:/Nam5_HK1/Seminar/VNFood-Nutrition-BE/backend/src/calcucalo/api/profile_progress.py)

#### `GET /api/v1/progress/weekly`

```
Authorization: Bearer <access_token>
?weeks=4    # 1–52, default 4
```

Mỗi bucket tuần trả về:

| Field | Ý nghĩa |
|---|---|
| `week_label` | `"2026-10-19 / 2026-10-25"` |
| `week_start` / `week_end` | ISO date |
| `meal_count` | Số lần ăn trong tuần |
| `days_logged` | Số ngày có log |
| `total_calories` | Tổng kcal tuần |
| `avg_daily_calories` | Trung bình kcal/ngày có log |
| `target_weekly_kcal` | `target_calories × 7` |
| `adherence_pct` | % hoàn thành mục tiêu (max 200%) |
| `total_protein_g` / `total_fat_g` / `total_carb_g` | Tổng macro tuần |

Tuần không có data → hiện `0` (không bị gap).

#### `GET /api/v1/progress/monthly`

```
Authorization: Bearer <access_token>
?months=3   # 1–24, default 3
```

Tương tự weekly nhưng theo tháng:
- `month_label`: `"2026-10"`
- `days_in_month`: số ngày trong tháng đó
- `target_monthly_kcal`: `target_calories × days_in_month`

---

### 3. API User Profile + Cập nhật cân nặng

#### `GET /api/v1/profile`
Trả toàn bộ profile của user đang đăng nhập (bao gồm cả `avatar_url`, `weight`, `bmi`, `tdee`, `target_calories`...).

#### `PATCH /api/v1/profile`
Cập nhật `full_name` và/hoặc `avatar_url`.

```json
{
  "full_name": "Nguyen Van A",
  "avatar_url": "https://res.cloudinary.com/.../avatar.jpg"
}
```

**Workflow đổi avatar:**
1. `POST /api/v1/upload/image` → nhận `url`
2. `PATCH /api/v1/profile` với `{ "avatar_url": url }`

#### `POST /api/v1/profile/weight`
Ghi nhận cân nặng mới → cập nhật `users.weight` và tạo 1 dòng trong `weight_logs`.

```json
{
  "weight_kg": 71.2,
  "recorded_at": "2026-10-28T07:30:00+07:00",
  "note": "Sáng sau ngủ dậy"
}
```

#### `GET /api/v1/profile/weight/history`
```
?limit=30   # 1–200, default 30
```
Trả danh sách lịch sử cân nặng mới nhất → cũ nhất.

---

## 📁 Files đã tạo / chỉnh sửa

| File | Thao tác | Mô tả |
|---|---|---|
| [`services/cloudinary_upload.py`](file:///d:/Nam5_HK1/Seminar/VNFood-Nutrition-BE/backend/src/calcucalo/services/cloudinary_upload.py) | Tạo mới | Cloudinary signed upload service |
| [`repositories/user_profile.py`](file:///d:/Nam5_HK1/Seminar/VNFood-Nutrition-BE/backend/src/calcucalo/repositories/user_profile.py) | Tạo mới | Profile CRUD, weight log, weekly/monthly stats |
| [`api/profile_progress.py`](file:///d:/Nam5_HK1/Seminar/VNFood-Nutrition-BE/backend/src/calcucalo/api/profile_progress.py) | Tạo mới | 7 API endpoints |
| [`api/app.py`](file:///d:/Nam5_HK1/Seminar/VNFood-Nutrition-BE/backend/src/calcucalo/api/app.py) | Chỉnh sửa | Đăng ký router mới; `cloudinary_configured` vào `/health` |
| [`migrations/0007_weight_logs_avatar.sql`](file:///d:/Nam5_HK1/Seminar/VNFood-Nutrition-BE/backend/migrations/0007_weight_logs_avatar.sql) | Tạo mới | Tạo `weight_logs` table + `avatar_url` column cho `users` |
| [`backend/.env.example`](file:///d:/Nam5_HK1/Seminar/VNFood-Nutrition-BE/backend/.env.example) | Chỉnh sửa | Thêm template Cloudinary env vars |
| [`pyproject.toml`](file:///d:/Nam5_HK1/Seminar/VNFood-Nutrition-BE/backend/pyproject.toml) | Chỉnh sửa | Chuyển `httpx` vào core dependencies |
| [`tests/test_profile_progress.py`](file:///d:/Nam5_HK1/Seminar/VNFood-Nutrition-BE/backend/tests/test_profile_progress.py) | Tạo mới | 16 unit tests |

---

## ⚙️ Việc cần làm trước khi dùng

### Bước 1: Chạy migration
Mở Neon SQL Editor (hoặc DBeaver) và chạy file:
```
backend/migrations/0007_weight_logs_avatar.sql
```

### Bước 2: Điền Cloudinary credentials vào `backend/.env`
```dotenv
CLOUDINARY_CLOUD_NAME=your-cloud-name
CLOUDINARY_API_KEY=your-api-key
CLOUDINARY_API_SECRET=your-api-secret
```
> Tạo tài khoản free tại https://cloudinary.com → Dashboard → Copy API keys.

### Bước 3: Reinstall nếu cần
```powershell
cd backend
pip install -e ".[all]"
```

### Bước 4: Khởi động server
```powershell
uvicorn calcucalo.api.app:app --reload --host 127.0.0.1 --port 8000
```

Kiểm tra Cloudinary đã config chưa:
```
GET http://127.0.0.1:8000/health
# → "cloudinary_configured": true/false
```

---

## 📊 Tổng kết API mới (7 endpoints)

| Method | Endpoint | Auth | Chức năng |
|---|---|---|---|
| `POST` | `/api/v1/upload/image` | ✅ Access | Upload ảnh → Cloudinary URL |
| `GET` | `/api/v1/profile` | ✅ Access | Xem profile đầy đủ |
| `PATCH` | `/api/v1/profile` | ✅ Access | Cập nhật tên / avatar |
| `POST` | `/api/v1/profile/weight` | ✅ Access | Ghi cân nặng mới |
| `GET` | `/api/v1/profile/weight/history` | ✅ Access | Lịch sử cân nặng |
| `GET` | `/api/v1/progress/weekly` | ✅ Access | Thống kê tuần (1–52 tuần) |
| `GET` | `/api/v1/progress/monthly` | ✅ Access | Thống kê tháng (1–24 tháng) |

---

## 🧪 Kết quả test

```
tests/test_profile_progress.py  ................  16 passed
```

Tất cả chạy với mock, không cần kết nối DB hay Cloudinary thật.
