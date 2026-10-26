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

## Seguridad

- **Autenticación por token:** todos los endpoints del panel (tarifas, tickets e
  informes) exigen `Authorization: Bearer <token>` o `X-API-Key: <token>`, con el
  token definido en `PARQUEADERO_TOKEN`. Solo `/api/salud` es público. Si el token
  no está configurado, la API **falla cerrada** (503). El panel pide el token una
  vez y lo guarda en `sessionStorage`.
- **CORS restringido:** los orígenes permitidos se definen en
  `PARQUEADERO_ORIGENES` (lista separada por coma); ya no se usa `*`.
- **Cabeceras de seguridad:** la API añade `X-Content-Type-Options`,
  `X-Frame-Options`, `Referrer-Policy`, `Content-Security-Policy`,
  `Strict-Transport-Security`, `Permissions-Policy` y `Cross-Origin-Opener-Policy`;
  nginx hace lo propio con el frontend.
- **Límite de tasa:** `PARQUEADERO_RATE_LIMIT=MAXIMO/VENTANA_SEGUNDOS` (por defecto
  `120/60`) limita las peticiones por IP a `/api` y responde `429` con `Retry-After`.
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
│   ├── tsconfig.json
│   ├── vite.config.ts
│   ├── nginx.conf
│   └── Dockerfile
├── docker-compose.yml
├── .env.example
└── README.md
```

## Ejecución con Docker

```bash
docker compose up --build
```

- Frontend y panel: http://localhost:8080

El backend no expone puerto al host: nginx le hace de proxy en `/api`. Por eso la
documentación interactiva (`/docs`) solo está disponible en la ejecución local.

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
| `PARQUEADERO_TOKEN` | Token del panel (obligatorio) | (ninguno) |
| `PARQUEADERO_ORIGENES` | Orígenes CORS permitidos (coma) | `http://localhost:8080,http://localhost:5173` |
| `PARQUEADERO_RATE_LIMIT` | Límite de tasa `MAXIMO/VENTANA_SEGUNDOS` | `120/60` |
