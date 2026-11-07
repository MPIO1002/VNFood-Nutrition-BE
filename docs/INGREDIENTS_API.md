# Ingredients Search API

Tài liệu này mô tả API tìm kiếm thành phần dinh dưỡng (nguyên liệu) trong cơ sở dữ liệu thực phẩm Việt Nam.

> API này chỉ đọc (GET). Dùng để hỗ trợ autocomplete khi người dùng xác định thành phần món ăn trong quá trình ghi nhật ký.

---

## 1. Tổng quan

| Method | Endpoint | Chức năng |
| --- | --- | --- |
| `GET` | `/api/v1/ingredients/search` | Tìm kiếm thành phần theo tên (substring, không phân biệt hoa thường) |

Yêu cầu JWT access token:

```http
Authorization: Bearer <access_token>
```

---

## 2. Thành phần triển khai

| File | Vai trò |
| --- | --- |
| `backend/src/calcucalo/api/ingredients.py` | Schema và router |
| `backend/migrations/0001_neon_nutrition_db.sql` | Bảng `ingredients` và dữ liệu mẫu |

---

## 3. Cơ sở dữ liệu

Bảng `ingredients` chứa dữ liệu dinh dưỡng **per 100g** của thực phẩm Việt Nam:

```sql
CREATE TABLE ingredients (
    id               SERIAL PRIMARY KEY,
    ingredients_name VARCHAR(255) NOT NULL,
    calories         FLOAT NOT NULL,  -- kcal per 100g
    protein          FLOAT NOT NULL,  -- g per 100g
    fat              FLOAT NOT NULL,  -- g per 100g
    carb             FLOAT NOT NULL,  -- g per 100g
    created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

Hiện có **~800+ nguyên liệu** từ cơm, bún, thịt, cá, rau củ, gia vị, v.v.

---

## 4. GET /api/v1/ingredients/search

### Request

```http
GET /api/v1/ingredients/search?q=gà&limit=10
Authorization: Bearer <access_token>
```

| Param | Kiểu | Bắt buộc | Mô tả |
| --- | --- | --- | --- |
| `q` | string (1–200 ký tự) | Có | Từ khóa tìm kiếm tên thành phần |
| `limit` | int (1–100) | Không | Số kết quả trả về (mặc định **20**) |
| `offset` | int (≥ 0) | Không | Bỏ qua N kết quả đầu để phân trang (mặc định **0**) |

**Cơ chế tìm kiếm:** `ILIKE '%<q>%'` — tìm chuỗi con, không phân biệt hoa thường, không cần dấu đầy đủ.

> [!TIP] Frontend nên gọi API khi user gõ ≥ 2 ký tự và debounce 300ms để tránh quá nhiều request.

### Response `200 OK`

```json
{
  "query": "gà",
  "total": 12,
  "results": [
    {
      "id": 145,
      "name": "Gà ta (thịt)",
      "calories_per_100g": 199.0,
      "protein_g": 20.3,
      "fat_g": 13.1,
      "carb_g": 0.0
    },
    {
      "id": 146,
      "name": "Gà broiler (thịt nạc)",
      "calories_per_100g": 165.0,
      "protein_g": 31.0,
      "fat_g": 3.6,
      "carb_g": 0.0
    },
    {
      "id": 147,
      "name": "Trứng gà",
      "calories_per_100g": 158.0,
      "protein_g": 12.5,
      "fat_g": 11.5,
      "carb_g": 1.1
    }
  ]
}
```

#### Giải thích trường response

| Trường | Ý nghĩa |
| --- | --- |
| `query` | Từ khóa đã tìm (đã trim whitespace) |
| `total` | Tổng số kết quả khớp (toàn bộ DB, không giới hạn bởi `limit`) |
| `results[]` | Danh sách kết quả theo trang |
| `results[].id` | ID nguyên liệu — dùng để tạo meal log thủ công |
| `results[].name` | Tên nguyên liệu |
| `results[].calories_per_100g` | Năng lượng (kcal) trên 100g |
| `results[].protein_g` | Protein (g) trên 100g |
| `results[].fat_g` | Chất béo (g) trên 100g |
| `results[].carb_g` | Tinh bột (g) trên 100g |

### Phân trang

Dùng `limit` + `offset` để phân trang:

```
# Trang 1: offset=0, limit=20
GET /api/v1/ingredients/search?q=gà&limit=20&offset=0

# Trang 2: offset=20, limit=20
GET /api/v1/ingredients/search?q=gà&limit=20&offset=20
```

---

## 5. Response lỗi

| HTTP | Tình huống |
| --- | --- |
| `401 Unauthorized` | Thiếu hoặc hết hạn JWT |
| `422 Unprocessable Entity` | `q` trống hoặc quá dài (> 200 ký tự); `limit` ngoài [1, 100]; `offset` âm |
| `503 Service Unavailable` | Lỗi kết nối database |

---

## 6. Ví dụ gọi API (cURL)

### Tìm nguyên liệu chứa "bò"

```bash
curl -X GET \
  "https://api.example.com/api/v1/ingredients/search?q=b%C3%B2&limit=10" \
  -H "Authorization: Bearer <token>"
```

### Tìm "rau muống" với phân trang

```bash
# Trang 1
curl -X GET \
  "https://api.example.com/api/v1/ingredients/search?q=rau+mu%E1%BB%91ng&limit=5&offset=0" \
  -H "Authorization: Bearer <token>"
```

---

## 7. Use case trong màn hình ghi nhật ký

```
User gõ "gà" vào ô tìm kiếm thành phần
  → FE gọi GET /api/v1/ingredients/search?q=gà&limit=10
  → Hiển thị dropdown với tên + calo/100g
  → User chọn "Gà ta (thịt)", nhập 150g
  → FE tính: calories = 199 × 1.5 = 298.5 kcal
  → FE gửi POST /api/v1/meals với total_calories=298.5, protein_g=30.5, v.v.
```

