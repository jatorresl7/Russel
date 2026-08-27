# Jarvis - Asistente Personal

## Objetivo
PWA personal que interactúa con el celular y corre scripts en el PC.

## Módulos
1. ✅ Leer y resumir Gmail diariamente
2. Análisis financiero de extractos bancarios (PDF por correo)
3. Stock tracking con criterios personales
4. ✅ Launcher de scripts de trabajo
5. Robot: vision (YOLO) + control de motores por WiFi — en curso
   - Reconocimiento de caras (SFace): enrolar, galeria y quien esta en cuadro ✅
6. ✅ Asistente con LLM local (Qwen3 sobre llama.cpp): voz y teclado en la misma charla
   - Memoria persistente: pendiente (hoy es solo una ventana de 8 turnos en RAM)
7. ✅ Consola web navegable: Russ (todo junto), consola, Gmail, scripts, tools,
   visión, robot, caras y sistema
8. ✅ Tools que Russ puede invocar (`recordar`, `mirar`), con gramática GBNF
9. ✅ Memoria: explícita (él la guarda) + consolidación diferida en background
10. ✅ Grafo de estados, con vista en vivo. La iniciativa viene apagada.

## Stack
- Backend: Python + FastAPI
- Frontend: Lit + @vaadin/router + webpack + Tailwind, sobre el esqueleto de
  `/PROJECTS/TYPESCRIPT/aeropuerto-ops-frontend` (ver **Frontend** abajo)
- Auth: Google OAuth 2.0 con refresh token
- AI: Anthropic API (Claude)
- LLM local: Qwen3-1.7B GGUF Q8 sobre llama.cpp (CPU), via `JARVIS_LLM=1.7b` en .env.
  `JARVIS_LLM=0.6b` baja a Qwen3-0.6B: la mitad de latencia, bastante menos calidad
- DB: PostgreSQL + SQLAlchemy + **pgvector** (memoria semántica)
- Embeddings: `intfloat/multilingual-e5-small` local, 384 dims, ~21 ms/vector
- Conectividad celular ↔ compu: Tailscale VPN ✅ (PC IP: 100.69.89.52, uvicorn con --host 0.0.0.0)
- Frontend nativo: Android (Kotlin) en /PROJECTS/KOTLIN/jarvis-app
- Deploy: Railway o Render (pendiente)

## Cómo correr
```bash
npm install                 # una sola vez
npm run build               # compila el front a web/dist
uvicorn main:app --reload --host 0.0.0.0 --port 8000 --timeout-graceful-shutdown 2
```
`--timeout-graceful-shutdown` no es opcional en la práctica: la consola deja
abierto un SSE (`/api/assistant/stream`) que no termina nunca, y sin el flag
`--reload` se queda colgado en «Waiting for connections to close» en cada
guardado. El mismo uvicorn sirve el front (raíz) y la API (`/api`). Mientras se toca el
front conviene dejar `npm run dev` en otra terminal: recompila al guardar.
DB: `postgresql://jarvis:jarvis123@localhost/jarvis`

## Estructura
```
main.py                        # entry point, solo monta routers
app/
├── db.py                      # modelos SQLAlchemy + session
├── repository.py              # BaseRepository, BaseService, Page (genérico)
├── routers/                   # controladores delgados, una línea por endpoint
│   ├── gmail.py
│   ├── tools.py
│   ├── work_scripts.py
│   └── chat.py
└── services/                  # toda la lógica de negocio vive acá
    ├── gmail.py               # lectura Gmail + extracción
    ├── gmail_service.py       # casos de uso Gmail
    ├── llm.py                 # clientes LLM (Groq, OpenAI, Gemini)
    ├── tools_service.py
    ├── work_scripts_service.py
    ├── chat_service.py
    ├── vision_service.py      # YOLO + ByteTrack, senales de control del robot
    └── auth.py                # flujo OAuth Gmail
src/                           # front (TypeScript + Lit)
├── index.ts                   # registra los custom elements: uno por vista
├── app-root.ts                # shell: header, menu lateral, router
├── global-config.ts           # apiUrl, sale de web/config.js
├── styles.css                 # tokens del tema — cambiar aca cambia todo
├── crud/                      # esqueleto generico, NO tocar por proyecto
│   ├── crud-page.ts           # listado + alta + edicion + borrado
│   ├── crud-table.ts          # tabla con paginacion y cache
│   ├── crud-form.ts           # formulario por `fields()`
│   ├── crud-service.ts        # findAll/findPage/create/update/delete
│   ├── carga.ts               # "mostrar lo guardado y revalidar"
│   ├── kanban-page.ts kanban-board.ts multi-select.ts broker.ts
│   └── types.ts icons.ts
├── i18n/                      # t('clave'), es/en, toggle en el header
└── modules/                   # una carpeta por vista
    ├── russ/                  # vista unificada: camara + micro + charla
    ├── consola/               # chat-panel y estado-barra, compartidos
    ├── vision/                # camara-panel y control-stats, compartidos
    ├── robot/                 # simulacion de marcha + ruedas + seguir/parar
    ├── caras/                 # enrolar, galeria, quien esta en cuadro
    ├── conocimiento/          # las memorias: ver, editar, probar busqueda
    ├── grafo/                 # el grafo en vivo + toggle de iniciativa
    └── gmail/  scripts/  tools/  sistema/
web/
├── index.html                 # el unico html; lo sirve main.py
├── config.js                  # apiUrl — no se compila, se lee en runtime
└── dist/                      # bundle de webpack (no va al repo)
vision_preview.py              # preview de vision por webcam (debug, no es parte del API)
scripts/                       # scripts individuales de trabajo (.sh, permisos 700)
```

