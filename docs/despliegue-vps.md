# Despliegue de `parking` en el VPS

**Fecha:** 2026-10-26
**Servidor:** `file-server`
**Proyecto:** `parking`
**Ruta local:** `/home/ubuntu/proyectos-docker/opencode/workspace/nuevos/parqueadero`
**URL:** `https://15.204.10.78:8443`
**Estado:** desplegado, accesible y con login del panel verificado.

Este documento registra el despliegue manual del proyecto `parking` (antes
`parqueadero`) en el VPS. El código fue publicado desde Neurobit mediante el flujo
`publicador-repos` de la versión 0.60.0; el despliegue de la aplicación se hizo
manualmente en el host con Docker Compose.

## 1. Versión desplegada

- Rama: `main`.
- Commit de referencia: `25910d0` (`Actualiza dependencias vulnerables y valida la
  suite completa (36 pruebas)`).
- Verificación: `git -C ~/proyectos-docker/opencode/workspace/nuevos/parqueadero rev-parse HEAD`.
- Imágenes construidas:
  - `parking-backend:latest`
  - `parking-frontend:latest`
- Contenedores:
  - `parking-backend-1` — escucha `8000/tcp` solo dentro de la red.
  - `parking-frontend-1` — publica `0.0.0.0:8443->443/tcp`.
- Proyecto Compose: `parking`.
- Red: `parking_interna` con subred `172.30.0.0/16`.
- Volúmenes:
  - `parking_datos` — base SQLite (`/datos/parqueadero.db`).
  - `parking_certificados` — certificado TLS autofirmado.

## 2. Archivos de despliegue

| Archivo | Estado | Uso |
|---|---|---|
| `docker-compose.yml` | versionado | Base de backend/frontend. Publica 80/443 y usa `172.28.0.0/16`. |
| `docker-compose.port.yml` | **no versionado** | Override efectivo del VPS: `8443:443` y red `172.30.0.0/16`. |
| `docker-compose.deploy.yml` | **eliminado** | Copia completa creada durante la prueba; no se versionó. |
| `.env` | **ignorado por git**, modo 600 | Token del panel y variables del despliegue. No se documenta su valor. |

Contenido efectivo del override:

```yaml
services:
  frontend:
    ports: !override
      - "8443:443"

networks:
  interna:
    ipam:
      config: !override
        - subnet: 172.30.0.0/16
```

> `!override` requiere una versión reciente de Docker Compose. En el VPS se usó
> **v5.0.2**.

## 3. Variables del `.env`

Claves presentes (sin incluir el valor del token):

```env
PARQUEADERO_TOKEN=<secreto de 43 caracteres; no documentar>
PARQUEADERO_ORIGENES=https://15.204.10.78:8443,https://localhost
PARQUEADERO_ENTORNO=desarrollo
PARQUEADERO_HSTS=max-age=300
PARQUEADERO_CERT_SAN=IP:15.204.10.78
```

> **Pendiente recomendado:** añadir `PARQUEADERO_PROXIES=172.30.0.0/16`.
> En el `.env` actual no está definido, por lo que el backend usa el valor por
> defecto `172.28.0.0/16`, que no coincide con la red del override (`172.30`). La
> aplicación funciona, pero el limitador de tasa no está reconociendo la IP real
> del cliente detrás de nginx. Después de añadirlo hay que recrear el backend.

El token del panel **no** es el token de GitHub. El de GitHub vive en el `.env` de
Neurobit; este es el token compartido del panel de Parqueadero.

## 4. Comando de despliegue

Desde el repositorio:

```bash
cd ~/proyectos-docker/opencode/workspace/nuevos/parqueadero

docker compose -p parking \
  -f docker-compose.yml \
  -f docker-compose.port.yml \
  up -d --build
```

Verificación:

```bash
docker compose -p parking \
  -f docker-compose.yml \
  -f docker-compose.port.yml \
  ps

sleep 5
curl -kfsS https://127.0.0.1:8443/api/salud
curl -kfsS -o /dev/null -w '%{http_code}\n' https://127.0.0.1:8443/
```

Resultado confirmado:

```text
{"estado":"ok"}
200
```

El 502 inicial fue transitorio: nginx arrancó antes de que el backend terminara de
iniciar. Se resolvió al esperar unos segundos.

## 5. Acceso y autenticación

- URL: `https://15.204.10.78:8443`
- El certificado es autofirmado; el navegador mostrará una advertencia. Es esperado
  con `PARQUEADERO_ENTORNO=desarrollo`.
- El panel pide un **token**, no usuario/contraseña.
- El token es `PARQUEADERO_TOKEN` del `.env` de `parking` (mínimo 32 caracteres).
- El frontend lo guarda en `sessionStorage` (`parqueadero_token`) y lo envía como:
  ```http
  Authorization: Bearer <token>
  ```
- La API también acepta `X-API-Key: <token>`.
- Solo `/api/salud` es público.
- `401`: token inválido o ausente; el frontend lo borra y vuelve a pedirlo.
- `503`: `PARQUEADERO_TOKEN` ausente o con menos de 32 caracteres.
- No hay usuarios, roles ni expiración de sesión: es un secreto compartido. Cerrar
  la pestaña/navegador borra el `sessionStorage` y vuelve a pedir el token.

