# VirtualOS — Plan de construcción (MVP para el viernes)

Principio: profundidad sobre amplitud. Cada fase arranca en Claude Code con plan mode y termina con su criterio de cierre.

## Fase 0 — Scaffold (hoy)
Prompt:
> Lee CLAUDE.md y docs/. En plan mode, crea el monorepo api/ + web/. Copia (sin editar el origen) los módulos de reutilización desde ../Companies Scrapper/orkiza-captacion y adáptalos al paquete `virtualos` (LLMProvider sobre anthropic/openai, settings, db, observability). Migración inicial del schema `vos` con RLS por workspace_id, interfaz JobQueue con implementación Postgres, endpoint /health, .env.example y gitleaks en pre-commit. No toques ../Companies Scrapper ni leas archivos de credenciales.

Cierre: tests verdes, /health responde, migración aplicada en Supabase, web levanta con el layout base.

## Fase 1 — Conectores (hoy)
Prompt:
> Implementa SourceConnector y los modelos Post y PlatformTrend. Conectores Apify: tiktok_trends (Creative Center por país), tiktok_profiles, instagram_profiles; news (Serper/DDG); facebook_pages como stub. Registro de costo en api_usage. Tests con fixtures JSON.

Cierre: un script trae tendencias de TikTok CO y 20 posts de 3 cuentas por plataforma, normalizados y guardados.

## Fase 2 — Métricas + tablero de outliers (hoy/mañana temprano)
Prompt:
> Worker que procesa jobs de ingesta por niche_profile, guarda posts y snapshots, calcula outlier score, velocidad y ranking por recencia. Endpoints de outliers y tendencias. En web, el tablero de outliers profesional: filtros por plataforma, país, rango de fechas y multiplicador; vista de detalle del post.

Cierre: tablero real con datos de un nicho.

## Fase 3 — Ganchos + brief (mañana)
Prompt:
> Solo sobre outliers: transcript (subtítulos del proveedor o faster-whisper) y análisis de gancho/estructura con el modelo rápido. generate_ideas con evidencia obligatoria y build_weekly_brief con el modelo fuerte. Vista de biblioteca de ganchos y vista del brief con export PDF y botón "lo grabé".

Cierre: brief semanal real, cada idea enlazada a su evidencia.

## Fase 4 — Mascota en onboarding (mañana)
Prompt:
> Agente con tool use en panel lateral (SSE). Onboarding que crea el perfil de nicho y lanza la ingesta; switch_niche con plan_limits; explain_feature sobre las vistas existentes. Nunca inventa números.

Cierre: usuario nuevo → conversación → perfil → tablero con datos.

## Fase 5 — Deploy + demo (viernes mañana)
> Contenedor en ECS (o demo local si AWS pasa de 2 horas), Supabase Auth activo, Nivel 1 de seguridad aplicado en lo que corre, guion de demo de 5 minutos.

## Fuera del MVP
SQS/CloudFront/WAF completos, BYOK, Facebook real, YouTube, herramienta de pauta (Top Ads del Creative Center), pagos, alertas proactivas.