## Endpoints
Todos cuelgan de `/api`. La raíz es del front: `/`, `/consola`, `/gmail`,
`/scripts`, `/tools`, `/sistema` devuelven el `index.html` de la SPA.

| Método | Path | Descripción |
|--------|------|-------------|
| POST | /api/gmail/summarize | Resume emails de hoy y guarda en DB |
| GET  | /api/gmail/summaries | Lista resúmenes guardados |
| GET  | /api/tools | Lista tools habilitadas |
| POST | /api/tools | Crea una tool |
| POST | /api/tools/{id}/run | Ejecuta una tool |
| GET  | /api/work-scripts | Lista scripts de trabajo |
| POST | /api/work-scripts | Registra un script |
| PATCH | /api/work-scripts/{id}/toggle | Habilita/deshabilita |
| POST | /api/work-scripts/generate | Regenera ~/scripts/launch.sh |
| POST | /api/work-scripts/run | Ejecuta ~/scripts/launch.sh |
| POST | /api/chat | Guarda mensaje |
| GET  | /api/chat/history | Recupera historial |
| GET  | /api/assistant/status | Estado del LLM local (tok/s, prefill, hilos) |
| POST | /api/assistant/ask | Pregunta por teclado, devuelve la respuesta |
| GET  | /api/assistant/stream | SSE: la charla token por token (voz y teclado) |
| POST | /api/assistant/clear | Borra la ventana de contexto |
| POST | /api/assistant/load | Precarga el modelo en RAM |
| POST | /api/assistant/unload | Lo saca de RAM |
| GET  | /api/memoria | Lista memorias (envoltorio `Page`, acepta `search`) |
| POST | /api/memoria | Alta a mano |
| PUT  | /api/memoria/{id} | Edita (recalcula el vector) |
| DELETE | /api/memoria/{id} | Olvida |
| POST | /api/memoria/buscar | Qué recuperaría Russ para una frase |
| POST | /api/memoria/consolidar | Fuerza una vuelta de consolidación |
| GET  | /api/memoria/estado | Totales, turnos sin leer, estado del embed |
| PATCH | /api/memoria/{id}/vigente | Aprueba (o saca de uso) una memoria |
| GET  | /api/assistant/contexto | Con qué pensó el último turno |
| GET  | /api/grafo | Estado, historia de transiciones y cooldown |
| GET  | /api/system | Presupuesto de CPU por modulo |
| POST | /api/system/toggle | Prende/apaga un modulo (vision, asr, llm) |
| GET  | /api/audio/status | Micrófono, VAD, `cargando`, `transcribiendo`, transcripciones |
| POST | /api/audio/start · /stop | Prende/apaga la escucha |
| GET  | /api/vision/stream | MJPEG de la camara con las cajas dibujadas |
| GET/POST | /api/vision/config | seg, all_classes, conf, imgsz, **det_hz** |
| GET  | /api/vision/control | Giro/avance/objetivo que consume el robot |
| POST | /api/vision/reset | Suelta el objetivo que venia siguiendo |
| GET  | /api/robot/state | Ruedas, suavizado, hace cuanto vio al objetivo |
| GET  | /api/robot/command | Solo las ruedas — lo que consulta el robot real |
| POST | /api/robot/enable · /stop | Prende el seguimiento / frena |
| GET  | /api/faces/estado | Enrolados, quien esta en cuadro, umbral |
| GET  | /api/faces/{nombre}/fotos | Nombres de los recortes guardados |
| GET  | /api/faces/{nombre}/foto/{archivo} | Un recorte |
| POST | /api/faces/enrolar | Toma N fotos de la camara y las enrola |
| DELETE | /api/faces/{nombre} | Olvida a alguien |

