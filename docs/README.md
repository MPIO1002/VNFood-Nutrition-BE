# Backend JWT Authentication

Tài liệu này mô tả cơ chế xác thực JWT hiện tại của CalcuCalo Backend và cách kiểm tra thủ công trên môi trường local kết nối Neon PostgreSQL.

## 1. Trạng thái hiện tại

Backend hỗ trợ các chức năng:

- Đăng ký tài khoản bằng email và mật khẩu.
- Đăng nhập để nhận access token và refresh token.
- Xác thực người dùng bằng Bearer access token.
- Đổi refresh token lấy một cặp token mới.
- Thu hồi refresh token khi đăng xuất.
- Thu hồi toàn bộ refresh token của một tài khoản.
- Lưu mật khẩu dưới dạng bcrypt hash.
- Chỉ lưu SHA-256 hash của refresh token trong database, không lưu token gốc.

Thời hạn mặc định:

- Access token: 15 phút.
- Refresh token: 30 ngày.

Các giá trị này có thể thay đổi bằng biến môi trường.

## 2. Thành phần chính

- `backend/src/calcucalo/api/auth.py`: request/response model, JWT service, dependency xác thực và auth router.
- `backend/src/calcucalo/core/database.py`: cấu hình PostgreSQL và connection pool.
- `backend/migrations/0002_auth.sql`: schema cho bảng người dùng và refresh token.
- `backend/scripts/init_auth_db.py`: khởi tạo schema và kiểm tra kết nối database.
- `backend/scripts/smoke_test_auth.py`: chạy luồng auth end-to-end với database thật.
- `backend/tests/test_auth.py`: unit test cho password hashing, token claims và route registration.

## 3. Luồng hoạt động

### Đăng ký hoặc đăng nhập

1. Client gửi email và mật khẩu.
2. Khi đăng ký, backend hash mật khẩu bằng bcrypt rồi lưu vào `app_users`.
3. Backend tạo một access token và một refresh token.
4. Refresh token được hash bằng SHA-256 trước khi lưu vào `auth_refresh_tokens`.
5. Token gốc chỉ được trả về cho client.

Mỗi JWT chứa các claim chính:

- `sub`: ID người dùng.
- `type`: `access` hoặc `refresh`.
- `jti`: ID duy nhất của token.
- `iss`: issuer.
- `aud`: audience.
- `iat`: thời điểm phát hành.
- `exp`: thời điểm hết hạn.

### Gọi API cần đăng nhập

Client gửi access token trong header:

```http
Authorization: Bearer <access_token>
```

Backend kiểm tra chữ ký, thời hạn, issuer, audience, loại token và trạng thái tài khoản trước khi trả dữ liệu.

### Refresh token

1. Client gửi refresh token hiện tại đến `/api/v1/auth/refresh`.
2. Backend xác thực JWT và tìm SHA-256 hash tương ứng trong database.
3. Backend khóa bản ghi token trong transaction để tránh refresh đồng thời.
4. Backend phát một cặp token mới.
5. Refresh token cũ bị thu hồi và liên kết tới token thay thế.

Refresh token cũ không thể sử dụng lại sau khi rotation thành công.

### Logout

- `/logout` thu hồi refresh token được gửi lên.
- `/logout-all` thu hồi toàn bộ refresh token còn hiệu lực của người dùng.
- Access token đã phát không được lưu trong database, vì vậy nó vẫn có hiệu lực cho tới khi hết hạn, tối đa 15 phút theo cấu hình mặc định.

## 4. Database schema

`app_users` lưu:

- Email duy nhất.
- Bcrypt password hash.
- Họ tên và trạng thái tài khoản.
- Thời điểm tạo/cập nhật.

`auth_refresh_tokens` lưu:

- ID token và ID người dùng.
- SHA-256 hash của refresh token.
- Thời điểm hết hạn và thu hồi.
- ID refresh token thay thế khi token được rotation.

Xóa một người dùng sẽ tự động xóa các refresh token liên quan qua `ON DELETE CASCADE`.

## 5. Cấu hình local

Yêu cầu Python 3.10-3.12 và một PostgreSQL/Neon database.

