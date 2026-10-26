# Parqueadero

Aplicación minimalista de gestión de parqueadero: controla entradas y salidas de
vehículos, calcula el cobro según tarifas por hora, emite facturas y genera
informes del negocio.

- **Backend:** Python + FastAPI, persistencia en SQLite (sin ORM).
- **Frontend:** TypeScript + Vite, estilos en CSS puro.
- **Docker:** `Dockerfile` para cada servicio y `docker-compose.yml`.

## Funcionalidad

- Registro de ingreso de vehículos (placa + tipo: auto, moto, camioneta).
- Registro de salida con cálculo del valor por fracciones y emisión de factura.
- Tarifas configurables por tipo de vehículo.
- Listado de vehículos dentro, facturas e informe de lo facturado por rango de fechas.

## Notas técnicas

- Las fechas se almacenan y comparan en **UTC tz-aware** (`...+00:00`); los filtros
  de facturas e informes exigen una zona horaria explícita.
- El dinero se calcula con `Decimal` y se persiste como **enteros en centavos**
  (`*_centavos`) para evitar errores de coma flotante.
- La API **serializa los montos como cadena decimal** (p. ej. `"3000.00"`) en
  lugar de `float`, de modo que el cliente recibe el valor exacto.
- El esquema SQLite usa tablas **STRICT** (requiere SQLite **3.37+**, se
  comprueba al arrancar) con restricciones `CHECK` (montos y tiempos no
  negativos, tarifas positivas) y un **índice único parcial** que impide dos
  tickets abiertos para la misma placa, comparando el texto con `COLLATE
  NOCASE`. Hay un índice en `facturas.hora_salida` para los filtros por fecha.
  La migración sanea antes los montos negativos y los tickets abiertos
  duplicados que no cumplirían las restricciones. Las actualizaciones se
  versionan con `PRAGMA user_version` **dentro de la misma transacción** y se
  aplican solas al arrancar; la conexión usa `journal_mode=WAL` (si el sistema de
  archivos no lo permite, se **registra el fallo** en el log y se continúa con el
  modo por defecto en vez de silenciarlo).

## Seguridad

- **Autenticación por token:** todos los endpoints del panel (tarifas, tickets e
  informes) exigen `Authorization: Bearer <token>` o `X-API-Key: <token>`, con el
  token definido en `PARQUEADERO_TOKEN` (**mínimo 32 caracteres**). Solo
  `/api/salud` es público. Si el token falta o es demasiado corto, la API **falla
  cerrada** (503). El panel pide el token una vez y lo guarda en `sessionStorage`.
- **CORS restringido:** los orígenes permitidos se definen en
  `PARQUEADERO_ORIGENES` (lista separada por coma); ya no se usa `*`.
- **TLS en nginx:** nginx termina TLS en el puerto **443** (con certificado
  autofirmado de desarrollo) y redirige todo el HTTP del puerto 80 a HTTPS. La
  clave privada **no se hornea en la imagen**: el contenedor la genera al
  arrancar dentro de un volumen (`certificados`) y en producción se monta un
  certificado real. El autofirmado incluye un **SAN** con `localhost` y loopback
  (ampliable con `PARQUEADERO_CERT_SAN`) para que el navegador y el CI lo
  acepten. Con `PARQUEADERO_ENTORNO=produccion` **no se genera autofirmado**: si
  falta el certificado, el contenedor falla en vez de servir TLS falso. HSTS se
  envía **solo** sobre HTTPS, tanto en nginx como en la API, con el valor
  parametrizado en `PARQUEADERO_HSTS` (por defecto corto, `max-age=300`, en
  desarrollo; largo en producción). El envsubst de la imagen de nginx se limita a
  esa variable con `NGINX_ENVSUBST_FILTER=PARQUEADERO_HSTS`.
- **IP real acotada:** nginx reescribe `X-Forwarded-For` con `$remote_addr`
  (ignora la cabecera entrante del cliente) y el backend solo acepta esa cabecera
  cuando la conexión directa proviene de una **subred de confianza**
  (`PARQUEADERO_PROXIES`, por defecto `172.28.0.0/16`); en caso contrario usa la
  IP del peer TCP (`request.client.host`), de modo que una `X-Forwarded-For`
  forjada no puede burlar el limitador. uvicorn solo confía en la subred interna
  de Compose (`--forwarded-allow-ips 172.28.0.0/16`), no en `*`.
- **Cabeceras de seguridad:** la API añade `X-Content-Type-Options`,
  `X-Frame-Options`, `Referrer-Policy`, `Content-Security-Policy`,
  `Permissions-Policy` y `Cross-Origin-Opener-Policy`; nginx hace lo propio con
  el frontend.
- **Límite de tasa:** `PARQUEADERO_RATE_LIMIT=MAXIMO/VENTANA_SEGUNDOS` (por defecto
  `120/60`) limita las peticiones por IP real a `/api` y responde `429` con
  `Retry-After`. La IP se toma de `X-Forwarded-For`/`X-Real-IP` **solo** si la
  conexión llega desde una subred de confianza; si no, se usa la IP del peer TCP.
  El diccionario de contadores se purga para no crecer sin límite y la
  configuración se recorta a un tope (`100000` peticiones / `86400` s).