## Frontend
El esqueleto sale de `aeropuerto-ops-frontend`. La regla es una sola: **lo que
sirve para cualquier proyecto vive en `src/crud/`; lo que es de Jarvis vive en
`src/modules/`.** Si hay que tocar `crud/` para que ande un módulo, casi siempre
lo que falta es un hook, no un caso especial.

Una vista CRUD son cuatro archivos y ninguno pasa de 50 líneas:

| archivo | qué declara |
|---------|-------------|
| `x.service.ts` | `base` (la URL) y `getKey`; hereda findAll/create/update/delete |
| `x.table.ts` | `columns()` — una fila por columna, con `renderer` si hace falta |
| `x.form.ts` | `fields()` — una fila por campo, con `type`, `required`, `zone` |
| `x.page.ts` | `prefix`, `label`, y devuelve la tabla y el form |

Después: registrar el import en `src/index.ts` y agregar la ruta y el ítem de
menú en `src/app-root.ts`.

Cosas que ya están resueltas y no hay que reinventar:
- **Textos:** todo pasa por `t('clave')`, con `es.ts` y `en.ts` en `src/i18n/`.
  Una clave nueva va en los dos archivos.
- **Cargas:** `Carga` (`src/crud/carga.ts`) sirve lo guardado y revalida, así
  que cambiar un filtro no vacía la pantalla. Después de mutar hay que llamar a
  `Carga.invalidar(prefijo)` o se vuelve a ver el estado anterior.
- **Colores y radios:** son tokens CSS al principio de `src/styles.css`. No hay
  colores sueltos en los componentes.

No todas las vistas son CRUD. `consola`, `vision`, `robot` y `caras` son
`LitElement` a secas: sondean su endpoint y pintan. Lo que se repetía entre
ellas se sacó a dos elementos compartidos en `src/modules/vision/`:

- `<camara-panel>` — el MJPEG y los toggles de YOLO/segmentación. Lo usan
  visión, robot y caras. **El stream no se recarga nunca**: hay un solo hilo
  leyendo `/dev/video` y los botones solo cambian su configuración.
- `<control-stats>` — giro, avance, objetivo, alto de caja y FPS.
- `<chat-panel>` — el SSE de la charla y la caja de texto.
- `<estado-barra>` — micrófono, VAD, estado del LLM y sus tres botones.
- `<grafo-vivo>` — el grafo moviéndose. `compacto` en `/russ`, entero en `/grafo`.
- `<contexto-vivo>` — con qué pensó el último turno: qué veía, qué recordó,
  cuánto contexto arrastraba y si decidió hablar o usar una herramienta.
- `<escucha-viva>` — lo que el micrófono está oyendo ahora y las últimas frases.

`grafo-vivo` va por **SSE y no por sondeo**: el backend publica cada transición
por `/assistant/stream`, y un turno entero puede empezar y terminar en menos de
lo que tarda una vuelta de `setInterval`. Sondeando se pierden los estados
cortos —`actuando` dura lo que tarda una tool— que son justo los que hay que
ver. El estado inicial sí se pide una vez al montar.

Hay **un solo `EventSource` en toda la app** (`sse.store.ts`) y un solo sondeo
de audio (`audio.store.ts`). No abras otro: cada SSE es una conexión permanente
y el navegador limita 6 por servidor, con el MJPEG de la cámara ya ocupando una.

Los dos de audio leen de `audio.store.ts`, un sondeo **compartido** de
`/audio/status` y `/assistant/status`. Es a propósito: el navegador limita las
conexiones por servidor (Firefox, 6) y el MJPEG de la cámara más el SSE de la
charla ya ocupan dos para siempre. Un componente nuevo que necesite ese estado
se suscribe al store, no abre su propio `setInterval`.

Ojo con `asr_stream`: viene apagado y es el que enciende la transcripción en
vivo. Apagado, mientras hablás no aparece nada — la frase sale entera recién al
terminar. `<escucha-viva>` lo avisa y ofrece prenderlo.

