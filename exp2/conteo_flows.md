# Nº de flujos analizados por fuente — Experimento 2

Generado por `python -m exp2.scripts.conteo`. **Todo estadístico de este
experimento hay que leerlo con estos tamaños de muestra delante.**

## Resumen por fuente

| Fuente | Perfil | Runs | Flujos | Flujos/run | Paquetes | Duración total |
|---|---|---:|---:|---:|---:|---:|
| `ours_regular` | regular | 10 | 29.702 | 2970.2 | 747.282 | 153 min |
| `ours_gamer` | gamer | 5 | 4.200 | 840.0 | 861.623 | 78 min |
| `ours_admin` | admin | 5 | 2.682 | 536.4 | 204.544 | 77 min |
| `baseline_interno` | random_baseline | 10 | 24.354 | 2435.4 | 624.521 | 155 min |
| `baseline_script` | script_simple | 3 | 4.357 | 1452.3 | 573.457 | 45 min |
| `baseline_publico_ctu` | ctu_normal | 1 | 2.978 | 2978.0 | 471.237 | 21 min |
| `baseline_publico_ids2018` | ids2018_benign | 1 | 50.000 | 50000.0 | n/d | n/d |

**Total: 118.273 flujos**

## Procedencia

- **`ours_regular`** — Nuestro · perfil regular (agentev7 + planner LLM) — exp1/llm/run_01..10
- **`ours_gamer`** — Nuestro · perfil gamer (Discord + Steam) — Articulo/capturaAgenteGamer15m1..5
- **`ours_admin`** — Nuestro · perfil admin de red (SSH multi-host) — Articulo/capturaAgenteAdmin15m1..5
- **`baseline_interno`** — Baseline interno · planner aleatorio (mismo navegador, sin LLM) — exp1/random/run_01..10
- **`baseline_script`** — Baseline interno · script simple (urllib, intervalo fijo, SIN navegador) — exp2/baseline_script/run_01..03
- **`baseline_publico_ctu`** — Baseline público en PCAP — Stratosphere CTU-Normal-7 (nuestro extractor)
- **`baseline_publico_ids2018`** — Baseline público en CSV — CSE-CIC-IDS2018 Wednesday, clase Benign (CICFlowMeter)

## Desbalance (declarado, no corregido)

- El perfil **regular** tiene 10 runs; **gamer** y **admin**, 5. Se usan
  las capturas existentes (ver LIMITACIONES.md §7).
- El baseline **CTU-Normal** es **una sola captura** de 21 min: no hay
  varianza entre runs que reportar.
- El baseline **IDS2018** es una **muestra aleatoria (seed 2000)** de los
  flujos Benign de un día completo, no una sesión: su 'run' es el día.

## Detalle por run

| Fuente | Run | Flujos | Paquetes | Duración (s) | DNS queries | IPs destino únicas |
|---|---|---:|---:|---:|---:|---:|
| `ours_regular` | llm_run01 | 6.174 | 218137 | 913.85 | 1924 | 510 |
| `ours_regular` | llm_run02 | 2.522 | 53716 | 921.627 | 846 | 256 |
| `ours_regular` | llm_run03 | 2.651 | 73437 | 902.967 | 888 | 260 |
| `ours_regular` | llm_run04 | 2.077 | 54780 | 902.768 | 687 | 194 |
| `ours_regular` | llm_run05 | 1.851 | 49822 | 963.583 | 634 | 142 |
| `ours_regular` | llm_run06 | 1.463 | 39181 | 902.077 | 525 | 108 |
| `ours_regular` | llm_run07 | 3.178 | 77992 | 935.777 | 1061 | 244 |
| `ours_regular` | llm_run08 | 2.794 | 54534 | 904.555 | 1000 | 256 |
| `ours_regular` | llm_run09 | 3.327 | 59368 | 903.903 | 1176 | 322 |
| `ours_regular` | llm_run10 | 3.665 | 66315 | 926.414 | 1342 | 337 |
| `ours_gamer` | gamer_run01 | 830 | 183988 | 919.656 | 215 | 101 |
| `ours_gamer` | gamer_run02 | 830 | 174115 | 984.859 | 251 | 97 |
| `ours_gamer` | gamer_run03 | 808 | 112538 | 935.245 | 225 | 91 |
| `ours_gamer` | gamer_run04 | 936 | 210751 | 920.867 | 265 | 112 |
| `ours_gamer` | gamer_run05 | 796 | 180231 | 907.963 | 171 | 118 |
| `ours_admin` | admin_run01 | 500 | 40485 | 911.951 | 258 | 4 |
| `ours_admin` | admin_run02 | 567 | 40643 | 924.977 | 330 | 4 |
| `ours_admin` | admin_run03 | 552 | 41400 | 905.254 | 270 | 4 |
| `ours_admin` | admin_run04 | 515 | 39945 | 920.535 | 258 | 5 |
| `ours_admin` | admin_run05 | 548 | 42071 | 933.252 | 278 | 4 |
| `baseline_interno` | random_run01 | 3.205 | 84952 | 949.539 | 1044 | 259 |
| `baseline_interno` | random_run02 | 2.240 | 66703 | 902.774 | 775 | 216 |
| `baseline_interno` | random_run03 | 2.498 | 67419 | 957.479 | 824 | 223 |
| `baseline_interno` | random_run04 | 1.788 | 50895 | 903.58 | 648 | 179 |
| `baseline_interno` | random_run05 | 1.596 | 51203 | 932.154 | 593 | 134 |
| `baseline_interno` | random_run06 | 2.766 | 64572 | 906.029 | 996 | 256 |
| `baseline_interno` | random_run07 | 1.896 | 50960 | 902.06 | 715 | 193 |
| `baseline_interno` | random_run08 | 2.916 | 68532 | 1014.058 | 979 | 292 |
| `baseline_interno` | random_run09 | 3.000 | 64822 | 924.889 | 1075 | 296 |
| `baseline_interno` | random_run10 | 2.449 | 54463 | 935.161 | 790 | 185 |
| `baseline_script` | script_run01 | 2.157 | 457292 | 902.211 | 2021 | 131 |
| `baseline_script` | script_run02 | 1.195 | 59331 | 900.651 | 1095 | 75 |
| `baseline_script` | script_run03 | 1.005 | 56834 | 901.696 | 792 | 73 |
| `baseline_publico_ctu` | ctu_normal_7 | 2.978 | 471237 | 1281.886 | 1075 | 1017 |
| `baseline_publico_ids2018` | wednesday-14-02-2018 | 50.000 |  |  |  |  |
