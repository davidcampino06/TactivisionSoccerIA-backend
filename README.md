# TactivisionSoccerIA-backend

Backend de **TactiVision IA** (Python + FastAPI + SQLAlchemy + PostgreSQL/Neon).

```
Frontend → Backend → PostgreSQL
Frontend → Backend → AI Service      (el Frontend NUNCA llama al AI Service)
```

## Estructura

```
main.py              app FastAPI, CORS, routers, /api/hello y /api/status (prototipo conservado)
config.py            variables de entorno (DATABASE_URL o NEON_DB_*; JWT; AI_SERVICE_*)
database.py          engine/sesiones SQLAlchemy + estado de la DB
models.py            entidades = tablas del ERD (TactiSoccerIA-db/sql/schema.sql)
schemas.py           contratos Pydantic de la API
security.py          bcrypt + JWT (acceso y recuperación de contraseña)
dependencies.py      usuario actual, roles y TeamAccessPolicy (reglas de equipo)
data_structures.py   Stack, Queue, DoublyLinkedList
singleton.py         SingletonMeta
create_admin.py      crea la cuenta ADMINISTRATOR preconfigurada
routers/             endpoints por módulo
services/            lógica de negocio y patrones
tests/               pytest contra PostgreSQL real + e2e_check.py
```

## Patrones de diseño y estructuras de datos (cada uno resuelve una necesidad real)

| Patrón / estructura | Dónde | Necesidad que resuelve |
|---|---|---|
| **Facade** | `services/analysis_facade.py` · AI: `pipeline.py` | Un solo punto de entrada para todo el caso de uso "Analizar video" |
| **State** | `services/analysis_state.py` | Estados de VideoAnalysis (PENDING→PROCESSING→COMPLETED/FAILED/CANCELLED); transiciones ilegales → 409 |
| **Observer** | `services/analysis_events.py` | Notificar cambios de análisis y alertas tácticas HIGH sin acoplar el Facade a los receptores |
| **Strategy** | AI: `tactical_analysis.py` | Cada familia de indicadores tácticos es intercambiable/extensible |
| **Factory Method** | `services/ai_client.py` (`create_client`) · AI: `DetectorFactory` | Crear el cliente IA / el detector (YOLO26n, YOLO11n, RT-DETR) sin depender de clases concretas |
| **Abstract Factory** | `services/ai_client.py` (`AnalysisSourceFactory`) | Crea la FAMILIA cliente + validador coherente: datos reales nunca se validan como simulados ni al revés |
| **Decorator** | `RetryingAIClient`, `LoggingAIClient` | Reintentos (Render "despertando") y medición de tiempo sobre cualquier cliente, sin modificarlo |
| **Adapter** | `services/ai_result_adapter.py` · AI: `ByteTrackTracker` | Traduce el JSON del AI Service a las tablas del ERD / adapta la librería `supervision` |
| **Bridge** | `services/reports.py` (`ReportView` × `ReportExporter`) | Tipos de reporte (Match, Analysis, Evolution) y formatos (JSON, CSV) crecen por separado |
| **Builder** | `services/reports.py` (`ReportBuilder` + `ReportDirector`) | El snapshot del reporte se arma por secciones; los 3 tipos reutilizan el mismo builder |
| **Prototype** | `services/tactical_versions.py` | Una nueva versión de jugada táctica es un clon profundo de otra + cambios; el original no se altera |
| **Singleton** | `singleton.py` → `AnalysisJobQueue`, `NotificationCenter`, `TeamNotificationInbox` | Una única cola/worker y un único bus de eventos por proceso |
| **Array** | listas de detecciones/indicadores; NumPy en el AI Service | Colecciones ordenadas e indexadas (frames, cajas, valores) |
| **Stack (pila)** | `undo_version` | "Deshacer" la versión actual de una jugada vuelve a la anterior (LIFO) |
| **Queue (cola)** | `services/analysis_queue.py` | Los análisis se procesan en orden de llegada, uno a la vez (FIFO); el usuario ve su posición |
| **Lista doblemente enlazada** | `services/match_timeline.py` | Línea de tiempo de partidos: anterior/siguiente y deltas entre partidos consecutivos (evolución) |

Principios OOP/SOLID: encapsulamiento (`TeamAccessPolicy`, `AnalysisStateMachine`), abstracción
(`AIAnalysisClient`, `ReportExporter`, `ObjectDetector`), polimorfismo (estados, estrategias,
exportadores), composición (Facade y decoradores), SRP (un servicio por responsabilidad), OCP
(nuevas estrategias/exportadores/observadores sin tocar código existente), DIP (routers dependen
de abstracciones).

## Reglas de seguridad (validadas en Backend)