Từ thư mục gốc repository, chuyển vào backend:

```powershell
cd backend
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[api,dev]"
Copy-Item .env.example .env
```

Điền cấu hình thật vào `.env`:

```dotenv
DATABASE_URL=postgresql://USER:PASSWORD@HOST:5432/DATABASE?sslmode=require
DB_POOL_MIN=1
DB_POOL_MAX=5

JWT_SECRET_KEY=replace-with-a-random-secret-of-at-least-32-characters
JWT_ALGORITHM=HS256
JWT_ISSUER=calcucalo-api
JWT_AUDIENCE=calcucalo-mobile
JWT_ACCESS_TOKEN_MINUTES=15
JWT_REFRESH_TOKEN_DAYS=30
```

Tạo JWT secret ngẫu nhiên:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(64))"
```

Không commit `.env`, database password, JWT secret hoặc token thật vào Git.

Khởi tạo schema và kiểm tra kết nối:

```powershell
python scripts/init_auth_db.py
```

Kết quả mong đợi:

```text
Authentication schema is ready in database 'nutrition_db'.
```

## 6. Khởi chạy API

```powershell
uvicorn calcucalo.api.app:app --reload --host 127.0.0.1 --port 8000
```

Mở Swagger UI tại:

```text
http://127.0.0.1:8000/docs
```

Hoặc mở giao diện kiểm thử trực quan tại:

```text
http://127.0.0.1:8000/
```

Giao diện hỗ trợ health check, đăng ký, đăng nhập, `/me`, refresh, logout, logout-all và gửi
ảnh tới food analysis API. Access/refresh token chỉ được lưu trong `sessionStorage` của tab hiện tại.

Kiểm tra auth service và database:

```powershell
Invoke-RestMethod -Method Get -Uri "http://127.0.0.1:8000/api/v1/auth/health"
```

Kết quả mong đợi:

```json
{
  "status": "ok",
  "database": "reachable"
}
```

## 7. Test thủ công bằng PowerShell

Các lệnh dưới đây giả định API đang chạy ở `http://127.0.0.1:8000`.

### Bước 1: Tạo dữ liệu test

```powershell
$baseUrl = "http://127.0.0.1:8000"
$email = "manual-$([guid]::NewGuid().ToString('N'))@example.com"
$password = "Manual-Test-Password-123!"
```

Email ngẫu nhiên giúp tránh lỗi trùng tài khoản khi chạy lại.

### Bước 2: Đăng ký

```powershell
$registerBody = @{
    email = $email
    password = $password
    full_name = "Manual JWT Test"
} | ConvertTo-Json

$register = Invoke-RestMethod `
    -Method Post `
    -Uri "$baseUrl/api/v1/auth/register" `
    -ContentType "application/json" `
    -Body $registerBody

$accessToken = $register.access_token
$refreshToken = $register.refresh_token
$register.user
```

Kết quả mong đợi: HTTP `201`, có `access_token`, `refresh_token` và thông tin user.

### Bước 3: Gọi `/me` bằng access token

```powershell
$headers = @{ Authorization = "Bearer $accessToken" }
$me = Invoke-RestMethod `
    -Method Get `
    -Uri "$baseUrl/api/v1/auth/me" `
    -Headers $headers

$me
```

Kết quả mong đợi: HTTP `200` và email trả về giống `$email`.

### Bước 4: Đăng nhập

```powershell
$loginBody = @{
    email = $email
    password = $password
} | ConvertTo-Json

$login = Invoke-RestMethod `
    -Method Post `
    -Uri "$baseUrl/api/v1/auth/login" `
    -ContentType "application/json" `
    -Body $loginBody

$login.access_token
```

Kết quả mong đợi: HTTP `200` và một cặp token mới.

### Bước 5: Refresh và kiểm tra rotation

```powershell
$refreshBody = @{ refresh_token = $refreshToken } | ConvertTo-Json
$refreshed = Invoke-RestMethod `
    -Method Post `
    -Uri "$baseUrl/api/v1/auth/refresh" `
    -ContentType "application/json" `
    -Body $refreshBody