Para leer el token actual (sin documentarlo):

```bash
grep '^PARQUEADERO_TOKEN=' .env
```

Si el token apareció en un chat, ticket o log, **rotarlo**:

```bash
python3 -c 'import secrets; print(secrets.token_urlsafe(32))'
# Reemplazar PARQUEADERO_TOKEN en .env
docker compose -p parking \
  -f docker-compose.yml \
  -f docker-compose.port.yml \
  up -d --force-recreate backend
```

## 6. Incidencias y decisiones

### Conflicto de subred Docker

El `docker-compose.yml` base fija `172.28.0.0/16`. En el servidor ya existía:

```text
evolution_evolution-net  172.28.0.0/16
```

El primer `up` falló con:

```text
invalid pool request: Pool overlaps with other one on this address space
```

Solución: el override usa `172.30.0.0/16` (`parking_interna`). No hay otra red con
esa subred en el host.

### 502 inicial

Nginx aceptó TLS, pero el `curl` se ejecutó antes de que el backend estuviera listo.
El `ps` mostraba `Up Less than a second`. Tras esperar, `/api/salud` respondió 200.
No era un fallo del token ni de la base SQLite.

### `--forwarded-allow-ips` y `PARQUEADERO_PROXIES`

El `Dockerfile` del backend fija:

```text
--forwarded-allow-ips 172.28.0.0/16
```

Con la red en `172.30`, uvicorn no reescribe `request.client` con la IP del cliente.
La aplicación tiene su propia validación (`PARQUEADERO_PROXIES`) para el limitador;
por eso el panel funciona. Para dejarlo coherente:

1. Añadir `PARQUEADERO_PROXIES=172.30.0.0/16` al `.env`.
2. Recrear el backend.
3. A medio plazo, parametrizar `--forwarded-allow-ips` en el Dockerfile/compose para
   que use la misma subred.

### Archivos temporales

- `docker-compose.port.yml` es el override efectivo. No contiene secretos; puede
  versionarse si se quiere hacer reproducible el despliegue.
- `docker-compose.deploy.yml` fue una copia de prueba y se eliminó; no se versiona.
- El `.env` está en `.gitignore`; no se versiona.

## 7. Operación

Detener sin borrar datos:

```bash
docker compose -p parking \
  -f docker-compose.yml \
  -f docker-compose.port.yml \
  stop
```

No usar `down -v`: borraría `parking_datos` y `parking_certificados`.

Logs:

```bash
docker compose -p parking \
  -f docker-compose.yml \
  -f docker-compose.port.yml \
  logs --tail=120 backend

docker compose -p parking \
  -f docker-compose.yml \
  -f docker-compose.port.yml \
  logs --tail=120 frontend
```

Diagnóstico directo del backend:

```bash
docker exec parking-backend-1 python -c \
  "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8000/api/salud').status)"

docker exec parking-frontend-1 wget -qO- http://backend:8000/api/salud
docker exec parking-frontend-1 cat /var/log/nginx/error.log
```

## 8. Pendientes recomendados

1. **Healthcheck:** añadir al backend:
   ```yaml
   healthcheck:
     test:
       - CMD
       - python
       - -c
       - "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/salud')"
     interval: 2s
     timeout: 3s
     retries: 20
   ```
   y hacer que el frontend dependa de `condition: service_healthy`. Desplegar con
   `--wait` para evitar el 502 inicial.
2. **Proxy real:** añadir `PARQUEADERO_PROXIES=172.30.0.0/16` y recrear el backend;
   idealmente parametrizar `--forwarded-allow-ips`.
3. **TLS real:** para producción, usar un dominio y un certificado real, con
   `PARQUEADERO_ENTORNO=produccion`. El autofirmado es solo para esta prueba.
4. **Firewall:** restringir `8443/tcp` en el firewall/cloud security group a las IPs
   de confianza.
5. **Rotar el token** si el valor actual estuvo expuesto.
6. **Despliegue automático por el agente:** no implementado. La Secretaría puede
   revisar el repositorio, pero no ejecutar Docker en el host. La siguiente fase es
   el helper host-side con cola de solicitudes, allowlist de proyectos/puertos,
   healthcheck y aprobación humana; sin montar el socket Docker en el contenedor
   `api`.

## 9. Rollback

```bash
# Volver al código/imagen anterior del proyecto
cd ~/proyectos-docker/opencode/workspace/nuevos/parqueadero
git checkout <commit_anterior>
docker compose -p parking \
  -f docker-compose.yml \
  -f docker-compose.port.yml \
  up -d --build
```

Los datos de `parking_datos` se conservan. El certificado de `parking_certificados`
se puede regenerar solo si cambia el SAN/IP:

```bash
docker compose -p parking \
  -f docker-compose.yml \
  -f docker-compose.port.yml \
  down

docker volume rm parking_certificados

docker compose -p parking \
  -f docker-compose.yml \
  -f docker-compose.port.yml \
  up -d --build
```

No borrar `parking_datos` salvo que se quiera perder la base.
