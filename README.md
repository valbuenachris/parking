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

- Frontend: http://localhost:8080
- API y documentación interactiva: http://localhost:8000/docs

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
