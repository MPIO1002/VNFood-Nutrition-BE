# VNFood Nutrition

Monorepo cho hệ thống nhận diện món ăn Việt Nam, ước lượng khẩu phần, tính dinh dưỡng và quản lý người dùng bằng JWT.

## Cấu trúc dự án

```text
VNFood-Nutrition/
├── backend/
│   ├── src/calcucalo/
│   │   ├── api/             # FastAPI app và auth endpoints
│   │   ├── core/            # Database và hạ tầng dùng chung
│   │   ├── domain/          # Domain models
│   │   ├── repositories/    # Truy cập nguồn dữ liệu
│   │   ├── services/        # AI/nutrition application services
│   │   └── cli.py
│   ├── tests/
│   ├── configs/
│   ├── migrations/
│   ├── schemas/
│   ├── scripts/
│   ├── models/
│   ├── pyproject.toml
│   ├── requirements.txt
│   └── .env.example
├── frontend/
│   ├── src/
│   ├── package.json
│   └── .env.example
├── docs/
│   └── README.md
├── infra/
│   └── compose.yaml
├── .gitignore
└── README.md
```

`frontend/` hiện là workspace rỗng để lựa chọn framework ở bước tiếp theo. Không có frontend giả hoặc dependency chưa sử dụng được đưa vào repository.

## Chạy backend local

Yêu cầu Python 3.10-3.12.

```powershell
cd backend
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[all]"
Copy-Item .env.example .env
```

Điền Neon PostgreSQL URL và JWT secret vào `backend/.env`, sau đó khởi tạo auth schema:

```powershell
python scripts/init_auth_db.py
```

Khởi chạy FastAPI:

```powershell
uvicorn calcucalo.api.app:app --reload --host 127.0.0.1 --port 8000
```

Các URL hữu ích:

- Test console: <http://127.0.0.1:8000/> hoặc <http://127.0.0.1:8000/test-ui/>
- Swagger UI: <http://127.0.0.1:8000/docs>
- API health: <http://127.0.0.1:8000/health>
- Auth/Neon health: <http://127.0.0.1:8000/api/v1/auth/health>

## JWT authentication

Backend cung cấp:

- `POST /api/v1/auth/register`
- `POST /api/v1/auth/login`
- `POST /api/v1/auth/refresh`
- `POST /api/v1/auth/logout`
- `POST /api/v1/auth/logout-all`
- `GET /api/v1/auth/me`
- `GET /api/v1/auth/health`

Xem [tổng quan backend](docs/BACKEND_OVERVIEW.md) để nắm cấu trúc source, luồng xử lý,
database/migration và trạng thái test. Hướng dẫn JWT chi tiết và test thủ công nằm trong
[docs/README.md](docs/README.md).

Test console trong `frontend/` cho phép kiểm tra health, register, login, `/me`, refresh,
logout, logout-all và upload ảnh phân tích trực tiếp trên trình duyệt. FastAPI phục vụ giao diện
này cùng origin nên không cần cấu hình CORS cho môi trường local.

## Nutrition và meal logs

Backend cung cấp API có JWT bảo vệ để ước tính BMI/RMR/TDEE, áp dụng giới hạn
an toàn cho mục tiêu kcal và theo dõi bữa ăn theo ngày. Meal log có thể dùng
kcal nhập thủ công hoặc để backend tính từ catalog nguyên liệu:

- `POST /api/v1/nutrition/calculate`
- `POST /api/v1/meals`
- `GET /api/v1/meals/daily?date=YYYY-MM-DD`

Chi tiết đầu vào, đầu ra, công thức và ví dụ nằm trong
[docs/NUTRITION_MEAL_API.md](docs/NUTRITION_MEAL_API.md).

## Test backend

Chạy từ thư mục `backend/`:

```powershell
python -m pytest
python -m pytest tests/test_auth.py -q
python scripts/smoke_test_auth.py
```

Smoke test sử dụng database trong `.env`, tạo tài khoản ngẫu nhiên và tự xóa dữ liệu test sau khi hoàn tất.

## Chạy bằng Docker Compose

Tạo `backend/.env` trước, sau đó chạy từ thư mục gốc:

```powershell
docker compose -f infra/compose.yaml up backend
```

Compose hiện phục vụ môi trường development: source được bind-mount và dependency backend được cài khi container khởi động.

## Training và evaluation

Chạy các lệnh từ `backend/`:

```powershell
python scripts/train_detector.py `
  --data configs\vietfood67.yaml `
  --model models\yolo11n.pt `
  --epochs 100 `
  --batch -1 `
  --device 0 `
  --export-onnx
```

Không commit `.env`, credential, dataset, checkpoint huấn luyện hoặc token thật vào Git.