`russ-page` es la composición de los cuatro y no tiene lógica propia: es la
vista por defecto (`/` redirige ahí). Que estén juntos importa —
`assistant_service._sistema()` le mete a Russ lo que la cámara ve en CADA
turno, así que con la cámara en otra pantalla la mitad de la conversación es
invisible.

Quedan tres páginas HTML embebidas en los routers (`/api/vision`, `/api/robot`,
`/api/faces`) que hacen lo mismo que las vistas nuevas. Siguen funcionando pero
están duplicadas: son las candidatas obvias a borrar.

Lo que el backend todavía no tiene: `PUT` y `DELETE` en `/api/tools` y
`/api/work-scripts`. Por eso esas dos tablas van con `canEdit = false` y
`canDelete = false` — el día que existan los endpoints se borran esas dos
líneas y los botones aparecen solos.

## Vision: donde se va la CPU

Medido en este PC, con el proceso del server y nadie hablandole:

| que | CPU |
|-----|-----|
| vision apagada | 1 % |
| vision on, deteccion 5 Hz | ~140 % |
| vision on, deteccion 3 Hz | ~85 % |
| vision on, deteccion 2 Hz | ~54 % |

**La perilla es `det_hz`, no la resolucion.** Bajar `imgsz` de 480 a 256 solo
llevo 128 % a 88 %: el costo esta en la llamada a YOLO, no en su tamano. La
frecuencia sí escala casi lineal, ~28 % de un nucleo por deteccion por segundo.
Se cambia en caliente con `POST /api/vision/config {"det_hz": 2}`.

**`JARVIS_CAM_FPS` necesita el freno por software.** Esta webcam ignora
`CAP_PROP_FPS`: pidiendole 30, 15, 10 o 5 siempre contesta «30.0» y siempre
entrega 15. El grabber duerme hasta completar el periodo, y por eso el numero
significa algo. Sin ese freno, bajar el valor no hacia absolutamente nada.

**El dibujado se apaga si nadie mira.** Componer el overlay y comprimir a JPEG
es un costo constante que se pagaba siempre, con la pestana cerrada incluida. La
deteccion NO se apaga: se apaga la pantalla, no los ojos.

**`STALE_S` se deriva del ritmo** (`4 / CAM_FPS`, minimo 0.5 s). Con 0.5 s fijo
y una camara lenta —la Raspberry— cualquier hipo del driver pasaba por «camara
muerta» y frenaba al robot sin motivo.

## Memoria y grafo

**Dos formas de escribir, una de leer.** `explicito` es Russ llamando a la tool
`recordar`; `consolidado` es el hilo de fondo releyendo `conversations` cuando
el LLM está prendido, sin nada que atender y el grafo en `latente`. Se leen
igual: búsqueda por similitud, y lo que sale entra en el **mensaje volátil**.

**El `system` no se mueve.** Es lo que hace que llama.cpp reuse el KV cache. Lo
que cambia por turno —lo que ve la cámara, las memorias recuperadas— va en un
mensaje aparte pegado al turno del usuario. Medido acá: primer turno 4190 ms de
prefill, turnos siguientes ~830 ms. Si alguien vuelve a meter algo variable en
el `system`, eso se pierde entero y no lo va a avisar ningún test.

**Umbral de similitud: 0.845.** e5 comprime las distancias — una memoria que
responde da ~0.88 y una sin relación ~0.79 — así que el umbral útil está pegado
arriba y mover dos centésimas cambia bastante. Para ajustarlo está «Probar
búsqueda» en `/conocimiento`: es la única forma honesta, esos números no se
intuyen.

**Cuidado con pedirle brevedad.** El catálogo de tools decía «tu respuesta es
SOLO la llamada, sin ninguna otra palabra». Las llamadas salían perfectas y la
conversación se destruyó: a «si ese soy yo» contestaba «si ese soy yo», a «qué
haces» contestaba «Jaime.» — el fallo #1 de la lista al principio de
`assistant_service.py`. El modelo no entiende que la brevedad era solo para el
caso de la tool. La redacción que funciona no tiene un solo imperativo:
describe la herramienta y cierra con «lo demás es conversación».

