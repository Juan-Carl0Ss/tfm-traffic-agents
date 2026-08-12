# Experimento 2 — Fundamentación conductual y plausibilidad de las distribuciones

Compara, **con el mismo extractor de features de flujo**, el tráfico de nuestros
tres perfiles de agente frente a (a) un **baseline interno simple** sin planner
LLM y (b) **dos datasets benignos públicos**.

**La afirmación que se quiere sostener es acotada**: nuestro tráfico se separa del
baseline simple y sus distribuciones caen en **rangos plausibles** frente a
datasets benignos públicos. *No* se afirma que replique tráfico empresarial real.

- **Resultados y su lectura honesta:** [`RESULTADOS.md`](RESULTADOS.md). En corto:
  nuestro tráfico **sí se separa de un script simple sin navegador** (KS D = 0,235
  en el perfil regular, y en las 12 features), pero **no se separa de un planner
  aleatorio con el mismo navegador** (D = 0,036). Es decir: lo que deja huella de
  red es el **agente y el perfil**, no el **planner LLM**.
- **Lo que estos datos no demuestran:** [`LIMITACIONES.md`](LIMITACIONES.md).

## Fuentes

| Fuente | Qué es | Runs | Extractor |
|---|---|---|---|
| `ours_regular` | Agente web (`agentev7.py`) con planner LLM — `exp1/llm` | 10 × 900 s | nuestro |
| `ours_gamer` | Agente gamer (Discord + Steam) — `Articulo/capturaAgenteGamer15m*` | 5 × 15 min | nuestro |
| `ours_admin` | Agente admin de red (SSH multi-host) — `Articulo/capturaAgenteAdmin15m*` | 5 × 15 min | nuestro |
| `baseline_interno` | **Mismo agente, planner aleatorio** (sin LLM), seed 1000+i — `exp1/random`. Contrasta el *planner*. | 10 × 900 s | nuestro |
| `baseline_script` | **Script simple**: `urllib`, GET a intervalo fijo, **sin navegador**, seed 3000+i. Contrasta el *comportamiento*. | 3 × 900 s | nuestro |
| `baseline_publico_ctu` | Stratosphere **CTU-Normal-7**: portátil real, navegación humana + P2P | 1 × 21 min | nuestro |
| `baseline_publico_ids2018` | **CSE-CIC-IDS2018** Wednesday, clase `Benign` (muestra de 50.000, seed 2000) | 1 día | **CICFlowMeter** |

El nº exacto de flujos por fuente está en [`conteo_flows.md`](conteo_flows.md);
la procedencia y licencia de los públicos, en [`DATASET_publico.md`](DATASET_publico.md).

**El mismo extractor se aplica a las cinco fuentes en PCAP.** La sexta
(CSE-CIC-IDS2018) solo se distribuye en features de flujo — el CIC publica los
PCAP como ZIP de 38–59 GB por día —, así que se alinea con un adaptador explícito
([`scripts/adapt_ids2018.py`](scripts/adapt_ids2018.py)) y sus diferencias de
definición se declaran en `LIMITACIONES.md` §2 y §4.

## Reproducir

```bash
# 0) Requisitos: Python con scapy/pandas/numpy/scipy/matplotlib. Wireshark (tshark)
#    solo si quieres re-verificar el extractor contra una tercera herramienta.

# 1) Validar el extractor contra el de exp1 (mismas magnitudes, otro parser)
python -m exp2.scripts.validate_extractor --pcap exp1/rule/run_01/capture.pcap

# 2) Descargar los baselines públicos (~775 MB; escribe SHA-256 y URLs)
python -m exp2.scripts.fetch_public

# 3) Generar el baseline "tonto" (captura con tshark: 3 × 15 min ≈ 46 min)
python -m exp2.scripts.baseline_script --runs 3 --duration 900
python -m exp2.scripts.baseline_script --smoke   # prueba: 1 run de 60 s

# 4) Extraer flujos de TODAS las fuentes en PCAP (mismo extractor)
python -m exp2.scripts.extract_all              # ~25 s, 68.273 flujos
python -m exp2.scripts.extract_all --smoke      # prueba rápida: 20 s por PCAP

# 5) Alinear el dataset público en CSV con nuestro esquema
python -m exp2.scripts.adapt_ids2018            # seed 2000, muestra de 50.000

# 6) Descriptivos + distancias (KS/JS/Wasserstein) + gráficas
python -m exp2.scripts.compare

# 7) Regenerar el conteo de flujos
python -m exp2.scripts.conteo
```

Todo es determinista salvo las capturas en sí. Las seeds son **2000** (muestreo de
IDS2018 y submuestreo del KS), **1000+i** (runs de exp1) y **3000+i** (baseline
script).
El commit y la ruta de cada PCAP quedan en `aggregated/resumenes_sesion.json`;
las URLs y hashes de los datasets públicos, en `public/procedencia.json`.

## Salidas

```
exp2/
  flows/                          un CSV por fuente, MISMO esquema (24 columnas)
  aggregated/
    por_perfil_dataset.csv        descriptivos: n, media, mediana, std, IQR, min, max
    distancias.csv                KS (D, p, D submuestreado), JS, Wasserstein (crudo y normalizado)
    servicios.csv                 distribución de servicios y ratio TCP/UDP por fuente
    resumenes_sesion.json         por run: paquetes, bytes, DNS, destinos únicos, commit
    ids2018_adaptacion.json       filas leídas/filtradas/muestreadas del CSV público
  plots/                          box_<feature>.png y cdf_<feature>.png por feature + servicios.png
  public/                         datasets descargados + procedencia.json (URL, SHA-256, fecha)
  scripts/                        los 6 scripts de arriba
  DATASET_publico.md              qué datasets, qué subset, cómo se acotan, licencia
  conteo_flows.md                 nº de flujos por fuente y por run (generado)
  LIMITACIONES.md                 qué NO demuestra esto, y las diferencias de definición
```

## Features extraídas (idénticas en todas las fuentes)

`protocol`, `src_port`, `dst_port`, `duration_s`, `packets`, `bytes_wire`,
`bytes_payload`, `pkt_size_mean_{wire,payload}`, `packets_per_s`,
`bytes_per_s_payload`, `{fin,syn,rst,psh,ack,urg}_count`, `service`, y a nivel de
sesión: ratio TCP/UDP, DNS queries, destinos únicos, distribución de servicios.

Dos avisos que condicionan la lectura de los números:

- **Los bytes se comparan siempre como `bytes_payload`** (payload L4), porque es lo
  único que mide CICFlowMeter. `bytes_wire` está en las tablas, pero no existe para
  IDS2018.
- **`src_port`, IPs, destinos únicos y DNS queries no existen en IDS2018**: esas
  métricas solo se comparan entre las fuentes en PCAP.

## Nota sobre el extractor

`scripts/flow_features.py` es nuevo (exp1 emitía un **resumen agregado por PCAP**;
aquí hace falta **una fila por flujo**). No modifica `exp1/src/traffic_metrics.py`,
así que los resultados de exp1 siguen siendo válidos. Cambia la definición de flujo
a **bidireccional con timeout de 120 s** para alinearla con CICFlowMeter, añade TCP
flags y puerto origen, y corrige dos defectos de exp1 verificados contra tshark
(ICMPv6 con hop-by-hop, y DNS sobre TCP/mDNS/LLMNR). Detalle en `LIMITACIONES.md` §9.