- **Puerto del backend:** el backend ya **no se publica** en el host; solo es
  accesible dentro de la red de Compose a través del proxy de nginx.


## Estructura

```
parqueadero/
├── backend/
│   ├── app/
│   │   ├── database.py     # conexión y esquema SQLite
│   │   ├── models.py       # modelos de dominio
│   │   ├── schemas.py      # esquemas de la API (pydantic)
│   │   ├── services.py     # reglas de negocio (tiempo y tarifa)
│   │   ├── main.py         # aplicación FastAPI
│   │   └── routers/        # tarifas, tickets e informes
│   ├── tests/              # pruebas con pytest
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/
│   ├── src/                # main.ts, api.ts, types.ts, styles.css
│   ├── index.html
│   ├── package.json
│   ├── package-lock.json
│   ├── tsconfig.json
│   ├── vite.config.ts
│   ├── nginx.conf
│   ├── docker-entrypoint.d/  # genera el certificado TLS al arrancar
│   ├── tests/                # verificación del certificado de runtime
│   └── Dockerfile
├── .github/workflows/ci.yml  # CI: pytest, npm ci && npm run build y SAN
├── docker-compose.yml
├── .env.example
└── README.md
```

## Ejecución con Docker

```bash
docker compose up --build
```

- Frontend y panel: https://localhost (el HTTP de http://localhost redirige a HTTPS)

El backend no expone puerto al host: nginx le hace de proxy en `/api`. Por eso la
documentación interactiva (`/docs`) solo está disponible en la ejecución local.

El certificado TLS es autofirmado (se genera al arrancar el contenedor y queda
en el volumen `certificados`, no en la imagen, con SAN para `localhost` y
loopback) y el navegador avisará; para producción define
`PARQUEADERO_ENTORNO=produccion` y monta un certificado real en
`/etc/nginx/certs/fullchain.pem` y `/etc/nginx/certs/privkey.pem`. En producción
no se genera autofirmado: si falta el certificado, el contenedor falla.

Los datos quedan en el volumen `datos` (archivo SQLite).

## Ejecución en local (sin Docker)

Backend:

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r backend/requirements.txt
uvicorn app.main:app --reload --app-dir backend
```

Frontend:

```bash
cd frontend
npm install
npm run dev
```

Durante el desarrollo, Vite hace proxy de `/api` hacia `http://localhost:8000`.

## Pruebas

```bash
pip install -r backend/requirements.txt
pytest backend/tests
```

Las pruebas incluyen la carrera de doble ingreso (con WAL y `busy_timeout`), el
saneo de una base legada con tickets abiertos duplicados y montos negativos, el
índice `COLLATE NOCASE`, el tope de configuración del limitador, el rechazo de
una `X-Forwarded-For` forjada y el valor de HSTS.

El CI (`.github/workflows/ci.yml`) ejecuta `pytest`, `npm ci && npm run build` en
el frontend y verifica el SAN del certificado autofirmado generado en runtime
(con `frontend/tests/verificar-certificado.sh`).

## API principal

Todos los endpoints requieren el token del panel (`Authorization: Bearer <token>`
o `X-API-Key: <token>`), excepto `/api/salud`.

| Método | Ruta | Descripción |
| --- | --- | --- |
| GET | `/api/salud` | Estado del servicio |
| GET | `/api/tarifas` | Lista las tarifas |
| PUT | `/api/tarifas/{tipo_vehiculo}` | Crea o actualiza una tarifa |
| POST | `/api/tickets/ingresos` | Registra la entrada de un vehículo |
| POST | `/api/tickets/{id}/salida` | Registra la salida y emite la factura |
| GET | `/api/tickets/activos` | Vehículos actualmente dentro |
| GET | `/api/tickets/{id}` | Consulta un ticket |
| GET | `/api/facturas` | Lista facturas (filtros `desde`, `hasta`) |
| GET | `/api/informes/resumen` | Totales facturados por rango |

## Variables de entorno

Ver `.env.example`. No incluyas secretos reales en el repositorio.

| Variable | Descripción | Por defecto |
| --- | --- | --- |
| `PARQUEADERO_DB` | Ruta del archivo SQLite | `backend/parqueadero.db` |
| `PARQUEADERO_TOKEN` | Token del panel (obligatorio, mínimo 32 caracteres) | (ninguno) |
| `PARQUEADERO_ORIGENES` | Orígenes CORS permitidos (coma) | `https://localhost,http://localhost:5173` |
| `PARQUEADERO_RATE_LIMIT` | Límite de tasa `MAXIMO/VENTANA_SEGUNDOS` (se recorta a 100000/86400) | `120/60` |
| `PARQUEADERO_ENTORNO` | `desarrollo` o `produccion` (HSTS largo y sin autofirmado en producción) | `desarrollo` |
| `PARQUEADERO_PROXIES` | Subredes de confianza de las que se acepta `X-Forwarded-For` | `172.28.0.0/16` |
| `PARQUEADERO_HSTS` | Valor de la cabecera HSTS que envía nginx sobre HTTPS | `max-age=300` (dev) |
| `PARQUEADERO_CERT_SAN` | Nombres extra para el SAN del certificado autofirmado de desarrollo | (ninguno) |
