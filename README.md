# Strix History Dashboard

Aplicación web local y de solo lectura para explorar los artefactos de
`PATH_STRIX/strix_runs`. El backend Python consume el contrato versionado de
`strix_runner.py history --all --json`; el frontend React no recibe rutas del
sistema de archivos ni puede iniciar, modificar o borrar ejecuciones.

## Relación con strix-runner

Este dashboard es un repositorio independiente del runner. Por defecto busca
`strix_runner.py` en la carpeta hermana `strix-runner`:

```text
proyectos/
├── strix-runner/
└── strix-runner-dashboard/
```

Si prefieres otra ubicación, define la variable de entorno `STRIX_RUNNER_PATH`:

```bash
export STRIX_RUNNER_PATH=/ruta/a/strix_runner.py
```

También puedes usar `STRIX_DASHBOARD_RUNNER`, que tiene prioridad sobre
`STRIX_RUNNER_PATH`.

## Estructura

```text
.
├── backend/   FastAPI, caché y acceso seguro a informes
└── frontend/  React, TypeScript y Vite
```

## Preparación

Requisitos de desarrollo:

- Python 3.12 y `uv`.
- Node.js y Corepack.

Desde la raíz de este repositorio:

```bash
uv sync --project backend --group dev
cd frontend
corepack pnpm install
corepack pnpm build
cd ..
```

El directorio compilado `frontend/dist` es local y no se versiona.

## Ejecución

```bash
uv run --project backend strix-dashboard
```

Abre <http://127.0.0.1:8765>. El backend utiliza la misma configuración que el
runner, incluida la variable `STRIX_RUNNER_CONFIG`. Debe ejecutarse en el mismo
entorno de rutas que `strix_runner.py`; por ejemplo, si la configuración utiliza
rutas `/mnt/c/...`, inicia también el dashboard desde WSL.

Opciones principales:

```text
--config ARCHIVO      Configuración alternativa del runner
--runner ARCHIVO      Ruta alternativa a strix_runner.py
--frontend DIRECTORIO
--cache-ttl SEGUNDOS
--host HOST
--port PUERTO
```

El servidor rechaza direcciones distintas de localhost salvo que se indique
expresamente `--allow-remote`. Esa opción no añade autenticación; no debe usarse
en una red compartida sin una capa de acceso externa.

## Desarrollo del frontend

Con el backend escuchando en el puerto 8765:

```bash
cd frontend
corepack pnpm dev
```

Vite sirve la interfaz en `http://127.0.0.1:5173` y reenvía `/api` al backend.

## API de solo lectura

```text
GET /api/v1/health
GET /api/v1/summary
GET /api/v1/facets
GET /api/v1/runs
GET /api/v1/runs/{stable_id}
GET /api/v1/runs/{stable_id}/report
```

El listado admite filtros por aplicación, estado, agente, skill, utilidad,
fechas y texto, además de orden y paginación. Los informes se resuelven mediante
un ID opaco y se validan contra `strix_runs`; la API nunca acepta rutas del
navegador.

## Verificación

```bash
uv run --project backend \
  python -m unittest discover -s backend/tests -v
cd frontend && corepack pnpm build
```

Las pruebas usan artefactos temporales y no ejecutan Strix ni acceden a redes
externas.

## Licencia

Este proyecto está licenciado bajo
[Creative Commons Attribution-NonCommercial 4.0 International](LICENSE).

- **Uso personal e individual**: libre, con atribución al autor y sin fines
  comerciales.
- **Uso por organizaciones**: cualquier uso por parte de empresas,
  instituciones, asociaciones, fundaciones, entidades públicas o privadas, o
  cualquier otra persona jurídica —incluido el uso interno, académico o sin
  fines de lucro directo— requiere **autorización previa y expresa del
  autor**.

Consulta el [adendum de licencia](LICENSE-ADDENDUM.md) para más detalles.
