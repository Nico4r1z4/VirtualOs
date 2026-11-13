# VirtualOS — Infraestructura de la demo (registro auditable)

Creada el 13 nov 2026. Este documento lista cada recurso, dónde verlo en la consola, cuánto cuesta y cómo cambiarlo o borrarlo. Es una infraestructura de **demo** (una sola máquina); la arquitectura objetivo (ECS + ALB + CloudFront + WAF) está en `ARQUITECTURA.md`.

## Cuentas y aislamiento

| Cosa | Valor |
|---|---|
| Cuenta AWS | **251082597354** (VirtualOS). Es independiente de la cuenta Korpox (442728149924). |
| Organización | Administrada desde la cuenta 827546917499. Una **SCP** (Service Control Policy) solo permite EC2 en **us-east-2 (Ohio)**; cualquier otra región devuelve *explicit deny*. |
| Usuario IAM operador | `VirtualOs-carga`, con la política inline de `deploy/iam-policy-demo.json` |
| Perfil local | `virtualos` en `~/.aws` (las llaves solo viven ahí, nunca en el repo) |
| Servidor MCP del proyecto | `aws-virtualos` en `.mcp.json`, fijado a `AWS_PROFILE=virtualos` |

La política permite crear recursos solo en us-east-2. Detener, borrar o liberar recursos solo se puede si tienen la etiqueta `Project=virtualos`.

## Recursos creados (todos en us-east-2, etiqueta `Project=virtualos`)

| Recurso | ID | Detalle | Consola |
|---|---|---|---|
| Instancia EC2 | `i-0b5ef404705ddabac` | t3.small (2 vCPU, 2 GB), Ubuntu 24.04 (`ami-096d6538c463eb1db`), IMDSv2 obligatorio | EC2 → Instances |
| Disco | (raíz de la instancia) | 20 GB gp3, **cifrado**, se borra junto con la instancia | EC2 → Volumes |
| Elastic IP | `eipalloc-0dc435b1c59017df5` | **3.137.22.45** (fija; sobrevive reinicios) | EC2 → Elastic IPs |
| Security group | `sg-0c6b8235ca9984c37` | 80/443 abiertos a internet; **22 solo desde 181.58.39.74/32** (IP del owner) | EC2 → Security Groups |
| Key pair | `key-075f61565c2c4a4b4` (`virtualos-demo`) | La llave privada está solo en `~/.ssh/virtualos-demo` del owner | EC2 → Key Pairs |

### DNS (Cloudflare)

Registro A `vos.orkiza.com → 3.137.22.45`, en modo **DNS only** (nube gris). Si se activa el proxy naranja, Caddy deja de poder renovar el certificado con el reto TLS-ALPN, así que primero habría que cambiar la configuración.

## Qué corre en la máquina

Hay tres contenedores con Docker Compose en `~/virtualos/deploy/` (ver `deploy/docker-compose.yml`):

- **caddy**: HTTPS automático con Let's Encrypt (se renueva solo). Sirve el frontend estático y hace proxy de la API en el mismo dominio, sin CORS.
- **api**: FastAPI.
- **worker**: procesa la cola de jobs (ingesta, ganchos, brief).

Los secretos están en `~/virtualos/deploy/.env` (permisos `600`). Se copian desde `api/.env` local y nunca pasan por git.

## Costos estimados (us-east-2, on-demand)

| Concepto | USD/mes aprox. |
|---|---|
| t3.small encendida 24/7 | ~15.2 |
| Elastic IP (IPv4 pública) | ~3.6 |
| Disco gp3 20 GB | ~1.6 |
| **Total** | **~20** |

Apagando la instancia, el costo baja a unos 5 USD/mes, porque la IP fija y el disco se siguen cobrando.

## Operación

Entrar por SSH:
```bash
ssh -i ~/.ssh/virtualos-demo ubuntu@3.137.22.45
```

Ver el estado y los logs:
```bash
ssh -i ~/.ssh/virtualos-demo ubuntu@3.137.22.45 "cd ~/virtualos/deploy && sudo docker compose ps && sudo docker compose logs --tail 50"
```

**Redesplegar solo el frontend** (sin caída): corre `./deploy/deploy_web.sh` desde Git Bash. Compila, sube y reemplaza los archivos **dentro** de `web/dist` sin borrar la carpeta, y verifica contra la respuesta real del servidor.

> ⚠️ **Nunca borres `~/virtualos/web/dist` en el servidor.** Caddy la tiene montada; si la carpeta se borra y se recrea, Caddy sigue apuntando a la borrada y todo el sitio responde 404. Pasó el 13 nov y estuvo caído ~5 min. Si vuelve a pasar: `sudo docker compose restart caddy`.

**Redesplegar la API o el worker:** empaqueta `api/` (sin `.venv`, `.env` ni `.data`), cópialo, descomprímelo en `~/virtualos` y corre `sudo docker compose up -d --build api worker`. El script `deploy/deploy.sh` usa rsync, que no viene en Git Bash de Windows; hasta automatizarlo, se usa tar + scp.

**Si cambia tu IP** y no puedes entrar por SSH: en EC2 → Security Groups → `sg-0c6b8235ca9984c37` → Inbound rules, edita la regla del puerto 22 con tu IP nueva.

**Apagar o encender** (desde la consola o con el CLI):
```bash
aws ec2 stop-instances --profile virtualos --region us-east-2 --instance-ids i-0b5ef404705ddabac
```

**Borrar todo** (es irreversible y se pierde la IP 3.137.22.45):
1. Terminar la instancia.
2. Liberar la Elastic IP.
3. Borrar el security group.
4. Borrar el key pair.
5. Borrar el registro A en Cloudflare.

## Pendiente antes de compartir más allá de la demo (Nivel 1 de `ARQUITECTURA.md`)

- Pasar los secretos de `.env` a AWS Secrets Manager.
- Activar alertas de AWS Budgets en esta cuenta.
- Rotar el token de Apify (quedó impreso en un log local el 13 nov; el bug ya está corregido).
- Agregar `https://vos.orkiza.com` a las Redirect URLs de Supabase Auth (paso del owner).
- Configurar CI/CD con un rol OIDC de GitHub y pasar a ECS, según `ARQUITECTURA.md`.
