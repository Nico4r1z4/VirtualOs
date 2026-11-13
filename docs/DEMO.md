# VirtualOS — Guion de demo (5 minutos)

**URL:** https://vos.orkiza.com · **Nicho cargado:** "Finanzas personales Colombia" (TikTok + Instagram, CO)

## Antes de empezar (checklist)

- [ ] Agregar `https://vos.orkiza.com` a las Redirect URLs de Supabase Auth, o el magic link vuelve a localhost.
- [ ] Entrar una vez con tu correo en https://vos.orkiza.com y confirmar que el tablero muestra datos.
- [ ] Si Eduardo va a entrar con su propio correo, debe hacerlo **antes** para que Claude lo agregue al workspace de la demo. Si no, verá un workspace vacío.
- [ ] Tener abiertas dos pestañas: Outliers y Brief.

## Guion

**1. El problema (30 s).** Los creadores y las agencias graban a ciegas. No saben qué está funcionando *esta semana* en su nicho ni por qué funcionó.

**2. Tablero de Outliers (90 s).** Muestra lo que el nicho premió esta semana.
- El multiplicador compara las vistas de cada post con la **mediana de su propio autor**, no con un promedio general.
- Filtra con el chip "3×" → quedan unos 21 posts sobre-rindiendo.
- Abre el primero: @finanzas.emocionales, **41×** su mediana. Muestra métricas, hashtags y el gancho detectado.
- Mensaje clave: *"esto lo calcula el código, sin IA. La IA solo trabaja sobre lo que ganó."* Es el embudo de costo.

**3. Biblioteca de ganchos (60 s).** Por qué ganó cada post.
- 29 ganchos analizados, solo de outliers, cada uno con su tipo (pregunta, tutorial, dato impactante...), su estructura por beats y su CTA.
- Filtra por "tutorial" para mostrar el patrón que más se repite en el nicho.

**4. Brief semanal (90 s).** El entregable.
- Lee el resumen: *"qué está funcionando esta semana"*.
- Recorre 2 ideas, por ejemplo **"50/30/20 vs 70/30: cuál te sirve en Colombia"** y **"Qué hacer con tu plata si viene otra reforma tributaria"**.
- Cada idea trae su gancho sugerido y su guion, y **está enlazada a su evidencia** (post outlier + noticia o tendencia). La IA no puede inventar ideas sin respaldo: si cita evidencia inexistente, la idea se descarta.
- Descarga el PDF.
- Pulsa **"Lo grabé"** en una idea: así se alimenta el loop de feedback, que es el foso competitivo.

**5. La mascota (30 s, opcional).** Abre el panel y pregunta *"¿qué está funcionando en mi nicho?"*. Responde con datos de las herramientas y nunca inventa números.

**6. Cierre (30 s).**
- **Costo real** de todo lo que se vio: unos **US$0.45** (Apify US$0.37 + OpenAI US$0.08), registrado por workspace.
- **Qué sigue:** más cuentas y nichos, refresco automático, alertas proactivas de outliers y la versión para agencias multi-marca.

## Si algo falla en vivo

- **La página no carga:** revisar los contenedores, ver `docs/INFRA.md` → Operación.
- **El login no llega:** revisar las Redirect URLs de Supabase. Como respaldo, mostrar desde una sesión ya iniciada.
- **La mascota no responde:** saltar al paso 6. El tablero y el brief no dependen de ella.
