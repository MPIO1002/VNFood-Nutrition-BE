# Tổng quan backend VNFood Nutrition

> Phạm vi tài liệu: source đang ở nhánh `main`, FastAPI `0.5.1`. Tài liệu này là
> bản đồ để biết backend có gì, nằm ở đâu và một request đi qua hệ thống như thế
> nào. Chi tiết hợp đồng request/response cho từng API dinh dưỡng nằm trong
> [NUTRITION_MEAL_API.md](NUTRITION_MEAL_API.md); hướng dẫn JWT chi tiết nằm trong
> [README.md](README.md).

## 1. Trạng thái hiện tại

Backend đã có bốn nhóm chức năng chính:

1. **Phân tích ảnh món ăn**: nhận ảnh, nhận diện món bằng YOLO, tạo mask/segment,
   ước lượng khẩu phần và tính dinh dưỡng dựa trên dữ liệu công thức món ăn.
2. **Xác thực người dùng**: đăng ký, đăng nhập, JWT access/refresh token, refresh
   token rotation, logout và lấy người dùng hiện tại.
3. **Dinh dưỡng cá nhân**: tính BMI, RMR/BMR theo Mifflin-St Jeor, TDEE, mục tiêu
   kcal, mục tiêu macro và thời gian ước tính để thay đổi cân nặng.
4. **Theo dõi bữa ăn**: tạo meal log và lấy tổng kcal/macro theo ngày, quy đổi theo
   múi giờ `Asia/Bangkok`.

Backend dùng **FastAPI + PostgreSQL/Neon + psycopg2**, còn phần AI dùng
**Ultralytics/ONNX (tùy model), OpenCV, NumPy và Pillow**. Mô hình được tìm tự động
tại `backend/models/best.pt` hoặc có thể chỉ định bằng biến `CALCUCALO_MODEL`.

## 2. Bản đồ source

```text
VNFood-Nutrition-BE/
├── backend/
│   ├── src/calcucalo/
│   │   ├── api/                 # HTTP layer: FastAPI routes và Pydantic models
│   │   │   ├── app.py           # App entry point, health, model info, food analysis
│   │   │   ├── auth.py          # JWT auth, current-user dependency
│   │   │   └── nutrition_meals.py # BMI/TDEE và meal-log routes
│   │   ├── core/
│   │   │   └── database.py      # Đọc .env, PostgreSQL connection pool
│   │   ├── domain/
│   │   │   └── models.py        # Các model dữ liệu cho vision pipeline
│   │   ├── repositories/
│   │   │   ├── nutrition.py     # Catalog/công thức dinh dưỡng và truy vấn món ăn
│   │   │   └── nutrition_tracking.py # Đọc/ghi profile và meal_logs
│   │   ├── services/            # Nghiệp vụ: detector, segmenter, portion, metabolism...
│   │   └── cli.py               # CLI xử lý ảnh/dataset ngoài HTTP API
│   ├── configs/                 # Class labels, portion priors, cấu hình DB không chứa secret
│   ├── migrations/              # SQL schema và seed data, chạy theo thứ tự thủ công
│   ├── models/                  # Checkpoint model cục bộ, hiện có best.pt
│   ├── scripts/                 # Init DB, smoke tests, train/evaluate/prepare dataset
│   ├── tests/                   # Unit/API tests
│   ├── .env.example             # Mẫu biến môi trường, không chứa credential thật
│   └── pyproject.toml           # Python package, dependencies và cấu hình pytest/ruff
├── frontend/                    # Test console HTML/CSS/JS tĩnh, không phải product frontend
├── docs/                        # Tài liệu backend
└── infra/compose.yaml           # Container development cho backend
```

### Nơi nên thêm code mới

| Loại thay đổi | Nơi đặt code |
| --- | --- |
| Route HTTP, validate input/output | `backend/src/calcucalo/api/` |
| Nghiệp vụ độc lập với HTTP/DB | `backend/src/calcucalo/services/` |
| SQL/query, đọc ghi PostgreSQL | `backend/src/calcucalo/repositories/` |
| Kết nối, cache, config hạ tầng | `backend/src/calcucalo/core/` |
| Kiểu dữ liệu vision dùng chung | `backend/src/calcucalo/domain/` |
| Thay đổi schema/data | migration SQL mới trong `backend/migrations/` |
| Kiểm thử | file tương ứng trong `backend/tests/` |

Nguyên tắc luồng phụ thuộc là: `api -> services/repositories -> core/database`.
Route không nên chứa SQL hoặc công thức nghiệp vụ lớn; service không nên phụ thuộc
trực tiếp vào FastAPI.

## 3. Các API đang có

Swagger sinh tự động tại `http://127.0.0.1:8000/docs` khi server chạy.