- Registro solo como `COACH` o `ANALYST`. `ADMINISTRATOR` se crea con `create_admin.py`.
- Un COACH tiene un único equipo (`teams.coach_id` UNIQUE) y solo administra ese.
- Un ANALYST entra con código de invitación (`BARCE-7K29`) y solo accede a ese equipo; no puede
  gestionar jugadores, jugadas ni borrar.
- ADMINISTRATOR gestiona usuarios y ve equipos registrados (`/api/admin/teams`, sin código ni
  contenido táctico); recibe 403 en jugadores, partidos, videos, análisis y reportes.
- Contraseñas con bcrypt; JWT firmado con `JWT_SECRET_KEY`; token de recuperación de un solo uso.
- Logout: JWT es stateless; el cliente elimina el token (expira según `ACCESS_TOKEN_EXPIRE_MINUTES`).

## Endpoints principales

| Módulo | Endpoints |
|---|---|
| Sistema | `GET /api/hello`, `GET /api/status` (backend, database, ai_service) |
| Auth | `POST /api/auth/register · login · logout · password-recovery · password-reset · change-password`, `GET/PUT /api/auth/me` |
| Admin | `GET /api/admin/users`, `PATCH /api/admin/users/{id}`, `GET /api/admin/teams` |
| Equipos | `POST /api/teams`, `GET /api/teams/mine`, `POST /api/teams/join`, `GET/PUT /api/teams/{id}`, `POST /api/teams/{id}/invitation-code`, `GET/DELETE /api/teams/{id}/analysts[/{userId}]` |
| Jugadores | `GET/POST /api/teams/{id}/players`, `GET/PUT/DELETE /api/players/{id}`, `GET /api/players/{id}/history` |
| Partidos | `GET/POST /api/teams/{id}/matches`, `GET/PUT/DELETE /api/matches/{id}`, `PUT .../result`, `GET .../neighbors`, eventos, formaciones, jugadas |
| Diseño táctico | `GET/POST /api/formations`, `GET/POST /api/teams/{id}/tactical-plays`, versiones: crear (clon), activar, `undo` |
| Videos | `POST/GET /api/matches/{id}/videos`, `GET/DELETE /api/videos/{id}`, **`POST /api/videos/{id}/analysis`** (202) |
| Análisis | `GET /api/analyses/{id}`, `/result`, `/indicators`, `/detections`, `/tracks`, `PUT /tracks/{trackId}/player`, `POST /cancel` |
| Recomendaciones | `GET /api/matches/{id}/recommendations`, `PATCH /api/recommendations/{id}` (review/confirm/dismiss) |
| Comparación | `GET /api/teams/{id}/comparisons?match_ids=a&match_ids=b` (≥2), `GET /api/teams/{id}/evolution` (≥3) |
| Reportes | `POST/GET /api/teams/{id}/reports`, `GET /api/reports/{id}`, `GET /api/reports/{id}/export?format=json|csv` |
| Notificaciones | `GET /api/notifications` |

Documentación interactiva: http://localhost:8000/docs

## Ejecutar localmente

```bash
cd TactivisionSoccerIA-backend
python -m venv .venv && .venv\Scripts\activate          # Linux/Mac: source .venv/bin/activate
pip install -r requirements-dev.txt
copy .env.example .env                                   # completar DATABASE_URL, JWT_SECRET_KEY, AI_SERVICE_*
psql "%DATABASE_URL%" -f ../TactiSoccerIA-db/sql/schema.sql
python create_admin.py                                   # con ADMIN_EMAIL y ADMIN_PASSWORD en el entorno
uvicorn main:app --reload --port 8000
```

`AI_SERVICE_API_KEY` debe ser el mismo valor en Backend y AI Service.

## Tests

```bash
# Base de datos de prueba VACÍA (se reinicia en cada ejecución)
set TEST_DATABASE_URL=postgresql://postgres:postgres@localhost:5432/tactivision_test
python -m pytest -q

# Integración real (AI Service en :8001 y Backend en :8000 corriendo)
python tests/e2e_check.py ruta/a/video.mp4
```

## Limitaciones actuales

- Videos guardados en disco local (`UPLOAD_DIR`). En Render Free el disco es efímero: para
  producción se necesita un disco persistente o almacenamiento de objetos.
- Notificaciones en memoria (se pierden al reiniciar). La cola también; al arrancar, los análisis
  PROCESSING se marcan FAILED y los PENDING se re-encolan.
- Recuperación de contraseña sin servicio de correo (token visible solo con
  `PASSWORD_RESET_EXPOSE_TOKEN=true` en desarrollo). Exportación PDF pendiente (JSON y CSV listos).
