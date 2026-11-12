# VirtualOS — Arquitectura, despliegue y seguridad

Decisiones: backend en Python; infraestructura mixta Supabase (Postgres + Auth) + AWS (cómputo, colas, almacenamiento, red); datos sociales vía Apify detrás de conectores.

## Arquitectura objetivo

```
Usuario (navegador)
   │ HTTPS
CloudFront + AWS WAF ──► S3 (frontend React estático)
   │
   └─► ALB ──► ECS Fargate: API FastAPI (mascota, endpoints, webhooks)
                   │  encola (JobQueue)
                   ▼
                 SQS ──► ECS Fargate: Worker (ingesta, transcripción, síntesis)
                   ▲                     │
 EventBridge Scheduler (refrescos)       ├─► Apify (TikTok / IG / FB) ──webhook──► API
                                         ├─► Anthropic (LLM)
                                         ├─► faster-whisper (local en el Worker)
                                         └─► S3 (crudos, audio, PDFs)
 API y Worker ──► Supabase Postgres (RLS por workspace) ; Supabase Auth (JWT)
 Secretos: AWS Secrets Manager · Logs: CloudWatch · Imágenes: ECR
 CI/CD: GitHub Actions ──(OIDC, sin llaves)──► ECR ──► ECS
```

Flujo de ingesta: la mascota crea el perfil de nicho → la API encola jobs → el Worker lanza runs en Apify → Apify llama al webhook al terminar → el Worker normaliza a `Post`, guarda crudos en S3, calcula métricas y dispara la síntesis solo sobre los outliers.

MVP: `JobQueue` con implementación en Postgres (SKIP LOCKED) y todo corriendo en local o en un solo servicio. SQS, CloudFront, WAF y CI/CD completo entran después sin cambiar el diseño.

## Seguridad por niveles

### Nivel 1 — obligatorio antes de compartir el MVP
- AWS: no usar root; MFA en root y usuarios; eliminar/rotar las llaves de administrador en CSV; humanos vía IAM Identity Center; CI con rol OIDC de GitHub; roles de tarea ECS con mínimo privilegio; AWS Budgets con alertas.
- Secretos solo en Secrets Manager; gitleaks en pre-commit; secret scanning en GitHub.
- Auth: Supabase Auth; la API valida el JWT en cada request; RLS en todas las tablas por workspace; service role key solo en backend.
- Red: HTTPS en todo; CORS restringido al dominio; security groups que solo aceptan tráfico del ALB; WAF con reglas administradas y rate limiting.
- Webhooks de Apify verificados con secreto.
- Límites de gasto: tope en Apify, límite en Anthropic, cuotas por workspace de ingesta y de mensajes a la mascota.
- LLM: contenido scrapeado delimitado como no confiable; herramientas del agente acotadas al workspace; ninguna herramienta hace fetch de URLs arbitrarias (anti-SSRF); validación de salidas.

### Nivel 2 — antes de lanzamiento público / cobro
- CloudTrail + GuardDuty; escaneo de imágenes en ECR; Dependabot + pip-audit + npm audit.
- Backups: PITR de Supabase o pg_dump diario a S3 cifrado.
- Legal: términos, política de privacidad, Ley 1581 (habeas data); política de retención; solo datos públicos de creadores.
- Egreso con IP fija (NAT + EIP) para restringir acceso a la DB de Supabase por IP.
- BYOK para empresas: llaves cifradas con KMS, validadas al conectar, nunca devueltas al frontend ni a logs.

### Nivel 3 — escala
- Pentest externo, SSO para agencias, auditoría de accesos, cuentas AWS separadas para dev y prod.