| Nhóm | Endpoint | JWT | Mục đích |
| --- | --- | --- | --- |
| System | `GET /` | Không | Chuyển đến test console `/test-ui/` |
| System | `GET /health` | Không | Trạng thái app, model và việc DB đã được cấu hình hay chưa |
| Vision | `GET /api/v1/model/info` | Không | Backend detector, trạng thái checkpoint và cảnh báo readiness |
| Vision | `POST /api/v1/food/analyze` | Không | Upload ảnh món ăn; tùy chọn `container_type`, `response_format=full|nutrition` |
| Auth | `GET /api/v1/auth/health` | Không | Kiểm tra auth schema và kết nối PostgreSQL |
| Auth | `POST /api/v1/auth/register` | Không | Tạo user và trả access/refresh token |
| Auth | `POST /api/v1/auth/login` | Không | Xác thực email/password và trả token pair |
| Auth | `POST /api/v1/auth/refresh` | Refresh token trong JSON | Rotate refresh token và trả token pair mới |
| Auth | `POST /api/v1/auth/logout` | Refresh token trong JSON | Thu hồi một refresh token |
| Auth | `POST /api/v1/auth/logout-all` | Access token | Thu hồi toàn bộ refresh token của user |
| Auth | `GET /api/v1/auth/me` | Access token | Lấy user hiện tại |
| Nutrition | `POST /api/v1/nutrition/calculate` | Access token | Tính và lưu profile BMI/RMR/TDEE/mục tiêu |
| Meals | `POST /api/v1/meals` | Access token | Tạo meal log từ catalog món hoặc kcal/macro nhập tay |
| Meals | `GET /api/v1/meals/daily?date=YYYY-MM-DD` | Access token | Lấy bữa ăn, tổng và phần còn lại trong một ngày |

`/food/analyze` giới hạn ảnh ở 15 MB. Các endpoint nutrition/meals dùng header:

```http
Authorization: Bearer <access_token>
```

## 4. Luồng xử lý chính

### 4.1 Khởi động và quản lý dependency

```text
.env
  -> core/database.py đọc DATABASE_URL hoặc DB_*
  -> PostgresDatabase (pool 1..5 connection mặc định, tạo lazy)
  -> api/app.py tạo FastAPI app và include các router
  -> request đầu tiên mới khởi tạo dependency cần thiết
```

- `get_database()` được cache một instance trên mỗi process; mỗi thao tác lấy một
  connection từ `ThreadedConnectionPool`, commit khi thành công và rollback khi lỗi.
- `get_auth_service()` và `get_analyzer()` cũng được cache. Vì vậy detector/model
  chỉ được load khi API vision đầu tiên cần nó, không phải ngay lúc Uvicorn khởi động.
- `app.py` mount thư mục `frontend/` tại `/test-ui`, nên test console và API local
  cùng origin, chưa cần cấu hình CORS cho trường hợp này.

### 4.2 Đăng ký, đăng nhập và JWT

```text
Client
  -> /auth/register hoặc /auth/login
  -> AuthService
      -> bcrypt hash / verify password
      -> users
      -> tạo access JWT + refresh JWT
      -> chỉ lưu SHA-256(refresh JWT) vào auth_refresh_tokens
  <- token pair + user

Client -- Authorization: Bearer access JWT --> endpoint bảo vệ
  -> get_current_user kiểm tra chữ ký, exp, issuer, audience, type=access
  -> lấy user còn active từ users
  -> route nghiệp vụ
```

- Access token mặc định sống **15 phút**, refresh token **30 ngày**; cấu hình bởi
  `JWT_ACCESS_TOKEN_MINUTES` và `JWT_REFRESH_TOKEN_DAYS`.
- Khi refresh, backend khóa dòng token trong transaction, thu hồi token cũ, tạo token
  mới và lưu quan hệ thay thế. Refresh token cũ không dùng lại được.
- Logout thu hồi refresh token; access token đã phát không có denylist nên còn hiệu
  lực đến khi hết hạn. Đây là hành vi có chủ đích của thiết kế hiện tại.

### 4.3 Tính chỉ số dinh dưỡng và mục tiêu ngày

```text
POST /nutrition/calculate + access token
  -> validate người trưởng thành, activity, goal và các trường hợp không hỗ trợ
  -> services/metabolism.py
      BMI = kg / m²
      RMR = Mifflin-St Jeor
      TDEE = RMR x activity factor
      mục tiêu kcal = TDEE +/- điều chỉnh theo goal, kèm safety floor
      macro target = tỷ lệ protein/carb/fat theo goal
  -> repositories/nutrition_tracking.py cập nhật profile users
  <- chỉ số, target kcal/macro, thời gian ước tính và cảnh báo
```

