# Limitaciones y decisiones de comparación — Experimento 2

Qué se puede y qué **no** se puede afirmar con estos datos. Nada de esto invalida
el experimento; todo esto condiciona cómo hay que leerlo.

---

## 1. Lo que el experimento NO demuestra

- **No demuestra que nuestro tráfico replique tráfico empresarial real.** No es el
  objetivo y los datos no lo sostienen: nuestras capturas son de **una sola
  máquina detrás de NAT**, y CSE-CIC-IDS2018 es una **red empresarial capturada en
  el borde** (cientos de hosts). Una distancia pequeña en una feature no significa
  equivalencia; una grande no significa que nuestro tráfico sea irreal.
- **No demuestra que el planner LLM genere tráfico "más realista"** que un planner
  aleatorio. De hecho los datos apuntan a lo contrario a nivel de flujo (ver §6).
- La afirmación que sí sostienen los datos es la acotada: los **tres perfiles se
  separan entre sí** y sus **rangos son plausibles** frente a los datasets
  benignos públicos.

---

## 2. Definición de flujo: la diferencia que más pesa

| | Nuestro extractor (exp2) | exp1 | CICFlowMeter (IDS2018) |
|---|---|---|---|
| Dirección | **Bidireccional** (5-tupla canónica) | Unidireccional | Bidireccional |
| Timeout | **120 s** desde el inicio + 120 s de inactividad | ninguno | 120 s |
| Cierre TCP | RST, o FIN en ambos sentidos | ninguno | FIN/RST |
| Bytes | trama (`bytes_wire`) **y** payload L4 (`bytes_payload`) | trama | **solo payload L4** |

Consecuencias:

- **Los números de flujo de exp2 no son comparables con los de exp1** (ahí un
  flujo podía durar toda la sesión). Sobre `rule/run_01`: 3.416 flujos
  unidireccionales sin timeout vs 3.138 bidireccionales con timeout.
- **Todas las comparaciones de bytes usan `bytes_payload`**, porque es lo único
  que CICFlowMeter mide. `bytes_wire` se reporta en las tablas descriptivas, pero
  solo existe para las fuentes en PCAP.
- El timeout de 120 s **parte** los flujos largos (streaming, voz de Discord, un
  `tail -f` por SSH) en varios flujos. Es deliberado —así lo hace el dataset
  público— pero significa que "duración del flujo" tiene un **techo efectivo de
  120 s** en todas las fuentes.

## 3. Tasas (packet rate / byte rate) con duración 0

Un flujo de un solo paquete tiene duración 0. CICFlowMeter emite `Infinity`/`NaN`
en `Flow Pkts/s` y `Flow Byts/s`. **No usamos esas columnas**: las recalculamos a
partir de paquetes/bytes/duración con la **misma regla en todas las fuentes**
(tasa = 0 si la duración es 0). Es una convención, no una medida: la fracción de
flujos afectados se reporta en cada gráfica ("% en 0").

## 4. Features que NO existen en el baseline público CSV

El CSV de IDS2018 **no trae IPs ni puerto origen**. Por tanto, para esa fuente:

- `src_ip`, `dst_ip`, `src_port`, `bytes_wire`, `pkt_size_mean_wire` van **vacíos**.
- **"Destinos únicos" y "DNS queries" no son computables.** Esas dos métricas de la
  lista del experimento solo se comparan entre las fuentes en PCAP (nuestros tres
  perfiles, el baseline interno y CTU-Normal).
- La **distribución de servicios** de IDS2018 se infiere **solo por puerto destino**
  (misma heurística `heuristic_app_proto` que el resto, pero sin poder mirar el
  payload). En las fuentes en PCAP la heurística sí puede usar payload.

## 5. Tamaño muestral y p-valores del KS

Con decenas de miles de flujos por fuente, **el p-valor del KS es ~0 para
cualquier diferencia, por mínima que sea**: con ese n, la significación
estadística no informa de nada. Lo que hay que leer es el **estadístico D**
(tamaño del efecto, en [0,1]). Por eso se reporta además `ks_D_submuestra`: la
media de D sobre 20 submuestras de 1.000 flujos por lado (seed 2000), que muestra
si D es estable o un artefacto del tamaño muestral. **El p-valor se incluye por
completitud, no como criterio.**

Wasserstein se reporta en crudo y **normalizado por la desviación típica
conjunta**: las features son de cola pesada y la distancia en crudo la domina la
escala (bytes/s se mide en millones, SYN por flujo en unidades).

## 6. Hay DOS baselines internos, y miden cosas distintas

| | `baseline_interno` | `baseline_script` |
|---|---|---|
| Qué es | `exp1/random`: muestreo uniforme del mismo catálogo de acciones | `urllib`, GET a intervalo fijo (10 s), sin navegador |
| Navegador | **Sí** (el mismo Chrome y el mismo dispatcher que el perfil regular) | **No** |
| Qué contrasta | el **planner** (LLM vs dado) | el **comportamiento** (agente vs script) |
| Runs / seed | 10 × 900 s, seed 1000+i | 3 × 900 s, seed 3000+i |
| KS D vs `ours_regular` | **0,036** | **0,235** |

