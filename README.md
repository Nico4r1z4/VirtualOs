# VirtualOS (suite Orkiza)

Inteligencia de contenido para creadores, compañías y agencias en TikTok, Instagram y Facebook.
Detecta contenido sobre-rindiendo en un nicho, lo cruza con tendencias y noticias, analiza ganchos
y lo convierte en un plan de grabación semanal.

- `api/` — FastAPI + Worker (Python 3.12, uv)
- `web/` — Vite + React + TS + Tailwind
- `deploy/` — Docker Compose + Caddy para la demo en EC2
- `docs/` — decisiones, arquitectura, plan

Setup: copiar `.env.example` → `api/.env`, llenar valores, `cd api && uv sync && uv run python scripts/apply_migrations.py`.
