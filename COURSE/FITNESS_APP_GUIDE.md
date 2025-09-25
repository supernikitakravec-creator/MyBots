# Fitness Bot → Mobile App (iOS/Android) Migration Guide

This document is a pragmatic plan to convert the Telegram Fitness Bot into a mobile application with a production-grade backend.

## 1. Goals and Deliverables
- Native-like mobile app (Flutter) for iOS/Android
- Backend (FastAPI) with Postgres and Redis
- In‑App Purchases (IAP) for subscriptions (StoreKit/Play Billing) with server-side receipt validation
- Push notifications (APNs via FCM for iOS, FCM for Android)
- Observability (logs, metrics), CI/CD, and secure configuration

## 2. Target Stack
- Mobile: Flutter 3+, Dart, Firebase Messaging (FCM), StoreKit 2 (iOS), Google Play Billing (Android)
- Backend: Python 3.11+, FastAPI, Uvicorn/Gunicorn, SQLAlchemy 2.0, Alembic, Pydantic Settings
- Database: PostgreSQL 15+
- Cache/Queue: Redis 7 (rate limiting, background tasks, notifications)
- Infra: Docker, docker-compose (or Helm later), Nginx reverse proxy
- Observability: Structured JSON logs, Prometheus metrics, Grafana (optional), Sentry (optional)

## 3. Architecture Overview
```
Mobile (Flutter)  <—HTTP/JSON—>  API Gateway (FastAPI)
                                  │
                                  ├─ Auth & Users
                                  ├─ Workouts & Plans
                                  ├─ Subscriptions (IAP receipts)
                                  ├─ Payments history
                                  ├─ Push notifications API
                                  ├─ Admin endpoints (restricted)
                                  │
                                  ├─ Postgres (persistent data)
                                  └─ Redis (cache, rate limits, jobs)

IAP Stores (Apple/Google) → Receipt verify services → Backend (validation)
FCM/APNs → Push delivery
```

## 4. Data Model (tables)
- users: id, email/phone, password_hash (or OAuth), created_at
- user_profiles: user_id, height, weight, age, sex, activity_level, goals, updated_at
- subscriptions: id, user_id, platform (ios/android), product_id, status (active/canceled/expired), 
  period_end, last_receipt, last_verified_at
- workouts: id, title, level, gender, duration, media_refs, is_active
- workout_plans: id, name, plan_json (sequence of workouts/sets), level, gender
- workout_sessions: id, user_id, plan_id/workout_id, start_at, end_at, calories, notes
- promo_codes (optional): code, duration_days, max_uses, used_count, is_active
- events (optional): name, user_id, payload_json, created_at (analytics)
Indexes: by foreign keys, status/date columns; uniques where applicable.

## 5. Configuration & Secrets
- Use .env for local dev; use secret manager or CI/CD secrets in prod
- Pydantic Settings to map env vars → config object
- Separate configs for dev/stage/prod (DB URL, Redis URL, log level)

## 6. API Design (v1)
- Auth
  - POST /auth/register
  - POST /auth/login
  - POST /auth/refresh
- Users & Profile
  - GET /users/me
  - PATCH /users/me/profile
- Workouts & Plans
  - GET /workouts
  - GET /plans
  - GET /plans/{plan_id}
- Sessions & Progress
  - POST /sessions/start
  - POST /sessions/{id}/finish
  - GET /sessions/history?limit=…
- Subscriptions (IAP)
  - POST /iap/verify (body: platform, receipt, app_user_id, device_info)
  - GET /subscriptions/me
- Notifications
  - POST /notifications/register_device (token)
- Admin (protected with role/secret)
  - POST /admin/promocodes
  - GET /admin/stats
Response format: JSON; errors: RFC7807-like {type,title,detail}.

## 7. IAP Flow (Server-Validated)
1) App shows paywall with products from respective stores
2) User buys subscription in app (StoreKit/Play Billing)
3) App sends receipt/token to backend: POST /iap/verify
4) Backend verifies with Apple/Google servers, validates product/period and signature
5) Backend upserts subscription row (status=active, period_end)
6) Mobile fetches /subscriptions/me to refresh UI
7) Renewals/Cancelations: handled via server cron/webhooks to stores if available; backend updates status and period

Security notes:
- Never trust subscription state from the client. Always verify server-side
- Store full receipt payload and last verification timestamps
- Implement replay protection/idempotency for receipt submissions

## 8. Notifications
- Mobile registers FCM token → backend stores token per user/device
- Use Redis queue / background worker to send push batches
- Message types: reminders (workout time), subscription renewal reminders, tips

## 9. Migrations & Seeding
- Alembic for schema changes
- Seed initial workouts/plans from existing training_programs (scripted import)

## 10. Observability
- Logs: JSON (request_id, user_id, route, latency, error)
- Metrics: request_duration, error_rate, push_queue_depth, iap_verify_latency
- Dashboards: API latency, subscription funnel, DAU/MAU, retention (optional)

## 11. Security
- JWT access/refresh tokens; short-lived access tokens
- Strong input validation (Pydantic), rate limiting by IP/user
- CORS rules for mobile; HTTPS everywhere behind Nginx/Load Balancer
- Secret rotation and minimal RBAC for admin endpoints

## 12. CI/CD
- GitHub Actions:
  - Lint (ruff), mypy, tests (pytest + coverage)
  - Build Docker images (backend), Trivy scan
  - Mobile: CI builds to TestFlight/Play Internal testing
- Environments: dev → staging → prod with .env.* or secrets

## 13. 4‑Week Plan & Acceptance Criteria

Week 1 — Backend foundation
- Setup FastAPI project, config, logging, health endpoints
- Setup Postgres + Alembic; implement users, profiles
- Import workouts/plans (from training_programs) into DB
AC:
- /health returns OK; user register/login works; workouts/plans endpoints return data

Week 2 — Mobile skeleton & progress
- Flutter app: auth screens, home, workouts list, plan details
- Sessions: start/finish flow; local caching; offline-safe writes with retry
AC:
- User can sign in, browse plans/workouts, record a session, see history

Week 3 — Subscriptions & notifications
- IAP integration (StoreKit/Play Billing); server receipt validation; subscription gating
- FCM/APNs integration (via FCM), reminders
AC:
- Paywall works on both platforms; server marks subscription active; push reminder arrives

Week 4 — Hardening & release
- Analytics events, error tracking; rate limiting; idempotency
- E2E tests for key flows; App Store/Play assets; Beta release (TestFlight/Closed testing)
AC:
- Beta builds available; basic dashboards; zero critical errors in smoke tests

## 14. Definition of Done (DoD)
- Functionality: auth, workouts/plans, sessions, subscriptions, notifications
- Quality: type-checked, linted, >80% coverage for domain/handlers
- Security: secrets out of repo, HTTPS, server-validated IAP, rate limiters
- Ops: healthchecks, logs/metrics, crash reporting, CI pipelines

## 15. Development Scripts (examples)
```bash
# Backend (dev)
cp .env.example .env
docker compose up -d postgres redis
alembic upgrade head
uvicorn app.main:app --reload

# Mobile (dev)
flutter pub get
flutter run
```

## 16. Next Steps (Post-MVP)
- Personalization (ML light): adaptive plans, streaks, challenges
- Social: friend leaderboards, sharing
- Web dashboard, admin UI
- Internationalization (i18n)

