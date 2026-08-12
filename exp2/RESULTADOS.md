# Resultados — Experimento 2

Lectura honesta de `aggregated/distancias.csv` y `aggregated/por_perfil_dataset.csv`.
**118.273 flujos, 7 fuentes.** Los tamaños de muestra están en `conteo_flows.md`
y en la columna `n_flows` de cada tabla.

Recordatorio de cómo se leen estos números (detalle en `LIMITACIONES.md` §5):
el **estadístico D del KS** (en [0,1]) es el tamaño del efecto y es lo que hay que
mirar. El **p-valor no informa** aquí: con decenas de miles de flujos sale < 0,05
en 102 de las 108 comparaciones, incluidas aquellas cuyo D es de 0,02. Se reporta
por completitud.

---

## 1. Distancia media por par (KS D, media de las 12 features)

Hay **dos** baselines internos, y la diferencia entre ellos es el resultado central:

- **Planner aleatorio** (`exp1/random`): el **mismo Chrome** y el mismo catálogo de
  acciones; solo cambia *quién elige* la acción.
- **Script simple** (`exp2/baseline_script`): `urllib`, GET a intervalo fijo,
  **sin navegador**, sin estado, sin comportamiento.

| | Planner aleatorio | **Script simple** | CTU-Normal (PCAP) | CIC-IDS2018 (CSV) |
|---|---:|---:|---:|---:|
| **Nuestro · regular** | **0,036** | **0,235** | 0,284 | 0,304 |
| **Nuestro · gamer** | 0,250 | 0,165 | **0,183** | 0,281 |
| **Nuestro · admin** | 0,300 | 0,380 | 0,416 | 0,357 |

Jensen-Shannon y Wasserstein normalizado dan el mismo orden (ver `distancias.csv`).

## 2. Lo que sostiene la hipótesis

**(a) Los tres perfiles se separan entre sí, y la separación es conductual, no un
artefacto de medida.** La distribución de servicios es la evidencia más directa
(`plots/servicios.png`):

| Fuente | Servicio dominante | Segundo | Ratio TCP/UDP |
|---|---|---|---:|
| Nuestro · regular | DNS 53 % | HTTPS 26 %, QUIC 11 % | 2,64 |
| Nuestro · gamer | **UNKNOWN 64 %** (juego + voz en puertos no estándar) | HTTPS 19 % | **0,38** |
| Nuestro · admin | **SSH 52 %** | DNS 29 %, HTTP 17 % | 2,39 |

El perfil admin es 52 % SSH y el gamer invierte el ratio TCP/UDP (0,38 frente a
2,6 del regular) por el tráfico UDP de juego y voz. Eso **no** se puede obtener
sacudiendo parámetros: sale del comportamiento que ejecuta cada agente.

**(b) Los rangos son plausibles frente a los datasets públicos.** Las medianas caen
en el mismo orden de magnitud que las de tráfico benigno real:

| Feature (mediana) | regular | gamer | admin | CTU-Normal | CIC-IDS2018 |
|---|---:|---:|---:|---:|---:|
| Bytes por flujo (payload) | 126 | 163 | 32 | 138 | 172 |
| Paquetes por flujo | 4 | 2 | 2 | 2 | 3 |
| Duración del flujo (s) | 0,05 | 0,05 | 0,00 | 0,09 | 0,03 |
| Tamaño medio de paquete (B) | 14,5 | 163 | 4,6 | 80 | 64 |

Las CDFs (`plots/cdf_bytes_payload.png`) se solapan en la región de 10²–10⁴ bytes,
que es donde vive la masa de los tres perfiles y de los dos datasets públicos.

**(c) El perfil gamer está más cerca del tráfico real de un host (CTU-Normal,
D = 0,183) que del baseline interno (D = 0,250).** Es el resultado más favorable
del experimento y no estaba buscado.

**(d) Frente a un baseline realmente ingenuo, el perfil regular SÍ se separa, y en
todas las features.** `ours_regular` vs `baseline_script`: **D = 0,235**, seis
veces más que contra el planner aleatorio. No hay ni una feature que no se separe:

| Feature | vs planner aleatorio | vs script simple | ×  |
|---|---:|---:|---:|
| Puerto destino | 0,021 | **0,463** | ×22 |
| Tamaño medio de paquete | 0,064 | **0,425** | ×6,6 |
| TCP ACK por flujo | 0,066 | 0,326 | ×4,9 |
| Duración del flujo | 0,024 | 0,287 | ×12 |
| Paquetes por flujo | 0,022 | 0,224 | ×10 |
| Byte rate | 0,028 | 0,222 | ×7,9 |
| Bytes por flujo | 0,046 | 0,198 | ×4,3 |

