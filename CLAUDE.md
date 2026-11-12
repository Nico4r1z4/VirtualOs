# VirtualOS — Contexto para Claude Code

Lee también: `docs/DECISIONES.md`, `docs/ARQUITECTURA.md`, `docs/PLAN.md`, `docs/COMPETENCIA.md`.

## Qué es
VirtualOS (suite Orkiza) es una herramienta PROFESIONAL de inteligencia de contenido para creadores, compañías y agencias en TikTok, Instagram y Facebook. Detecta qué contenido está sobre-rindiendo en un nicho, lo cruza con tendencias de plataforma (hashtags, sonidos) y noticias, analiza los ganchos de lo que ganó y lo convierte en un plan de grabación semanal.

Posicionamiento tipo Adobe: usable por cualquiera, pero con herramientas profundas para quien las domina. NO es una herramienta genérica ni "chat-first". El centro de la UI son herramientas densas (tableros, filtros, biblioteca de ganchos, radar de tendencias, calendario). La mascota vive en un panel lateral y las opera; no las reemplaza.

## La mascota (agente)
1. Onboarding: construye un perfil de nicho persistente y anclado; todo el motor trabaja para ese perfil.
2. Única vía para cambiar de nicho; límites por plan (nichos activos, cambios/mes). El perfil viejo se archiva, nunca se borra.
3. Copiloto experto: explica funciones en contexto, sugiere el siguiente paso y ejecuta acciones con herramientas.
4. Proactiva: avisa outliers nuevos y captura feedback post-grabación (idea_feedback).
Regla: nunca inventa métricas; todo número sale de una herramienta.

## Reglas duras
1. Código, variables y commits en inglés; UI, prompts al usuario y docs en español.
2. **No modificar nunca** `../Companies Scrapper/`. Es solo fuente de lectura: se COPIAN módulos aquí y se adaptan.
3. Nunca leer, imprimir ni commitear credenciales (`*accessKeys*.csv`, `.env`). Secretos solo por variables de entorno / AWS Secrets Manager.
4. Toda fuente externa pasa por `SourceConnector` (en `connectors/`). Todo LLM pasa por `LLMProvider`. Ningún otro módulo conoce a Apify, Anthropic u OpenAI.
5. Embudo de costo: el código filtra primero (outliers, ranking) y la IA solo procesa lo que ganó.
6. Texto scrapeado (captions, transcripciones, noticias) entra a prompts delimitado como no confiable. Las herramientas del agente están acotadas al workspace y ninguna hace fetch de URLs arbitrarias.
7. Cada llamada externa (scraper, LLM, transcripción) registra costo y uso en `api_usage` por workspace.
8. Plan mode antes de cada fase. Tests mínimos por conector y por métrica, con fixtures (sin red en tests).

## Stack
- Monorepo: `api/` (Python 3.12, FastAPI, asyncpg, Pydantic Settings, uv) y `web/` (Vite + React + TS + Tailwind + react-query).
- Supabase: Postgres (schema `vos`, RLS por `workspace_id`) + Auth (magic link). La API valida el JWT en cada request.
- AWS: ECS Fargate (API y Worker, misma imagen), SQS, EventBridge Scheduler, S3, Secrets Manager, ECR, CloudFront + WAF. App Runner NO (cerrado a clientes nuevos).
- Cola: interfaz `JobQueue`. MVP con implementación en Postgres (`SELECT ... FOR UPDATE SKIP LOCKED`); SQS como segunda implementación para AWS.
- Datos: Apify (TikTok Creative Center, TikTok perfiles/videos, Instagram perfiles/reels; Facebook como stub). Webhooks de Apify verificados con secreto.
- Transcripción: subtítulos del proveedor; si no hay, faster-whisper local en el Worker.
- LLM: Anthropic por API (modelo rápido para ganchos/agrupación; modelo fuerte para ideas y mascota). IDs de modelo en settings. Prompt caching.
- Modelo de IA por segmento: creadores con IA incluida y topes por plan; empresas con opción futura de traer su propia llave (BYOK, cifrada con KMS). No construir la UI de BYOK en el MVP, pero `LLMProvider` debe permitirlo.

## Dominio
- `niche_profiles`: workspace_id, status (active|archived), tipo (creator|company|agency), plataformas[], países[], idiomas[], keywords[], hashtags[], cuentas_semilla (por plataforma), objetivos, tono.
- `Post` normalizado: platform, external_id, author_handle, url, published_at, views, likes, comments, shares, caption, hashtags[], sound_id/sound_name, duration_s, thumbnail_url, transcript, raw (jsonb, y copia cruda en S3).
- Métricas: outlier = views / mediana de views de los últimos N posts del autor (N=20, mínimo 5); velocidad = Δviews/Δhoras entre `post_snapshots`; ranking ponderado por recencia (7–14 días); tendencias de plataforma por país.
- Tablas (`vos`): workspaces, workspace_members, plan_limits, niche_profiles, accounts, posts, post_snapshots, platform_trends, news_items, hooks, content_ideas (con evidencia: post_ids/trend_ids/news_ids), weekly_briefs, idea_feedback, jobs, api_usage, agent_conversations, agent_messages.

## Herramientas de la mascota
upsert_niche_profile · switch_niche (valida plan_limits) · start_ingestion · get_job_status · get_outliers · get_platform_trends · get_news · get_hooks · generate_ideas · build_weekly_brief · record_feedback · explain_feature.

## Reutilización desde ../Companies Scrapper/orkiza-captacion (copiar, no editar)
- `src/orkiza_captacion/integrations/anthropic_client.py` y `openai_client.py` → base de `LLMProvider` (patrón `LLM_PROVIDER`, caché, costo).
- `src/orkiza_captacion/integrations/web_research.py` → noticias (Serper + DDG).
- `src/orkiza_captacion/observability/emitter.py`, `usage.py` → eventos y costo.
- `src/orkiza_captacion/db/client.py`, `config/settings.py` → pool asyncpg + session pooler de Supabase.
- `Dockerfile`, `.github/workflows/supabase-keepalive.yml`.
- `dashboard/` (shell, `Layout`, `ui.tsx`, `api/client.ts`) → base de `web/`.
- `services/pdf_renderer.py` → export del brief.
NO reutilizar: LangGraph Discover, HITL, RUES, Google Places, ICP.
