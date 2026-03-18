# Dev & Deployment Commands

## Local Development (Docker Compose)

### Start app + database
```bash
docker compose up
```

### Start in background
```bash
docker compose up -d
```

### Stop everything
```bash
docker compose down
```

### Stop + xóa volumes (reset DB)
```bash
docker compose down -v
```

---

## Build

### Build image bình thường
```bash
docker compose build
```

### Build lại từ đầu (no cache)
```bash
docker compose build --no-cache
```

### Build chỉ test stage
```bash
docker build --target test -t scheduler-test .
```

---

## Database & Migrations

### Chạy tất cả migrations (upgrade to latest)
```bash
docker compose exec app alembic upgrade head
```

### Upgrade lên 1 bước tiếp theo
```bash
docker compose exec app alembic upgrade +1
```

### Upgrade đến revision cụ thể
```bash
docker compose exec app alembic upgrade 001
```

### Rollback 1 bước
```bash
docker compose exec app alembic downgrade -1
```

### Rollback toàn bộ (về trạng thái trống)
```bash
docker compose exec app alembic downgrade base
```

### Rollback về revision cụ thể
```bash
docker compose exec app alembic downgrade 001
```

### Xem migration history (tất cả)
```bash
docker compose exec app alembic history
```

### Xem migration history dạng verbose
```bash
docker compose exec app alembic history --verbose
```

### Xem revision hiện tại đang apply
```bash
docker compose exec app alembic current
```

### Tạo migration mới (autogenerate từ model changes)
```bash
docker compose exec app alembic revision --autogenerate -m "describe your change"
```

### Tạo migration thủ công (không autogenerate)
```bash
docker compose exec app alembic revision -m "describe your change"
```

### Xem SQL sẽ chạy mà KHÔNG apply (dry run)
```bash
docker compose exec app alembic upgrade head --sql
```

### Stamp revision (đánh dấu DB đang ở revision nào mà không chạy migration)
```bash
# Dùng khi DB đã có sẵn schema, cần sync với alembic
docker compose exec app alembic stamp head
docker compose exec app alembic stamp 001
```

### Chạy migration trực tiếp trên test DB
```bash
docker run --rm \
  --network host \
  -e TEST_DATABASE_URL=postgresql://scheduler:scheduler@localhost:5432/scheduler_test \
  scheduler-test \
  alembic upgrade head
```

### Seed dữ liệu mẫu
```bash
docker compose --profile seed run --rm seeder
```

---

## Testing

### Chạy tests với SQLite (nhanh, không cần Postgres)
```bash
docker compose --profile test run --rm test
```

### Chạy tests với PostgreSQL (đầy đủ, giống CI/CD)
```bash
docker compose --profile test-pg run --rm test-pg
```

### Chạy test cụ thể
```bash
docker compose --profile test-pg run --rm test-pg python -m pytest tests/test_routes/test_appointments.py -v
```

### Chạy test theo keyword
```bash
docker compose --profile test-pg run --rm test-pg python -m pytest -k "test_create" -v
```

---

## Logs & Debug

### Xem logs app
```bash
docker compose logs app
```

### Xem logs theo realtime
```bash
docker compose logs -f app
```

### Vào shell bên trong container app
```bash
docker compose exec app bash
```

### Vào psql trực tiếp
```bash
docker compose exec db psql -U scheduler -d scheduler_db
```

---

## Clean Up

### Xóa stale containers + networks
```bash
docker compose down --remove-orphans
```

### Xóa dangling images
```bash
docker image prune -f
```

### Xóa unused networks
```bash
docker network prune -f
```

### Full reset (containers + volumes + images)
```bash
docker compose down -v && docker image prune -f
```

### Rebuild + restart từ đầu
```bash
docker compose down -v && docker compose build --no-cache && docker compose up
```

---

## Production

### Build production image
```bash
docker build --target runtime -t scheduler-app:latest .
```

### Chạy production container
```bash
docker run -d \
  --name scheduler-app \
  -p 5000:5000 \
  -e SECRET_KEY=<your-secret> \
  -e DATABASE_URL=postgresql://user:pass@host:5432/scheduler_db \
  scheduler-app:latest
```

### Health check
```bash
curl http://localhost:5000/health
```