Đây là **ước tính cho người trưởng thành khỏe mạnh**, không phải chẩn đoán hoặc đơn
thuốc. Request có thai/cho con bú, vận động viên thi đấu hoặc tình trạng/thuốc ảnh
hưởng chuyển hóa sẽ bị từ chối `422` thay vì trả một kết quả có vẻ chính xác nhưng
không an toàn.

### 4.4 Ghi và tổng hợp meal log

```text
POST /meals + access token
  -> NutritionTrackingRepository
  -> nếu có dish_id: lấy recipe từ dishes -> dish_ingredients -> ingredients
  -> nếu nhập tay: dùng total_calories (và macro nếu có)
  -> lưu snapshot kcal/macro, calorie_source vào meal_logs

GET /meals/daily
  -> lấy meal_logs của user trong ngày Asia/Bangkok
  -> cộng kcal/protein/fat/carb
  -> lấy target_calories/profile đã lưu trong users
  <- tổng đã nạp, target, phần còn lại và danh sách meals
```

Lưu giá trị kcal/macro tại thời điểm tạo log giúp lịch sử không bị thay đổi ngược khi
công thức một món ăn được cập nhật sau này. Xem đầy đủ input/output, giới hạn và ví dụ
tại [NUTRITION_MEAL_API.md](NUTRITION_MEAL_API.md).

### 4.5 Phân tích ảnh món ăn

```text
POST /food/analyze (multipart image)
  -> kiểm tra ảnh/ràng buộc 15 MB
  -> detector (YOLO .pt/.onnx) tìm món ăn
  -> segmenter (mặc định GrabCut) tạo mask nếu detector chưa có mask
  -> portion estimator dùng scale/plate/container hoặc prior
  -> NutritionDB đối chiếu dish/ingredients trong PostgreSQL
  -> AnalysisResult + nutrition totals + optional visual_base64 overlay
```

Kết quả vision là ước lượng. Endpoint `/api/v1/model/info` luôn báo rõ checkpoint
chưa được coi là production-ready (`production_ready: false`) cho đến khi có đánh giá
độc lập về nhận diện, khẩu phần và dinh dưỡng end-to-end.

## 5. Database và migration

PostgreSQL/Neon là nguồn dữ liệu dùng chung cho auth, profile, catalog món ăn và meal
log. Quan hệ chính trong source hiện tại là:

```text
users
 ├──< auth_refresh_tokens       (user_id, ON DELETE CASCADE)
 └──< meal_logs                 (user_id, ON DELETE CASCADE)
          └──> dishes           (dish_id, ON DELETE SET NULL)
                    └──< dish_ingredients >── ingredients
```

| Migration | Vai trò | Lưu ý |
| --- | --- | --- |
| `0001_neon_nutrition_db.sql` | Tạo/seed `dishes`, `ingredients`, `dish_ingredients` | Dữ liệu catalog ban đầu |
| `0002_auth.sql` | Auth schema cũ với `app_users` | Chỉ còn giá trị lịch sử, không dùng cho DB mới |
| `0003_unify_user_model.sql` | Hợp nhất auth vào `users`, tạo `auth_refresh_tokens` | Có `DROP TABLE`; không chạy lại trên DB đang có dữ liệu mà chưa review/backup |
| `0004_nutrition_meal_apis.sql` | Thêm profile cho `users`, tạo `meal_logs` | Cần cho nutrition/meal API |
| `0005_harden_nutrition_calculations.sql` | Thêm `sex_for_equation`, nguồn/calories catalog | Bổ sung validation/schema |
| `0006_meal_macros.sql` | Thêm protein, fat, carb cho `meal_logs` | Cần để theo dõi macro |

`scripts/init_auth_db.py` chỉ bảo đảm bảng/cột **auth** cần thiết có mặt; nó không
phải migration runner và không tự chạy các migration meal/catalog. Với database mới,
hãy review rồi chạy các script theo thứ tự trong DBeaver/Neon SQL Editor. Đối với Neon
đang dùng, chỉ áp dụng migration chưa có; kiểm tra trạng thái schema trước khi chạy.

Lưu ý: sơ đồ DBeaver có thể còn các bảng legacy như `weight_history`. Source hiện tại
không có repository/endpoint sử dụng bảng đó, nên không xem nó là một phần của luồng
backend đang hoạt động.

## 6. Cấu hình, chạy local và Docker

Tạo `backend/.env` từ `backend/.env.example`; credential Neon và JWT secret chỉ nằm
trong `.env`, không commit vào Git.

Biến cần thiết:

```dotenv
DATABASE_URL=postgresql://USER:PASSWORD@HOST:5432/DATABASE?sslmode=require
DB_POOL_MIN=1
DB_POOL_MAX=5

JWT_SECRET_KEY=<random-secret-at-least-32-characters>
JWT_ALGORITHM=HS256
JWT_ISSUER=calcucalo-api
JWT_AUDIENCE=calcucalo-mobile
JWT_ACCESS_TOKEN_MINUTES=15
JWT_REFRESH_TOKEN_DAYS=30

# Tùy chọn; nếu bỏ trống app tự tìm backend/models/best.pt
CALCUCALO_MODEL=models/best.pt
CALCUCALO_SEGMENTER=grabcut
```

