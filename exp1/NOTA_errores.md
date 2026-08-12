# NOTA — incidencias y decisiones de diseño (Experimento 1)

## Bugs preexistentes encontrados y corregidos al montar el experimento

1. **`estadisticas4.py` — TRES regresiones de indentación (el script era
   inejecutable).** Al añadir la funcionalidad de `local_ip` en la v4 se
   desindentaron tres bloques:
   - el análisis L4/flows/DNS/app-proto quedó **fuera del bucle de paquetes**
     (flows, puertos, DNS y protocolos salían vacíos o corruptos);
   - el resumen de puertos outbound quedó **a nivel de módulo** → `NameError`
     al cargar el fichero (ni siquiera arrancaba);
   - dos `plot_bar` de puertos outbound, también a nivel de módulo.
   Se restauró la indentación (comportamiento de `estadisticas3.py`)
   conservando la funcionalidad de `local_ip`. Verificado tras el fix con
   `captura5m2.pcapng`: 8.693 pkts, 136 flows, JSON y gráficas OK. Las métricas
   previas del TFM no están afectadas (se generaron con `estadisticas3.py`; la
   v4 no podía ejecutarse). El extractor del experimento
   (`exp1/src/traffic_metrics.py`) reutiliza los helpers ya corregidos.

2. **`captura_combinada.py` — variable de entorno equivocada.**
   Pasaba `DURACION_TOTAL_SEGUNDOS` al agente web, pero `agentev7.py` lee
   `DURACION_WEB_S`: el agente web ignoraba la duración pedida. Corregido.

## Cambios de soporte en `agentev7.py` (sin cambio de comportamiento)

- `crear_driver()` extraído del `__main__` (lo reutiliza el session runner).
- `ejecutar_accion_browser()` ahora devuelve `bool` (antes tragaba errores sin
  señal); necesario para contar acciones fallidas.
- `obtener_accion_json_llm(trace=...)` opcional: anota prompt/respuesta/intentos
  y fallback para la trazabilidad exigida por el experimento.

## Decisiones de diseño

- **Duración de sesión: 900 s (15 min)** por run (decisión del usuario, 2026-07-10;
  antes 300 s). Con la sobrecarga por run (~90 s de arranque de Chrome + extracción
  de métricas + pausa) cada run tarda ~16,5 min de reloj: 10 runs × 2 planners
  (random+rule) ≈ 5,5 h; los 3 planners ≈ 8 h. Parametrizable con `--duration`.
- **Seeds:** `1000 + índice_de_run`, compartida por las tres variantes del mismo
  índice. En el planner LLM la seed no controla la API (no determinista), pero
  sí la aleatoriedad local (elección de perfil/intención del prompt, fallbacks,
  scrolls de `simular_actividad`).
- **Pools de parámetros de random/rule:** derivados de los valores de fallback
  de `agentev7.py`, ampliados mínimamente (8 términos de búsqueda, 5 URLs, 6
  búsquedas de YouTube), declarados en `exp1/src/planners.py`. Decisión: un
  baseline sin LLM necesita una lista curada a mano; su menor variedad frente
  al LLM es parte del resultado del experimento, no un artefacto a esconder.
- **Orden de ejecución intercalado** (llm, random, rule, llm, ...) para no
  confundir planner con hora del día / estado de la red.
- **Captura de interfaz completa** (misma que el pipeline existente): incluye
  ruido de fondo del SO (telemetría, actualizaciones). Es idéntico entre
  variantes y queda registrado; no se filtra para no introducir sesgos nuevos.
- **Perfil de Chrome compartido** (`chrome_profile_tfm/`, el del sistema
  actual) para las tres variantes: cookies/sesiones constantes entre planners.
- **`set_page_load_timeout(60)`** en el runner (agentev7 no fijaba límite y una
  página colgada podía consumir la sesión). Aplica igual a las tres variantes.
- **Acciones `revisar_correo`/`usar_twitter`** pueden fallar por bloqueos de
  Google/X: se cuentan como `ejecutadas_fallo` (dato honesto, no se excluyen).

## Incidencias durante la ejecución

### Experimento completo 3 planners × 10 runs × 900 s (2026-07-10, ~20:28–)