**Lo que consolida Russ nace en espera.** Extraer datos de un diálogo es lo que
peor le sale a un 4B: sobre «mi hermana Ana vive en Cali» + «yo trabajo en
Aixa» sacó «Ana trabaja en Aixa». Insistir con el prompt bajó el ruido pero no
arregló la atribución, así que lo consolidado entra con `vigente=False` y
`buscar()` no lo ve hasta que se aprueba en `/conocimiento`. Lo explícito
—cuando Russ llama a `recordar`— entra directo, porque ahí no hay que adivinar
de quién es el dato.

**La gramática garantiza la forma, no la decisión.** Con GBNF una llamada
inválida es imposible de emitir. Pero que el modelo *elija* llamar depende del
prompt: con el catálogo solo en prosa, Qwen3-4B contestaba en texto plano. Se
arregló mostrándole la llamada literal en `EJEMPLOS_LLAMADA` — un modelo chico
copia el formato que tiene más cerca.

**Russ no ejecuta comandos.** `russ_tools.TOOLS` es un registro cerrado y no
incluye nada que corra shell. La tabla `tools` de la DB nunca se le muestra. La
regla: el modelo elige un nombre, nunca compone un comando.

**El grafo es determinista; el modelo solo se invoca en las hojas.** De los
cinco estados, solo `resolviendo` y `consolidando` gastan LLM. La política de
`atento` (cooldown de 90 s, no repetir motivo) son comparaciones baratas. La
arista `latente → atento` —la iniciativa— viene **apagada**: es la única que
hace que Russ hable sin que le hablen.

## Convenciones
- Routers: solo reciben request y delegan al service. Sin lógica. Se montan con
  `prefix=API` en `main.py`; la raíz queda libre para las rutas del front.
- Services: toda la lógica de negocio y acceso a DB.
- Modelos nuevos se agregan en `app/db.py` heredando de `Base` (incluye `to_dict()` y `__repr__`).
- Scripts de trabajo van en `scripts/` con permisos 700. La DB guarda nombre, título y filename — nunca el comando.
- Cada script contiene solo el comando interno del tab (sin gnome-terminal). El generador arma un único `gnome-terminal --window` con todos los `--tab -e`.
- Para que gnome-terminal funcione desde el servidor: `DISPLAY=:0` y `DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus`.
- Front: un módulo por carpeta en `src/modules/`, nada de lógica en `src/crud/`.
- La URL de la API sale de `web/config.js`, nunca escrita a mano en un service.

## Scripts registrados
| ID | Nombre | Título | Archivo |
|----|--------|--------|---------|
| 1 | logs-aixa | Logs Aixa | logs-aixa.sh |
| 2 | send-prexc | Mediport Automation | send-prexc.sh |
| 3 | mediport | Ext Tools Mediport | ssh-mediport.sh — SSH a 154.38.166.214 como aixabot en /opt/aixabot-external-sources/mediport |

## LLM local
- Medido en este PC (Ryzen 7 5800HS, sin GPU, 3 hilos para el LLM):

  | modelo | prefill | generacion | por turno | RAM |
  |--------|---------|------------|-----------|-----|
  | Qwen3-0.6B-Q8 | 175 ms | 41 tok/s | ~1.0 s | 640 MB |
  | Qwen3-1.7B-Q8 (en uso) | 300-500 ms | 18 tok/s | 0.8-2.8 s | 1.83 GB |

- A 18 tok/s cada token cuesta ~55ms, asi que la longitud de la respuesta pesa
  mas que el prefill. El prompt de sistema pide brevedad por latencia, no por
  estilo: bajar de 90 a 25 tokens de respuesta corta 3.5s de espera.
- El 1.7B sabe lo que el 0.6B inventa (que un VAD es Voice Activity Detection,
  por ejemplo), pero sigue equivocandose en datos finos: dijo que Whisper es de
  Meta. No confiar en el para hechos.

- El motor es llama.cpp, no transformers: con transformers el mismo 0.6B daba
  13 tok/s y 5.8 s de prefill en el tercer turno (rearma el prompt entero cada
  vez). llama.cpp reusa el KV cache del prefijo comun.
- El modo thinking de Qwen3 va apagado: en CPU son cientos de tokens de espera
  antes de la primera palabra.
- El LLM arranca apagado (`runtime.POR_DEFECTO`). Se prende desde la consola o
  con `POST /system/toggle {"modulo":"llm","on":true}`.

## Skills
- `/db` — inspeccionar la DB con psql desde Claude
- `/add-script` — crear script .sh + registrarlo en la DB

## Mantenimiento
Al cerrar un objetivo considerable: actualizar sección **Módulos** y **Endpoints** de este archivo.
