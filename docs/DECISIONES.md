# VirtualOS — Registro de decisiones

- 11 nov — Nombre: VirtualOS. Usuarios: creadores, compañías y agencias (multimercado).
- 11 nov — Plataformas foco: TikTok, Instagram, Facebook. YouTube fuera del MVP.
- 12 nov — Infra mixta: Supabase (Postgres + Auth) + AWS (cómputo, colas, S3, red). Migrable después.
- 12 nov — Backend en Python. Se reutiliza infraestructura del scraper copiando módulos; el repo original no se toca.
- 12 nov — Datos sociales vía proveedores de terceros (Apify) detrás de conectores. Scraping propio solo después, para las rutas de mayor volumen ("comprar ahora, construir después").
- 12 nov — Embudo de costo: el código filtra (outliers, ranking) y la IA solo procesa lo que ganó. No se replica el patrón Pasada A/B con LLM del scraper.
- 12 nov — Transcripción: subtítulos del proveedor; si no, faster-whisper local. MarkItDown descartado (sin video, audio básico vía servicio de Google).
- 12 nov — Modelos de IA por API (pago por uso). Creadores: IA incluida con topes por plan. Empresas: opción futura de traer su propia llave (BYOK) con modelos certificados, panel de consumo y llaves cifradas con KMS. `LLMProvider` desde el día 1.
- 12 nov — Posicionamiento: herramienta profesional tipo Adobe, no genérica. UI centrada en herramientas; la mascota en panel lateral.
- 12 nov — Mascota: onboarding con perfil anclado; única vía para cambiar de nicho con límites por plan; copiloto experto; check-ins proactivos y feedback post-grabación.
- 12 nov — Alcance del viernes: profundidad sobre amplitud (tablero de outliers + ganchos, brief semanal, mascota en onboarding).