- **PCAP truncado en 2 de 30 runs (tshark matado en duro).** En Windows,
  `captura_combinada.detener_tshark()` usa `Popen.terminate()` (= TerminateProcess,
  no da tiempo a vaciar el último bloque pcapng). Ocasionalmente el fichero queda
  con el bloque final incompleto → `PcapNg: Invalid Block body length (too short)`
  al leerlo con scapy, y el orquestador marca el run como `failed`. Afectó a
  **`rule/run_04` y `rule/run_10`**. Mitigación: `traffic_metrics.extraer_metricas()`
  tolera el truncamiento (procesa todos los paquetes completos y marca
  `pcap_truncado=True`), y `exp1/src/salvage.py` re-extrae las métricas de los runs
  `failed`, escribe su `metrics.json` y los marca `completed` con
  `recuperado_de_truncamiento=True`. Recuperados: `rule/run_04` (63.685 pkts /
  3.790 flows) y `rule/run_10` (747.837 pkts / 4.087 flows). No se re-captura: los
  paquetes completos ya estaban en el fichero (solo se pierde el bloque final).
  **Resultado final: 30/30 runs con métricas válidas.** Mejora futura recomendada:
  detener tshark con `CTRL_BREAK_EVENT` en vez de `terminate()` para un cierre
  limpio del pcapng.

## Resultado del experimento (resumen honesto)

Ejecución: 3 planners × 10 runs × 900 s, 2026-07-10/11, ~8 h, commit `8a1ef84`
(working tree con cambios de exp1), interfaz Wi-Fi (5), brazo LLM con clave Groq
válida (`llama-4-scout`, temp 0.2/0.3, fallback_rate=0).

Hallazgo principal (medianas): **el LLM NO aportó más diversidad de acciones que
los baselines; de hecho usó menos tipos**. Entropía de tipos: llm 1,58 <
random 2,31 < rule 2,44. El LLM concentró en `mirar_youtube` (69 acc.) y
`buscar_google` (37), y **nunca** eligió `abrir_url` ni `ver_streaming` (0/0),
mientras random y rule ejercitaron los 6 tipos. Repetición inmediata: llm 0,26 >
random 0,15 > rule 0,00. La estabilidad de ejecución fue equivalente
(tasa_exec_ok ≈ 0,87 en los tres): el LLM **no genera más fallos**, pero tampoco
más variedad. En tráfico, `rule` produjo más destinos/dominios únicos (306/57)
por recorrer todos los tipos; llm y random, menos (256/39 y 219/37).

Lectura: con este prompt y modelo, el planner LLM se comporta de forma más
sesgada/repetitiva que un muestreo uniforme. El resultado es específico de la
configuración (prompt que muestrea perfil/intención al azar + Llama-4-Scout a
temp 0.2) y así debe reportarse; no se maquilla.

### Smoke test (2026-07-10)

1. **PCAP vacío por interfaz de captura mal detectada (corregido).**
   `captura_combinada._autodetect_iface()` elige el primer adaptador no-loopback
   de `tshark -D`, que en esta máquina es una "Conexión de área local*" virtual
   sin tráfico (interfaz 1) → capturas de 0 paquetes. El tráfico real va por
   Wi-Fi (interfaz 5, GUID `FBE55F81-…`). Se añadió
   `orchestrate.detectar_iface_activa()`, que mapea la GUID del adaptador con la
   ruta por defecto (0.0.0.0/0) a la interfaz de `tshark -D`, con override
   `--iface N`. La interfaz se fija UNA vez y es la misma para los 30 runs.

2. **Clave de Groq expirada → el planner LLM degrada a fallback (HTTP 401).**
   La `GROQ_API_KEY` del `.env` devuelve `401 Unauthorized`. En consecuencia,
   `obtener_accion_json_llm()` agota los reintentos y usa
   `generar_accion_fallback()` en cada iteración: el brazo "llm" se comporta como
   las 4 plantillas de fallback, no como el LLM real. Queda registrado
   honestamente en cada run (llm_trace.jsonl con los 401, y contador
   `fallbacks == emitidas` en el manifest). **Acción requerida del usuario:**
   renovar la clave en `.env`; después, re-lanzar SOLO el brazo LLM con
   `python -m exp1.src.orchestrate --planners llm --runs 10 --force`
   (el orquestador es idempotente por planner). Los brazos random y rule no
   dependen de la API y son plenamente válidos.