$newAccessToken = $refreshed.access_token
$newRefreshToken = $refreshed.refresh_token
```

Thử dùng lại refresh token cũ:

```powershell
try {
    Invoke-RestMethod `
        -Method Post `
        -Uri "$baseUrl/api/v1/auth/refresh" `
        -ContentType "application/json" `
        -Body $refreshBody
} catch {
    $_.Exception.Response.StatusCode.value__
}
```

Kết quả mong đợi: HTTP `401`, vì refresh token cũ đã bị thu hồi.

### Bước 6: Logout

```powershell
$logoutBody = @{ refresh_token = $newRefreshToken } | ConvertTo-Json
Invoke-RestMethod `
    -Method Post `
    -Uri "$baseUrl/api/v1/auth/logout" `
    -ContentType "application/json" `
    -Body $logoutBody
```

Thử refresh bằng token vừa logout:

```powershell
try {
    Invoke-RestMethod `
        -Method Post `
        -Uri "$baseUrl/api/v1/auth/refresh" `
        -ContentType "application/json" `
        -Body $logoutBody
} catch {
    $_.Exception.Response.StatusCode.value__
}
```

Kết quả mong đợi: HTTP `401`.

### Bước 7: Test logout tất cả thiết bị

Đăng nhập lại để nhận token mới:

```powershell
$session = Invoke-RestMethod `
    -Method Post `
    -Uri "$baseUrl/api/v1/auth/login" `
    -ContentType "application/json" `
    -Body $loginBody

$sessionHeaders = @{ Authorization = "Bearer $($session.access_token)" }

Invoke-RestMethod `
    -Method Post `
    -Uri "$baseUrl/api/v1/auth/logout-all" `
    -Headers $sessionHeaders
```

Kết quả mong đợi: HTTP `200`. Refresh token của `$session` và các refresh token còn hiệu lực khác của tài khoản sẽ không sử dụng được nữa.

## 8. Test tự động

Chạy các lệnh sau từ thư mục `backend/`.

Chạy unit test JWT không cần gọi database thật:

```powershell
python -m pytest tests/test_auth.py -q
```

Chạy smoke test end-to-end với database trong `.env`:

```powershell
python scripts/smoke_test_auth.py
```

Smoke test thực hiện register, login, gọi `/me`, refresh rotation, kiểm tra token cũ bị từ chối và logout. Tài khoản test được tạo với email ngẫu nhiên và được xóa trong bước cleanup.

## 9. API và mã phản hồi

| Method | Endpoint | Xác thực | Kết quả chính |
| --- | --- | --- | --- |
| `GET` | `/api/v1/auth/health` | Không | Kiểm tra schema và kết nối database |
| `POST` | `/api/v1/auth/register` | Không | Tạo user và trả cặp token |
| `POST` | `/api/v1/auth/login` | Không | Trả cặp token |
| `POST` | `/api/v1/auth/refresh` | Refresh token trong JSON | Rotation và trả cặp token mới |
| `POST` | `/api/v1/auth/logout` | Refresh token trong JSON | Thu hồi một refresh token |
| `POST` | `/api/v1/auth/logout-all` | Bearer access token | Thu hồi toàn bộ refresh token của user |
| `GET` | `/api/v1/auth/me` | Bearer access token | Trả thông tin user hiện tại |

Mã phản hồi thường gặp:

- `200`: yêu cầu thành công.
- `201`: đăng ký thành công.
- `401`: token sai, hết hạn, sai loại hoặc đã bị thu hồi; thông tin đăng nhập không đúng.
- `403`: tài khoản đã bị vô hiệu hóa.
- `409`: email đã được đăng ký.
- `422`: request body không hợp lệ.
- `503`: database hoặc auth service tạm thời không sử dụng được.

## 10. Giới hạn hiện tại

- Chưa có xác minh email, quên mật khẩu hoặc đổi mật khẩu.
- Chưa có rate limiting cho register/login.
- Chưa có job định kỳ dọn refresh token đã hết hạn.
- Access token chưa có denylist nên không bị vô hiệu hóa ngay khi logout.
- Schema đang được khởi tạo bằng SQL/script; khi hệ thống lớn hơn nên chuyển sang migration tool như Alembic.
