# Baselines públicos del Experimento 2

Se usan **dos** datasets públicos benignos, por una razón concreta: uno permite
aplicar **nuestro propio extractor** (comparación limpia), y el otro es el
**dataset canónico** que un revisor espera ver (comparación citable). Cada uno
cubre la debilidad del otro.

---

## 1. CIC-IDS2017 — descartado (y por qué)

Era la primera opción (día *Monday-WorkingHours* = el único 100 % benigno del
dataset). **No es descargable de forma automatizable**: el servidor del CIC
redirige cualquier descarga directa al formulario de registro de UNB.
Comprobado el 2026-07-14:

```
$ curl -sSI http://cicresearch.ca/CICDataset/CIC-IDS-2017/Dataset/PCAPs/Monday-WorkingHours.pcap
HTTP/1.1 301 Moved Permanently
Location: https://cicresearch.ca/.../Monday-WorkingHours.pcap
$ curl -sSI https://cicresearch.ca/.../Monday-WorkingHours.pcap
HTTP/1.1 302 Found
Location: https://www.unb.ca/cic/datasets/index.html      <-- formulario
```

Se probó también con `User-Agent` de navegador y `Referer` de la página del
dataset: mismo redirect. Se descartó para no introducir un paso manual no
reproducible en el pipeline.

---

## 2. CSE-CIC-IDS2018 — baseline público **canónico** (CSV)

| | |
|---|---|
| **Qué es** | Tráfico de una red empresarial emulada en AWS (50 máquinas atacantes, 420 víctimas + 30 servidores), generado por el Canadian Institute for Cybersecurity (CIC) y el Communications Security Establishment (CSE). |
| **Por qué este** | Es uno de los datasets de referencia en IDS/NDR, tiene **clase `Benign` etiquetada explícitamente**, y el CIC lo publica en **AWS Open Data con acceso anónimo** (sin registro, descarga automatizable). |
| **Subset concreto** | Fichero `Wednesday-14-02-2018_TrafficForML_CICFlowMeter.csv` (358 MB), de `Processed Traffic Data for ML Algorithms/`. |
| **Clase usada** | Solo filas con `Label == "Benign"`. Se descartan las de ataque (FTP-BruteForce, SSH-Bruteforce), las cabeceras repetidas a mitad de fichero (un defecto conocido de estos CSV) y los flujos que no son TCP/UDP. |
| **Cómo se acota** | Muestra aleatoria de **50.000 flujos** sobre el total de flujos Benign TCP/UDP del día, por **muestreo de reservorio** (una sola pasada, sin cargar el CSV en memoria) con **seed = 2000**. |
| **Formato** | Ya viene en **features de flujo de CICFlowMeter**, no en PCAP. El CIC sí publica los PCAP originales, pero como ZIP de **38–59 GB por día**: inviable. |
| **Procedencia** | `https://cse-cic-ids2018.s3.amazonaws.com/` (AWS Open Data Registry). SHA-256 del fichero descargado en `exp2/public/procedencia.json`. |
| **Licencia** | Uso libre para investigación **con citación obligatoria**: Sharafaldin, Lashkari & Ghorbani, *"Toward Generating a New Intrusion Detection Dataset and Intrusion Traffic Characterization"*, ICISSP 2018. |

### Consecuencia: esta fuente NO pasa por nuestro extractor

Es la única. La traducción está en [`scripts/adapt_ids2018.py`](scripts/adapt_ids2018.py),
a la vista y sin pasos manuales. Las diferencias de definición están en
[`LIMITACIONES.md`](LIMITACIONES.md); las dos que más pesan:

- **CICFlowMeter cuenta solo bytes de payload L4**, no la trama. Por eso nuestro
  extractor emite `bytes_wire` *y* `bytes_payload`, y **todas las comparaciones
  usan `bytes_payload`** en ambos lados.
- **El CSV no trae IPs ni puerto origen.** Por tanto, para esta fuente no existen
  "destinos únicos" ni "DNS queries": esas columnas quedan vacías y esas métricas
  solo se comparan contra las fuentes en PCAP.

---

## 3. Stratosphere CTU-Normal-7 — baseline público **con nuestro extractor** (PCAP)

| | |
|---|---|
| **Qué es** | Captura real de **un solo portátil** (Debian, red doméstica) con actividad humana: navegación con Chrome (Twitter, YouTube), jabber y descargas P2P con Deluge. Verificada manualmente como limpia por el Stratosphere IPS Project (CTU, Praga). |
| **Por qué este** | Es tráfico **benigno real de un único host**, que es exactamente nuestra topología (nuestros agentes corren en una máquina detrás de NAT). CSE-CIC-IDS2018 es tráfico de red empresarial capturado en el borde: útil como referencia, pero no comparable en "destinos únicos" ni en volumen agregado. Y, sobre todo, **está en PCAP**: lo procesa **el mismo extractor** que nuestras fuentes, lo que sostiene el requisito de "mismo extractor para todas las fuentes". |
| **Subset concreto** | `CTU-Normal-7/2013-12-17_capture1.pcap` (417 MB). Se usa entero. |
| **Procedencia** | `https://mcfp.felk.cvut.cz/publicDatasets/CTU-Normal-7/`. SHA-256 en `exp2/public/procedencia.json`. |
| **Licencia** | Stratosphere IPS Project (CTU University, Czech Republic). Uso libre para investigación **con citación**: García, Grill, Stiborek & Zunino, *"An empirical comparison of botnet detection methods"*, Computers & Security, 2014. |

### Advertencias honestas sobre esta fuente

- **Es de 2013.** No hay QUIC ni TLS 1.3, y hay más HTTP en claro que en nuestras
  capturas de 2026. Afecta sobre todo a la *distribución de servicios*.
- **Lleva P2P (Deluge)**, que nuestros perfiles no tienen. Genera muchísimos
  flujos cortos hacia destinos únicos: infla los destinos únicos y desplaza la
  distribución de duración/bytes hacia flujos pequeños. Es una diferencia de
  comportamiento, no un defecto de medida, y así se reporta.

---

## Reproducir la descarga

```bash
python -m exp2.scripts.fetch_public                 # ambas fuentes + SHA-256
python -m exp2.scripts.adapt_ids2018                # CSV -> esquema común (seed 2000)
python -m exp2.scripts.extract_all --fuentes baseline_publico   # CTU con nuestro extractor
```

Los hashes y las URLs exactas quedan en `exp2/public/procedencia.json`.
