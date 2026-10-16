# Diagramas UML · TactiVision IA

Diagramas del sistema completo (frontend, backend, servicio de IA y base de datos), escritos en
Mermaid para que GitHub los dibuje y se puedan editar como texto. Los nombres de clases y métodos son
los del código. El diagrama entidad-relación de la base de datos está en el repositorio
`TactiVisionSoccerIA-db`, en `docs/DICCIONARIO_DE_DATOS.md`.

1. [Casos de uso](#1-casos-de-uso)
2. [Despliegue](#2-despliegue)
3. [Componentes del backend](#3-componentes-del-backend)
4. [Clases: análisis de video](#4-clases-análisis-de-video)
5. [Clases: reportes y jugadas](#5-clases-reportes-y-jugadas)
6. [Clases: servicio de IA](#6-clases-servicio-de-ia)
7. [Clases: estructuras de datos](#7-clases-estructuras-de-datos)
8. [Estados de un análisis](#8-estados-de-un-análisis)
9. [Secuencia: analizar un video](#9-secuencia-analizar-un-video)
10. [Secuencia: iniciar sesión](#10-secuencia-iniciar-sesión)
11. [Secuencia: recuperar la contraseña](#11-secuencia-recuperar-la-contraseña)

## 1. Casos de uso

Tres actores humanos y uno externo (el servicio de IA, al que solo llama el backend).

```mermaid
flowchart LR
    coach(["👤 Entrenador"])
    analyst(["👤 Analista"])
    member(["👥 Miembro del equipo"])
    admin(["👤 Administrador"])
    ai(["⚙️ Servicio de IA"])

    coach -- "«generaliza»" --> member
    analyst -- "«generaliza»" --> member

    subgraph sistema["TactiVision IA"]
        direction TB
        uc1(["Registrarse, iniciar sesión<br/>y recuperar la contraseña"])
        uc3(["Crear equipo y<br/>compartir el código"])
        uc4(["Unirse a un equipo<br/>con el código"])
        uc5(["Gestionar partidos,<br/>eventos y jugadores"])
        uc6(["Subir video y<br/>pedir análisis"])
        uc7(["Revisar posibles problemas"])
        uc8(["Diseñar jugadas<br/>en la pizarra"])
        uc9(["Comparar partidos<br/>y ver la evolución"])
        uc10(["Generar y exportar reportes"])
        uc11(["Administrar usuarios<br/>y equipos"])
        uc12(["Ver el estado del sistema"])
    end

    coach --- uc3
    analyst --- uc4
    member --- uc1 & uc5 & uc6 & uc7 & uc8 & uc9 & uc10
    admin --- uc1 & uc11 & uc12
    uc6 -. "«include»" .-> ai
```

El administrador no tiene acceso al contenido táctico de ningún equipo: la API lo rechaza y, además,
Row-Level Security en PostgreSQL no le entrega esas filas.

## 2. Despliegue

```mermaid
flowchart LR
    user["🧑 Navegador<br/>(computador o celular)"]

    subgraph render["Render"]
        fe["Static Site<br/>Frontend React + Vite<br/>regla /* → /index.html"]
        be["Web Service<br/>Backend FastAPI<br/>cola de análisis en memoria"]
        ai["Web Service<br/>AI Service FastAPI<br/>YOLO26n ONNX + ByteTrack"]
    end

    neon[("Neon<br/>PostgreSQL 16<br/>Row-Level Security")]
    brevo["Brevo<br/>correo transaccional"]
    gh["GitHub<br/>4 repositorios + Actions"]

    user -- "HTTPS" --> fe
    user -- "HTTPS + JWT<br/>contraseñas RSA-OAEP" --> be
    be -- "HTTPS + X-API-Key<br/>multipart (video)" --> ai
    be -- "TLS · SET LOCAL ROLE<br/>tactivision_app" --> neon
    be -- "API HTTPS" --> brevo
    gh -- "despliegue automático<br/>al fusionar en main" --> render
```

## 3. Componentes del backend

```mermaid
flowchart TB
    subgraph api["Capa API (routers/)"]
        auth["auth"]
        teams["teams · players · matches"]
        videos["videos · analyses"]
        insights["insights · recommendations"]
        plays["tactical_plays · formations"]
        reports["reports"]
        users["users (admin)"]
        notif["notifications"]
    end

    subgraph cross["Transversal"]
        deps["dependencies.py<br/>usuario actual, roles,<br/>TeamAccessPolicy"]
        sec["security.py · password_crypto.py<br/>password_policy.py"]
        rls["rls.py<br/>SET LOCAL app.current_*"]
        logs["log_setup.py<br/>filtro de secretos"]
    end

    subgraph services["Servicios (services/)"]
        facade["analysis_facade<br/>VideoAnalysisFacade"]
        queue["analysis_queue<br/>AnalysisJobQueue"]
        state["analysis_state<br/>AnalysisStateMachine"]
        events["analysis_events<br/>NotificationCenter"]
        client["ai_client<br/>AnalysisSourceFactory"]
        adapter["ai_result_adapter<br/>AIResultAdapter"]
        rep["reports · report_pdf<br/>ReportDirector, ReportView"]
        ver["tactical_versions<br/>TacticalConfigurationPrototype"]
        prio["review_priority<br/>PriorityQueue"]
        timeline["match_timeline<br/>DoublyLinkedList"]
        login["login_attempts<br/>LoginAttemptTracker"]
        mail["mailer<br/>SmtpMailer / BrevoMailer"]
    end

    db[("models.py + database.py<br/>SQLAlchemy → PostgreSQL")]

    api --> cross
    videos --> facade
    facade --> queue & state & events & client & adapter
    insights --> prio & timeline
    reports --> rep
    plays --> ver
    auth --> login & mail
    services --> db
    cross --> db
```

## 4. Clases: análisis de video

Facade, State, Observer, Singleton, Abstract Factory, Decorator y Adapter trabajando juntos en el
caso de uso más importante.

```mermaid
classDiagram
    direction LR

    class VideoAnalysisFacade {
        -AnalysisJobQueue _queue
        -NotificationCenter _notifications
        +request_analysis(db, video, options) tuple
        +cancel_analysis(db, analysis) VideoAnalysis
        +queue_position(analysis_id) int
        +run_analysis(job) None
    }

    class SingletonMeta {
        <<metaclass>>
        +reset(cls)
    }

    class AnalysisJobQueue {
        <<Singleton>>
        -Queue~AnalysisJob~ _jobs
        +set_handler(handler)
        +submit(job) int
        +position(analysis_id) int
        +discard(analysis_id) bool
    }

    class AnalysisJob {
        +str analysis_id
        +dict options
    }

    class AnalysisStateMachine {
        -VideoAnalysis analysis
        +state AnalysisState
        +transition_to(state)
        +start()
        +complete(warning)
        +fail(reason)
        +cancel()
    }

    class AnalysisState {
        <<abstract>>
        +start(machine)
        +complete(machine, warning)
        +fail(machine, reason)
        +cancel(machine)
    }
    class PendingState
    class ProcessingState
    class CompletedState
    class FailedState
    class CancelledState

    class NotificationCenter {
        <<Singleton>>
        -list~AnalysisObserver~ _observers
        +subscribe(observer)
        +unsubscribe(observer)
        +publish(event)
    }
    class AnalysisObserver {
        <<interface>>
        +update(event)
    }
    class LoggingObserver
    class PersistentNotificationObserver
    class AnalysisEvent {
        +str event
        +str team_id
        +str analysis_id
        +str message
        +str actor_id
    }

    class AnalysisSourceFactory {
        <<abstract>>
        +create_client() AIAnalysisClient
        +create_validator() AIResponseValidator
    }
    class RealVideoSourceFactory
    class SimulationSourceFactory

    class AIAnalysisClient {
        <<interface>>
        +analyze(video_path, options) dict
    }
    class HttpVideoAnalysisClient
    class HttpSimulationClient
    class AIClientDecorator {
        <<abstract>>
        -AIAnalysisClient wrapped
    }
    class RetryingAIClient
    class LoggingAIClient
    class AIResponseValidator {
        +validate(raw_payload) AIAnalysisPayload
    }
    class AIResultAdapter {
        +detection_rows() list
        +indicators() list
        +recommendations() tuple
        +proximity_network_json() str
    }

    SingletonMeta <.. AnalysisJobQueue : metaclass
    SingletonMeta <.. NotificationCenter : metaclass
    VideoAnalysisFacade --> AnalysisJobQueue
    VideoAnalysisFacade --> NotificationCenter
    VideoAnalysisFacade ..> AnalysisStateMachine : crea
    VideoAnalysisFacade ..> AnalysisSourceFactory : usa
    VideoAnalysisFacade ..> AIResultAdapter : usa
    AnalysisJobQueue o-- AnalysisJob

    AnalysisStateMachine --> AnalysisState : estado actual
    AnalysisState <|-- PendingState
    AnalysisState <|-- ProcessingState
    AnalysisState <|-- CompletedState
    AnalysisState <|-- FailedState
    AnalysisState <|-- CancelledState

    NotificationCenter o-- AnalysisObserver
    AnalysisObserver <|.. LoggingObserver
    AnalysisObserver <|.. PersistentNotificationObserver
    NotificationCenter ..> AnalysisEvent : publica

    AnalysisSourceFactory <|-- RealVideoSourceFactory
    AnalysisSourceFactory <|-- SimulationSourceFactory
    AnalysisSourceFactory ..> AIAnalysisClient : crea
    AnalysisSourceFactory ..> AIResponseValidator : crea
    AIAnalysisClient <|.. HttpVideoAnalysisClient
    AIAnalysisClient <|.. HttpSimulationClient
    AIAnalysisClient <|.. AIClientDecorator
    AIClientDecorator <|-- RetryingAIClient
    AIClientDecorator <|-- LoggingAIClient
    AIClientDecorator o-- AIAnalysisClient : envuelve
```

## 5. Clases: reportes y jugadas

Bridge (tipo de reporte × formato), Builder (el contenido del reporte por secciones) y Prototype
(cada versión de una jugada es un clon de la anterior).

```mermaid
classDiagram
    direction LR

    class ReportDirector {
        -ReportBuilder builder
        +match_report(team, author, title, match) dict
        +analysis_report(team, author, title, analysis) dict
        +evolution_report(team, author, title, match_ids) dict
    }
    class ReportBuilder {
        +header(type, title, team, author) ReportBuilder
        +match(match) ReportBuilder
        +events(events) ReportBuilder
        +analysis(analysis) ReportBuilder
        +indicators(indicators) ReportBuilder
        +recommendations(recommendations) ReportBuilder
        +evolution(evolution) ReportBuilder
        +build() dict
    }

    class ReportView {
        <<abstract>>
        +dict snapshot
        +ReportExporter exporter
        +rows()* list
        +content_blocks()* list
        +title() str
        +export() str|bytes
    }
    class MatchReportView
    class AnalysisReportView
    class EvolutionReportView

    class ReportExporter {
        <<abstract>>
        +str media_type
        +str extension
        +render(view)* str|bytes
    }
    class JsonExporter
    class CsvExporter
    class PdfExporter

    ReportDirector --> ReportBuilder : dirige
    ReportView <|-- MatchReportView
    MatchReportView <|-- AnalysisReportView
    ReportView <|-- EvolutionReportView
    ReportView o-- ReportExporter : puente
    ReportExporter <|-- JsonExporter
    ReportExporter <|-- CsvExporter
    ReportExporter <|-- PdfExporter

    class TacticalConfigurationPrototype {
        -dict _configuration
        +from_version(version)$ TacticalConfigurationPrototype
        +clone() TacticalConfigurationPrototype
        +apply_patch(patch) TacticalConfigurationPrototype
        +configuration dict
        +to_json() str
    }
    class TacticalPlay {
        +str id
        +str name
        +str action_type
    }
    class TacticalPlayVersion {
        +int version_number
        +str configuration_data
        +bool is_current
    }
    TacticalPlay "1" *-- "1..*" TacticalPlayVersion : historial
    TacticalConfigurationPrototype ..> TacticalPlayVersion : clona
```

## 6. Clases: servicio de IA

Facade (`VideoAnalysisPipeline`), Factory Method (detector y tracker), Adapter (`ByteTrackTracker`
sobre la librería `supervision`) y Strategy (cada familia de indicadores).

```mermaid
classDiagram
    direction LR

    class VideoAnalysisPipeline {
        <<Facade>>
        +analyze_video(path, options) dict
    }
    class AnalysisOptions {
        +float confidence_threshold
        +int frame_stride
        +int max_frames
        +str team_a_attack_direction
    }

    class DetectorFactory {
        +supported_models()$ list
        +create(model_name, runtime, model_dir, auto_download)$ ObjectDetector
    }
    class ObjectDetector {
        <<abstract>>
        +detect(frame_bgr, confidence_threshold)* list~Detection~
        +describe() dict
    }
    class OnnxYoloDetector
    class UltralyticsDetector

    class TrackerFactory {
        +create(tracker_name, frame_rate)$ ObjectTracker
    }
    class ObjectTracker {
        <<abstract>>
        +update(player_detections)* list~TrackedDetection~
        +reset()
    }
    class ByteTrackTracker {
        <<Adapter>>
    }

    class JerseyColorTeamClassifier {
        +collect(frame_bgr, tracked_players)
        +assign() TeamAssignmentResult
    }

    class TacticalAnalyzer {
        -list~IndicatorStrategy~ strategies
        +analyze(context) list~IndicatorResult~
    }
    class IndicatorStrategy {
        <<abstract>>
        +compute(context)* list~IndicatorResult~
    }
    class TeamShapeStrategy
    class CompactnessStrategy
    class LinesStrategy
    class ZoneOccupationStrategy
    class BallStrategy
    class ProximityNetworkStrategy
    class PossessionPhaseStrategy

    class TacticalInsightGenerator {
        -list~IssueRule~ rules
        +generate(indicators, team_separation) tuple
    }
    class Graph~N~ {
        +add_edge(a, b)
        +bfs(start) dict
        +connected_components() list
        +all_hops() dict
        +diameter() int
    }

    VideoAnalysisPipeline ..> AnalysisOptions
    VideoAnalysisPipeline --> DetectorFactory
    VideoAnalysisPipeline --> TrackerFactory
    VideoAnalysisPipeline --> JerseyColorTeamClassifier
    VideoAnalysisPipeline --> TacticalAnalyzer
    VideoAnalysisPipeline --> TacticalInsightGenerator
    DetectorFactory ..> ObjectDetector : crea
    ObjectDetector <|-- OnnxYoloDetector
    ObjectDetector <|-- UltralyticsDetector
    TrackerFactory ..> ObjectTracker : crea
    ObjectTracker <|-- ByteTrackTracker
    TacticalAnalyzer o-- IndicatorStrategy
    IndicatorStrategy <|-- TeamShapeStrategy
    IndicatorStrategy <|-- CompactnessStrategy
    IndicatorStrategy <|-- LinesStrategy
    IndicatorStrategy <|-- ZoneOccupationStrategy
    IndicatorStrategy <|-- BallStrategy
    IndicatorStrategy <|-- ProximityNetworkStrategy
    IndicatorStrategy <|-- PossessionPhaseStrategy
    ProximityNetworkStrategy ..> Graph : construye y recorre
```

## 7. Clases: estructuras de datos

Implementadas a mano (no son las de la librería estándar) y cada una con sus pruebas.

```mermaid
classDiagram
    direction LR

    class Stack~T~ {
        <<backend>>
        -list items
        +push(item)
        +pop() T
        +peek() T
        +is_empty() bool
    }
    class Queue~T~ {
        <<backend>>
        +enqueue(item) int
        +dequeue(timeout) T
        +position_of(item) int
        +remove(item) bool
    }
    class DoublyLinkedList~T~ {
        <<backend>>
        -_Node head
        -_Node tail
        +append(value) _Node
        +prepend(value) _Node
        +remove(node)
        +find(predicate) _Node
        +reversed() Iterator
    }
    class _Node~T~ {
        +T value
        +_Node prev
        +_Node next
    }
    class HashTable~K,V~ {
        <<backend>>
        -list buckets
        +put(key, value)
        +get(key) V
        +remove(key) bool
        +load_factor() float
    }
    class PriorityQueue~T~ {
        <<backend · montículo binario>>
        -list heap
        +from_items(items, key)$ PriorityQueue
        +push(item)
        +pop() T
        +pop_many(count) list
        +as_array() list
    }
    class SlidingWindowRateLimiter {
        <<IA · cola FIFO por cliente>>
        +check(client) float
    }
    class Graph~N~ {
        <<IA · lista de adyacencia + BFS>>
    }
    class Trie~T~ {
        <<frontend>>
        +insert(word, value)
        +search(prefix) TrieSearch
    }
    class BinarySearchTree~K,V~ {
        <<frontend · ABB / AVL>>
        +insert(key, value)
        +searchPath(key) path
        +descending() list
        +range(low, high) RangeResult
        +height() int
    }
    class FrontendStack["Stack (frontend)"] {
        <<inmutable>>
        +push(value) Stack
        +pop() tuple
        +peek() T
    }
    class UndoHistory~S~ {
        <<frontend · dos pilas>>
        +record(label, before) UndoHistory
        +undo(current) result
        +redo(current) result
    }

    DoublyLinkedList *-- _Node
    UndoHistory *-- "2" FrontendStack : deshacer / rehacer
    LoginAttemptTracker --> HashTable
    review_queue ..> PriorityQueue
    MatchTimeline --> DoublyLinkedList
    AnalysisJobQueue --> Queue
    class LoginAttemptTracker
    class review_queue {
        <<función>>
    }
    class MatchTimeline
    class AnalysisJobQueue
```

## 8. Estados de un análisis

Patrón State: cada estado decide qué transiciones acepta; una transición ilegal responde 409.

```mermaid
stateDiagram-v2
    [*] --> PENDING : POST /api/videos/{id}/analysis
    PENDING --> PROCESSING : el trabajador toma el análisis de la cola
    PENDING --> CANCELLED : el usuario cancela
    PENDING --> PENDING : el servidor se reinició (vuelve a la cola)
    PROCESSING --> COMPLETED : la IA respondió y se guardó todo
    PROCESSING --> FAILED : error de la IA, respuesta inválida o reinicio del servidor
    PROCESSING --> CANCELLED : el usuario cancela (se descarta el resultado)
    COMPLETED --> [*]
    FAILED --> [*]
    CANCELLED --> [*]
```

## 9. Secuencia: analizar un video

```mermaid
sequenceDiagram
    autonumber
    actor U as Entrenador / Analista
    participant FE as Frontend
    participant API as Backend (routers/videos)
    participant F as VideoAnalysisFacade
    participant Q as AnalysisJobQueue
    participant W as Trabajador (hilo)
    participant AI as AI Service
    participant DB as PostgreSQL

    U->>FE: Elige el video y "Analizar"
    FE->>API: POST /api/videos/{id}/analysis (JWT)
    API->>API: TeamAccessPolicy: ¿es de su equipo?
    API->>F: request_analysis(video, options)
    F->>DB: INSERT video_analyses (PENDING)
    F->>Q: submit(job)
    Q-->>F: posición en la cola
    F-->>API: análisis + posición
    API-->>FE: 202 Accepted
    FE->>FE: muestra "En cola, posición N"

    Q->>W: dequeue() (FIFO)
    W->>DB: PENDING → PROCESSING (State)
    W->>AI: POST /api/analyze (video + X-API-Key)<br/>RetryingAIClient reintenta si Render está despertando
    AI->>AI: detectar (YOLO) → seguir (ByteTrack) → equipos → indicadores (Strategy) → reglas
    AI-->>W: JSON con detecciones, indicadores, problemas y red de cercanía
    W->>W: AIResponseValidator + AIResultAdapter
    W->>DB: INSERT detecciones, indicadores, recomendaciones · COMPLETED
    W->>DB: notificación del equipo (Observer)

    loop mientras no termine
        FE->>API: GET /api/analyses/{id}
        API-->>FE: estado
    end
    FE->>API: GET /api/analyses/{id}/result
    API-->>FE: problemas con evidencia y confianza, indicadores, red
```

## 10. Secuencia: iniciar sesión

```mermaid
sequenceDiagram
    autonumber
    actor U as Usuario
    participant FE as Frontend
    participant API as Backend (routers/auth)
    participant T as LoginAttemptTracker (HashTable)
    participant DB as PostgreSQL

    FE->>API: GET /api/auth/public-key
    API-->>FE: clave pública RSA
    U->>FE: correo + contraseña
    FE->>FE: cifra la contraseña con RSA-OAEP
    FE->>API: POST /api/auth/login (correo, contraseña cifrada)
    API->>API: descifra con la clave privada
    API->>T: seconds_locked(correo)
    alt cuenta bloqueada
        API-->>FE: 429 ACCOUNT_LOCKED (minutos restantes)
    else
        API->>DB: SELECT usuario por correo
        API->>API: bcrypt.verify(contraseña, hash)
        alt contraseña incorrecta
            API->>T: record_failure(correo)
            API-->>FE: 401 con intentos restantes (al quinto fallo, 429 y bloqueo de 15 min)
        else cuenta desactivada
            API-->>FE: 403
        else correcto
            API->>T: record_success(correo)
            API-->>FE: 200 JWT de acceso
            FE->>FE: guarda el token y programa el cierre al vencer
        end
    end
```

## 11. Secuencia: recuperar la contraseña

```mermaid
sequenceDiagram
    autonumber
    actor U as Usuario
    participant FE as Frontend
    participant API as Backend
    participant M as Mailer (Strategy: Brevo o SMTP)
    participant B as Brevo

    U->>FE: "Olvidé mi contraseña" + correo
    FE->>API: POST /api/auth/password-recovery
    API->>API: JWT de recuperación con huella del hash actual (sirve una sola vez)
    API->>M: send(MailMessage con el enlace)
    M->>B: POST /v3/smtp/email
    API-->>FE: 202 (la misma respuesta exista o no la cuenta)
    B-->>U: correo con el enlace /restablecer?token=…
    U->>FE: abre el enlace y escribe la nueva contraseña
    FE->>API: POST /api/auth/password-reset (token, contraseña cifrada RSA)
    API->>API: valida token y reglas de contraseña, guarda el nuevo hash bcrypt
    API-->>FE: 204
```