Từ thư mục `backend/` sau khi đã cài package editable:

```powershell
uvicorn calcucalo.api.app:app --reload --host 127.0.0.1 --port 8000
```

Các địa chỉ kiểm tra:

- `http://127.0.0.1:8000/docs`: Swagger/OpenAPI.
- `http://127.0.0.1:8000/test-ui/`: giao diện test auth và upload ảnh.
- `http://127.0.0.1:8000/health`: không kiểm tra kết nối DB thật, chỉ cho biết DB đã được cấu hình.
- `http://127.0.0.1:8000/api/v1/auth/health`: kiểm tra auth schema và kết nối DB thật.

Docker development dùng [infra/compose.yaml](../infra/compose.yaml):

```powershell
docker compose -f infra/compose.yaml up backend
```

Container bind-mount source repo, đọc `backend/.env`, cài extra `[api]` rồi chạy
Uvicorn cổng 8000. Đây là compose cho development, chưa phải production deployment.

## 7. Kiểm thử và trạng thái đã xác minh

Test code nằm ở `backend/tests/`:

- `test_auth.py`, `test_nutrition_meals_api.py`, `test_metabolism.py`: JWT và phần
  API dinh dưỡng/bữa ăn.
- Các test còn lại: vision, portion, detector, calibration, dataset và evaluation.
- `scripts/smoke_test_auth.py`: E2E với DB trong `.env`; tạo user tạm rồi cleanup.
- `scripts/smoke_test_nutrition_meals.py`: E2E register -> calculate -> create meal
  -> daily meals với DB thật; cũng dọn dữ liệu test.

Lệnh nên chạy từ `backend/`, sau khi kích hoạt **đúng virtual environment của repo**:

```powershell
python -m pytest
python -m pytest tests/test_auth.py tests/test_metabolism.py tests/test_nutrition_meals_api.py -q
python scripts/smoke_test_auth.py
python scripts/smoke_test_nutrition_meals.py
```

Test console frontend chỉ cần kiểm tra cú pháp JavaScript:

```powershell
cd frontend
npm run check
```

**Kết quả kiểm tra source hiện tại (25-10-2026):** chạy full suite từ `backend/` bằng
virtual environment của dự án cho kết quả **58 pass, 5 fail**. Năm test fail đều ở
`tests/test_nutrition.py` vì file `backend/configs/food_catalog.json` không còn trong
repository. Luồng API đang đọc catalog PostgreSQL thông qua `NutritionDB`, nhưng
fallback JSON/CLI và các test catalog vẫn còn tham chiếu file cũ này. Đây là technical
debt cần xử lý trước khi có thể coi full suite là xanh.

Không chạy smoke test trong lúc viết tài liệu vì các script này tạo dữ liệu tạm trên
Neon thật. Hãy chỉ chạy khi `.env` trỏ đúng môi trường được phép ghi dữ liệu.

## 8. Giới hạn và việc nên làm tiếp

1. **Sửa hoặc khôi phục `food_catalog.json`**: hoặc đưa catalog JSON quay lại và cập
   nhật nó, hoặc đổi CLI/tests để dùng PostgreSQL một cách nhất quán.
2. **Dùng migration tool**: hiện migration SQL được chạy thủ công. Khi nhiều môi
   trường/team hơn, nên dùng Alembic hoặc công cụ tương đương có bảng version.
3. **Chuẩn bị product frontend**: `frontend/` hiện là test console thuần HTML/CSS/JS.
   Frontend tách origin sau này sẽ cần cấu hình CORS, luồng refresh token và quản lý
   state rõ ràng.
4. **Bổ sung API nghiệp vụ**: chưa có update/delete meal, profile CRUD riêng, lịch sử
   cân nặng được quản lý qua API, search catalog món ăn, password reset/email verify
   hay rate-limit đăng nhập.
5. **Đánh giá model**: không dùng output vision để kết luận chính xác y khoa hoặc
   production khi chưa có bộ đánh giá độc lập cho detector, khẩu phần và nutrition.

## 9. Quy ước làm việc đề xuất

Với mỗi feature backend mới: tạo branch từ `main`, thêm route/service/repository/test
theo đúng layer, thêm migration *chỉ theo hướng tiến* nếu đổi schema, chạy test liên
quan và full suite, review migration trên Neon staging/dev trước, rồi mới merge về
`main`. Không sửa hoặc chạy lại migration cũ có thao tác phá hủy dữ liệu trên database
đang dùng.