El primero **no separa** (D = 0,036): abrir YouTube porque lo decidió un LLM y
abrirlo porque salió en un dado produce el mismo tráfico. Es un **resultado**, no un
fallo del montaje: las features de flujo **no distinguen el planner**.

El segundo **sí separa** (D = 0,235, en las 12 features). Es el contraste "tonto"
que pedía el experimento, y es el que sostiene la afirmación objetivo.

Al citar "el baseline interno" en el paper hay que decir **cuál**, porque las dos
frases son ciertas y dicen cosas opuestas.

## 6b. El baseline script no es un usuario, y no pretende serlo

Va a los **mismos 10 dominios** que el agente web (para que lo medido sea el
comportamiento y no el destino), pero:

- No ejecuta JavaScript ni descarga subrecursos: por eso hace **8,9 % de flujos
  DNS** frente al **53 %** del agente. Esa diferencia *es* el resultado.
- Su intervalo es fijo (10 s), sin tiempos de lectura ni encadenamiento de acciones.
- Al no llevar navegador, **no genera QUIC** (el agente sí: 11 % de sus flujos).

No es un "usuario malo": es la ausencia de comportamiento, que es justo lo que se
quería tener enfrente.

## 7. Composición de las fuentes propias

- **Runs desbalanceados**: regular = 10 runs (900 s), gamer = 5 runs (15 min),
  admin = 5 runs (15 min). El nº de runs y de flujos detrás de **cada** estadístico
  está en `conteo_flows.md` y en la columna `n_flows` de cada tabla.
- **Capturas de interfaz completa**: incluyen el **ruido de fondo del SO**
  (telemetría de Windows, actualizaciones, mDNS/LLMNR). No se filtra, para no
  introducir un sesgo nuevo; es idéntico entre nuestras fuentes y queda registrado.
  Ese ruido **no siempre es pequeño**: `script_run01` se llevó 507 peticiones de
  Windows Update (602 MB de PCAP frente a 70 MB de los otros runs), y `llm_run01`
  de exp1 muestra el mismo patrón (195 MB). Se conserva y se declara; la
  comprobación de robustez está en `RESULTADOS.md` §5 (quitar el run contaminado
  **aumenta** la distancia, así que conservarlo es lo conservador).
- **Fechas distintas**: los runs regular/random son de julio de 2026 (exp1); los de
  gamer/admin, de marzo de 2026. Misma máquina y misma red, pero no la misma
  sesión temporal.
- El perfil **admin** genera tráfico contra **VMs locales** (SSH/ICMP/DNS internos),
  con lo que sus destinos son privados y muy repetidos. No es comparable con los
  destinos únicos de una fuente que navega por Internet.

## 8. Sobre el baseline público en PCAP (CTU-Normal-7)

- Es de **2013**: sin QUIC ni TLS 1.3, con más HTTP en claro. Sesga la
  *distribución de servicios* frente a nuestras capturas de 2026.
- Lleva **P2P (Deluge)**, que ninguno de nuestros perfiles tiene: infla los
  destinos únicos y la cola de flujos cortos.
- Es **un solo host y una sola captura** (21 min): no hay varianza entre runs que
  reportar, a diferencia de nuestras fuentes.

## 9. Sobre el extractor

- Sustituye la disección de scapy de exp1 por un **parser propio** (struct) por
  rendimiento. La equivalencia está verificada con
  `python -m exp2.scripts.validate_extractor` (paquetes, bytes, TCP/UDP, destinos
  únicos y duración coinciden **exactamente**).
- Se apartó de exp1 en dos puntos, **a mejor**, verificado contra tshark:
  - **ICMPv6 con cabecera hop-by-hop**: exp1 los etiquetaba `IPv6_0`; exp2 recorre
    la cadena de cabeceras de extensión y los clasifica bien.
  - **DNS**: exp2 parsea UDP/53, mDNS (5353), LLMNR (5355) **y DNS sobre TCP/53**
    (Windows/Chrome resuelven así contra la puerta de enlace: 682 queries en
    `rule/run_01`, que exp1 no contaba). Recuento verificado contra tshark
    (1.021 vs 1.019 queries; la diferencia son retransmisiones contadas una vez
    por segmento).
- **No hay reensamblado de TCP**: las queries DNS sobre TCP se leen segmento a
  segmento. Una query partida entre dos segmentos se perdería (no se observó).
- La heurística de servicio es **por puerto** (con un vistazo al payload para
  HTTP). No hay inspección profunda: un servicio en un puerto no estándar se
  clasifica como `UNKNOWN`. Eso explica el 64 % de `UNKNOWN` del perfil gamer
  (juego y voz en puertos altos) y el 54 % de CTU-Normal (P2P): es una limitación
  de la heurística, no una propiedad del tráfico.

## 10. Las tasas tienen colas absurdas, y son reales

`packets_per_s` y `bytes_per_s_payload` alcanzan valores de 10⁵–10⁶ en el perfil
admin y en IDS2018. No es un error de cálculo: son flujos de 2-3 paquetes en
duraciones de microsegundos (el admin habla con **VMs en la misma máquina/LAN**;
IDS2018 tiene tráfico interno del datacenter). La media de estas dos features **no
es interpretable**; hay que leer la mediana y el IQR. Se reportan igualmente en
crudo, sin recortar outliers, para no maquillar la distribución.