La causa es estructural y se ve en la distribución de servicios: **nuestro agente
genera 53 % de flujos DNS; el script, 8,9 %.** Un navegador cargando una página
real resuelve decenas de dominios de terceros (CDN, analítica, fuentes,
publicidad) y abre conexiones concurrentes hacia ellos; un `GET` de `urllib` baja
un HTML y se acaba. Esa cascada de subrecursos **es** el comportamiento, y deja
una huella de red que un script no reproduce.

## 3. Lo que NO sostiene (y hay que decir)

**El planner LLM no genera un tráfico distinguible del de un planner aleatorio.**
`ours_regular` vs `baseline_interno` da **D = 0,036** (JS = 0,051): prácticamente
la misma distribución. Feature a feature, las medianas casi coinciden — 126 vs 135
bytes, 0,0476 vs 0,0487 s de duración, puerto destino 53 en ambos.

La razón es de diseño, no de medida: ese baseline es **el mismo agente web, el
mismo Chrome y el mismo catálogo de acciones**, cambiando solo *quién elige* la
acción. A nivel de flujo, abrir YouTube porque lo decidió un LLM y abrirlo porque
salió en un dado **produce el mismo tráfico**. Es coherente con el hallazgo de exp1
(el planner LLM no aportó más diversidad de acciones que el muestreo uniforme; ver
`exp1/NOTA_errores.md`).

La distinción que hay que hacer en el paper, y que estos datos sostienen:

- **Lo que aporta la fundamentación conductual es el AGENTE** (navegador real,
  cascada de subrecursos, sesión, concurrencia) y el **PERFIL** (regular / gamer /
  admin). Eso separa con claridad de un script simple (D = 0,235–0,380).
- **Lo que NO aporta valor medible a nivel de flujo es el PLANNER LLM** frente a un
  muestreo aleatorio sobre el mismo catálogo (D = 0,036). Si el LLM aporta algo,
  será en la secuencia semántica de acciones, no en las features de flujo — y este
  experimento no lo mide.

## 4. Distancia a los datasets públicos: ni cero, ni desmedida

Nuestros perfiles quedan a **D = 0,18–0,42** de los dos datasets públicos. No es
cero —y no debería serlo: son un host único frente a una red empresarial (IDS2018)
y frente a un portátil con P2P y tráfico de 2013 (CTU)—, pero está en el mismo
rango en el que los perfiles distan **entre sí**. Es decir: la diferencia entre
nuestro tráfico y el tráfico benigno público es del mismo orden que la diferencia
entre un usuario y un gamer. Eso es exactamente lo que significa "rangos
plausibles", y es todo lo que se afirma.

Las features donde más nos separamos de IDS2018 son `packets_per_s` y
`bytes_per_s_payload`, y la causa está identificada: el perfil admin habla con
**VMs en la LAN** (RTT de microsegundos), lo que dispara las tasas en flujos muy
cortos. Es real, no un error de cálculo, y la mediana lo refleja mejor que la media
(admin: 305 pkt/s de mediana frente a 69.666 de media).

## 5. Incidencia: Windows Update contaminó `script_run01`

El `run_01` del baseline script pesa **602 MB** frente a los ~70 MB de los otros
dos, con las mismas 90 peticiones. Identificado con tshark: **507 peticiones HTTP a
`dl.delivery.mp.microsoft.com`** (Windows Update / Delivery Optimization)
descargando en segundo plano durante la captura. No es tráfico del script, que va
todo por HTTPS.

**No se filtra** (exp1 fijó la política de capturar la interfaz completa y no
limpiar el ruido de fondo, para no introducir sesgos nuevos), pero se comprueba que
no sostiene la conclusión:

| | n flujos | KS D medio (vs `ours_regular`) |
|---|---:|---:|
| Baseline script, 3 runs (con Windows Update) | 4.357 | 0,235 |
| Baseline script, 2 runs (sin `run_01`) | 2.200 | **0,267** |

Al quitar el run contaminado la distancia **sube**: el ruido de Windows Update, si
acaso, *acerca* el baseline a nuestro tráfico. Conservar los 3 runs es la opción
conservadora. (El mismo fenómeno explica que `llm_run01` de exp1 pese 195 MB frente
a los 40-70 MB del resto de runs.)
