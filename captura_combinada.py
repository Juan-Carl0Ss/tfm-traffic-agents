#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
captura_combinada.py — Captura PCAP simultánea de todos los agentes TFM

Flujo:
  1. Arranca tshark en Windows (captura tráfico web/gamer + host↔VMs)
  2. Arranca tcpdump en la VM admin vía SSH (captura tráfico VM↔VM)
  3. Lanza los agentes configurados (web, gamer, admin) según el modo
  4. Para las capturas
  5. Fusiona los PCAPs con mergecap → un solo archivo final

Uso:
  python captura_combinada.py
  MODO_AGENTES=admin DURACION_S=900 python captura_combinada.py
  MODO_AGENTES=todos DURACION_S=3600 python captura_combinada.py

Variables de entorno:
  DURACION_S       duración total de la sesión en segundos (default: 300)
  MODO_AGENTES     web | gamer | admin | todos (default: admin)
  NOMBRE_PCAP      prefijo del archivo de salida (default: captura_tfm)
  IFACE_WINDOWS    interfaz de red en Windows para tshark (default: autodetect)
  IFACE_VM         interfaz en la VM admin para tcpdump (default: eth0)
  MERGECAP         ruta a mergecap.exe (default: junto a tshark)
"""

import os
import sys
import time
import signal
import subprocess
import threading
from datetime import datetime

# paramiko solo hace falta para la captura remota en la VM admin (tcpdump vía
# SSH); se hace opcional para poder reutilizar los helpers de tshark sin él.
try:
    import paramiko
    from paramiko.ssh_exception import SSHException
except ImportError:
    paramiko = None
    SSHException = Exception

# ══════════════════════════════════════════════════════════
#  CONFIGURACIÓN
# ══════════════════════════════════════════════════════════

DURACION_S   = int(os.environ.get("DURACION_S",   "300"))
MODO_AGENTES = os.environ.get("MODO_AGENTES", "admin")   # web | gamer | admin | todos
NOMBRE_PCAP  = os.environ.get("NOMBRE_PCAP",  "captura_tfm")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ── Rutas de herramientas Windows ──
TSHARK   = os.environ.get("TSHARK",   r"C:\Program Files\Wireshark\tshark.exe")
MERGECAP = os.environ.get("MERGECAP", r"C:\Program Files\Wireshark\mergecap.exe")

# Interfaz Windows: None = autodetectar la primera con tráfico real
IFACE_WINDOWS = os.environ.get("IFACE_WINDOWS", None)

# ── VM Admin (para tcpdump remoto) ──
VM_ADMIN_HOST = os.environ.get("VM_ADMIN_HOST", "10.10.0.1")
VM_ADMIN_PORT = int(os.environ.get("VM_ADMIN_PORT", "22"))
VM_ADMIN_USER = os.environ.get("VM_ADMIN_USER", "kali")
VM_ADMIN_PASS = os.environ.get("VM_ADMIN_PASS", "kali") or None
VM_ADMIN_KEY  = os.environ.get("VM_ADMIN_KEY",  None)   or None

# Interfaz de red dentro de la VM admin (eth0, enp0s3, ens3...)
IFACE_VM = os.environ.get("IFACE_VM", "eth0")

# Ruta donde se guarda el PCAP dentro de la VM
PCAP_VM_REMOTO = f"/tmp/{NOMBRE_PCAP}_vm_admin.pcap"

# ── Rutas de los scripts de agentes ──
SCRIPT_WEB   = os.path.join(BASE_DIR, "agentev7.py")
SCRIPT_GAMER = os.path.join(BASE_DIR, "agentegamer3.py")
SCRIPT_ADMIN = os.path.join(BASE_DIR, "agenteadminavanzado.py")

# ══════════════════════════════════════════════════════════
#  ESTADO GLOBAL
# ══════════════════════════════════════════════════════════

_procesos: list = []          # subprocesos Windows activos
_ssh_captura: "paramiko.SSHClient | None" = None
_chan_tcpdump: "paramiko.Channel | None" = None
_stop = threading.Event()


def _cleanup(sig=None, frame=None):
    print("\n[Captura] Señal recibida. Deteniendo todo...")
    _stop.set()
    _detener_tcpdump_remoto()
    for p in _procesos:
        if p and p.poll() is None:
            p.terminate()
    sys.exit(0)

signal.signal(signal.SIGINT, _cleanup)

# ══════════════════════════════════════════════════════════
#  UTILIDADES
# ══════════════════════════════════════════════════════════

def _ts():
    return datetime.now().strftime("%H:%M:%S")


def _autodetect_iface() -> str:
    """Devuelve el índice/nombre de la primera interfaz real en tshark."""
    try:
        r = subprocess.run([TSHARK, "-D"], capture_output=True, text=True, timeout=10)
        for line in r.stdout.splitlines():
            # Buscar interfaz que no sea loopback ni virtual de VirtualBox para tráfico real
            low = line.lower()
            if "loopback" in low or "npcap" in low:
                continue
            # La primera parte es el índice (ej: "1. \Device\NPF_{...}")
            idx = line.split(".")[0].strip()
            if idx.isdigit():
                print(f"  [tshark] Interfaz autodetectada: {line.strip()}")
                return idx
    except Exception as e:
        print(f"  [tshark] Error autodetectando interfaz: {e}")
    return "1"  # fallback

# ══════════════════════════════════════════════════════════
#  CAPTURA EN WINDOWS (tshark)
# ══════════════════════════════════════════════════════════

def listar_interfaces_tshark():
    """Muestra todas las interfaces disponibles — útil para elegir IFACE_WINDOWS."""
    print("\n[tshark] Interfaces disponibles:")
    try:
        r = subprocess.run([TSHARK, "-D"], capture_output=True, text=True, timeout=10)
        for line in r.stdout.strip().splitlines():
            print(f"  {line}")
    except FileNotFoundError:
        print(f"  ERROR: tshark no encontrado en {TSHARK}")
        print("  Instala Wireshark o ajusta la variable TSHARK.")
    print()


def iniciar_tshark(pcap_path: str) -> "subprocess.Popen | None":
    iface = IFACE_WINDOWS or _autodetect_iface()
    print(f"[{_ts()}] [tshark] Iniciando captura en interfaz {iface} → {pcap_path}")
    try:
        p = subprocess.Popen(
            [TSHARK, "-i", iface, "-w", pcap_path, "-q"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        _procesos.append(p)
        time.sleep(1)  # esperar a que tshark abra la interfaz
        if p.poll() is not None:
            print(f"  [tshark] ERROR: proceso terminó inmediatamente (código {p.returncode}).")
            print("  Prueba a ejecutar como administrador o ajusta IFACE_WINDOWS.")
            return None
        print(f"  [tshark] Capturando (PID={p.pid})...")
        return p
    except FileNotFoundError:
        print(f"  [tshark] No encontrado en {TSHARK}. Instala Wireshark.")
        return None
    except Exception as e:
        print(f"  [tshark] Error: {e}")
        return None


def detener_tshark(p: "subprocess.Popen"):
    if p and p.poll() is None:
        print(f"[{_ts()}] [tshark] Deteniendo captura...")
        p.terminate()
        try:
            p.wait(timeout=10)
        except subprocess.TimeoutExpired:
            p.kill()
        print("  [tshark] Captura detenida.")

# ══════════════════════════════════════════════════════════
#  CAPTURA EN VM ADMIN (tcpdump vía SSH)
# ══════════════════════════════════════════════════════════

def _ssh_connect_admin() -> "paramiko.SSHClient | None":
    if paramiko is None:
        print("  [tcpdump] paramiko no está instalado (pip install paramiko).")
        return None
    client = paramiko.SSHClient()
    client.load_system_host_keys()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect(
            VM_ADMIN_HOST, port=VM_ADMIN_PORT,
            username=VM_ADMIN_USER,
            password=VM_ADMIN_PASS,
            key_filename=VM_ADMIN_KEY,
            timeout=10,
            allow_agent=(VM_ADMIN_PASS is None),
            look_for_keys=(VM_ADMIN_PASS is None),
        )
        return client
    except Exception as e:
        print(f"  [tcpdump] No se pudo conectar a VM admin: {e}")
        return None


def iniciar_tcpdump_remoto() -> bool:
    global _ssh_captura, _chan_tcpdump
    print(f"[{_ts()}] [tcpdump] Conectando a VM admin ({VM_ADMIN_USER}@{VM_ADMIN_HOST})...")
    client = _ssh_connect_admin()
    if client is None:
        return False
    _ssh_captura = client

    # Verificar que tcpdump está instalado
    _, out, _ = client.exec_command("which tcpdump || echo NOTFOUND")
    result = out.read().decode().strip()
    if "NOTFOUND" in result:
        print("  [tcpdump] tcpdump no instalado en la VM. Instalando...")
        client.exec_command("sudo apt-get install -y tcpdump 2>&1")
        time.sleep(5)

    cmd = (
        f"sudo tcpdump -i {IFACE_VM} -w {PCAP_VM_REMOTO} "
        f"-s 0 -q 2>&1 &"
    )
    print(f"  [tcpdump] Iniciando en VM: {cmd}")

    # Ejecutar en background remoto
    stdin, stdout, stderr = client.exec_command(
        f"sudo tcpdump -i {IFACE_VM} -w {PCAP_VM_REMOTO} -s 0 -q > /tmp/tcpdump.log 2>&1 & echo PID:$!"
    )
    out_txt = stdout.read().decode().strip()
    print(f"  [tcpdump] {out_txt}")
    time.sleep(2)

    # Verificar que está corriendo
    _, chk, _ = client.exec_command("pgrep -a tcpdump")
    chk_txt = chk.read().decode().strip()
    if chk_txt:
        print(f"  [tcpdump] Proceso activo: {chk_txt}")
        return True
    else:
        print("  [tcpdump] ADVERTENCIA: no se detectó proceso tcpdump activo.")
        return False


def _detener_tcpdump_remoto():
    global _ssh_captura, _chan_tcpdump
    if _ssh_captura is None:
        return
    print(f"[{_ts()}] [tcpdump] Deteniendo tcpdump en VM admin...")
    try:
        _ssh_captura.exec_command("sudo pkill -INT tcpdump")
        time.sleep(2)  # esperar flush a disco
        print("  [tcpdump] Detenido.")
    except Exception as e:
        print(f"  [tcpdump] Error al detener: {e}")


def descargar_pcap_vm(local_path: str) -> bool:
    """Descarga el PCAP de la VM admin al Windows host vía SFTP."""
    if _ssh_captura is None:
        return False
    print(f"[{_ts()}] [SFTP] Descargando {PCAP_VM_REMOTO} → {local_path}...")
    try:
        sftp = _ssh_captura.open_sftp()
        sftp.get(PCAP_VM_REMOTO, local_path)
        sftp.close()
        size = os.path.getsize(local_path)
        print(f"  [SFTP] Descargado ({size/1024:.1f} KB)")
        # Limpiar el temporal en la VM
        _ssh_captura.exec_command(f"rm -f {PCAP_VM_REMOTO}")
        return True
    except Exception as e:
        print(f"  [SFTP] Error descargando: {e}")
        return False


def cerrar_ssh_captura():
    global _ssh_captura
    if _ssh_captura:
        try:
            _ssh_captura.close()
        except Exception:
            pass
        _ssh_captura = None

# ══════════════════════════════════════════════════════════
#  FUSIÓN DE PCAPs (mergecap)
# ══════════════════════════════════════════════════════════

def fusionar_pcaps(archivos: list, salida: str) -> bool:
    existentes = [f for f in archivos if os.path.isfile(f)]
    if len(existentes) == 0:
        print("[mergecap] No hay archivos para fusionar.")
        return False
    if len(existentes) == 1:
        import shutil
        shutil.copy(existentes[0], salida)
        print(f"[mergecap] Solo un archivo, copiado como {salida}")
        return True

    print(f"[{_ts()}] [mergecap] Fusionando {len(existentes)} PCAPs → {salida}")
    try:
        r = subprocess.run(
            [MERGECAP, "-w", salida] + existentes,
            capture_output=True, text=True, timeout=60
        )
        if r.returncode == 0:
            size = os.path.getsize(salida)
            print(f"  [mergecap] OK — {salida} ({size/1024/1024:.2f} MB)")
            return True
        else:
            print(f"  [mergecap] ERROR: {r.stderr.strip()}")
            print(f"  Los PCAPs individuales están en: {existentes}")
            return False
    except FileNotFoundError:
        print(f"  [mergecap] No encontrado en {MERGECAP}.")
        print(f"  Instala Wireshark o fusiona manualmente:")
        print(f"  mergecap -w {salida} {' '.join(existentes)}")
        return False

# ══════════════════════════════════════════════════════════
#  LANZAMIENTO DE AGENTES
# ══════════════════════════════════════════════════════════

def _lanzar_subproceso(script: str, env_extra: dict) -> "subprocess.Popen | None":
    if not os.path.isfile(script):
        print(f"  [Agente] Script no encontrado: {script}")
        return None
    env = os.environ.copy()
    env.update(env_extra)
    print(f"  [Agente] Lanzando: {os.path.basename(script)} (env={env_extra})")
    p = subprocess.Popen([sys.executable, script], env=env)
    _procesos.append(p)
    return p


def lanzar_agentes(duracion: int):
    modo = MODO_AGENTES.lower()
    print(f"\n[{_ts()}] [Agentes] Modo={modo} | Duración={duracion}s")

    if modo in ("web", "todos"):
        # FIX: agentev7.py lee DURACION_WEB_S (antes se pasaba DURACION_TOTAL_SEGUNDOS y se ignoraba)
        _lanzar_subproceso(SCRIPT_WEB,   {"DURACION_WEB_S": str(duracion)})

    if modo in ("gamer", "todos"):
        _lanzar_subproceso(SCRIPT_GAMER, {"DURACION_GAMER_S": str(duracion)})

    if modo in ("admin", "todos"):
        # El agente admin lanza las VMs y ejecuta AgenteAdminDeRed.py remotamente
        _lanzar_subproceso(SCRIPT_ADMIN, {
            "MODO":             "ciclico",
            "CICLOS":           "1",
            "DURACION_ADMIN_S": str(duracion),
        })


def esperar_agentes(duracion: int):
    print(f"[{_ts()}] [Agentes] Esperando {duracion}s (Ctrl+C para parar antes)...")
    t0 = time.time()
    while time.time() - t0 < duracion and not _stop.is_set():
        # Si todos los agentes terminaron antes, salir
        activos = [p for p in _procesos if p and p.poll() is None]
        if not activos:
            print(f"[{_ts()}] Todos los agentes terminaron.")
            break
        time.sleep(5)


def detener_agentes():
    print(f"[{_ts()}] [Agentes] Deteniendo agentes activos...")
    for p in _procesos:
        if p and p.poll() is None:
            p.terminate()
    for p in _procesos:
        if p:
            try:
                p.wait(timeout=10)
            except subprocess.TimeoutExpired:
                p.kill()

# ══════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════

if __name__ == "__main__":
    ahora = datetime.now().strftime("%Y%m%d_%H%M%S")
    pcap_windows = os.path.join(BASE_DIR, f"{NOMBRE_PCAP}_windows_{ahora}.pcap")
    pcap_vm      = os.path.join(BASE_DIR, f"{NOMBRE_PCAP}_vm_admin_{ahora}.pcap")
    pcap_final   = os.path.join(BASE_DIR, f"{NOMBRE_PCAP}_FINAL_{ahora}.pcap")

    print("=" * 60)
    print("  Captura Combinada TFM")
    print("=" * 60)
    print(f"  Agentes:        {MODO_AGENTES}")
    print(f"  Duración:       {DURACION_S}s")
    print(f"  PCAP Windows:   {pcap_windows}")
    print(f"  PCAP VM admin:  {pcap_vm}")
    print(f"  PCAP final:     {pcap_final}")
    print("=" * 60)

    listar_interfaces_tshark()

    if IFACE_WINDOWS is None:
        print("AVISO: No has definido IFACE_WINDOWS.")
        print("Revisa la lista de arriba y ejecuta con:")
        print(f"  IFACE_WINDOWS=<número> python {os.path.basename(__file__)}")
        print("Continuando con autodetección...\n")

    # 1. Iniciar capturas
    proc_tshark = iniciar_tshark(pcap_windows)
    captura_vm_ok = False
    if MODO_AGENTES in ("admin", "todos"):
        captura_vm_ok = iniciar_tcpdump_remoto()

    time.sleep(2)  # margen para que las capturas estén listas

    # 2. Lanzar agentes
    lanzar_agentes(DURACION_S)

    # 3. Esperar duración
    esperar_agentes(DURACION_S)

    # 4. Detener agentes
    detener_agentes()

    # 5. Detener capturas
    if proc_tshark:
        detener_tshark(proc_tshark)

    if captura_vm_ok:
        _detener_tcpdump_remoto()
        time.sleep(2)
        descargar_pcap_vm(pcap_vm)

    cerrar_ssh_captura()

    # 6. Fusionar PCAPs
    print()
    archivos = []
    if proc_tshark and os.path.isfile(pcap_windows):
        archivos.append(pcap_windows)
    if captura_vm_ok and os.path.isfile(pcap_vm):
        archivos.append(pcap_vm)

    if archivos:
        fusionar_pcaps(archivos, pcap_final)
    else:
        print("[AVISO] No se generaron PCAPs.")

    print()
    print("=" * 60)
    print("  Captura completada.")
    if os.path.isfile(pcap_final):
        size = os.path.getsize(pcap_final) / 1024 / 1024
        print(f"  Archivo final: {pcap_final} ({size:.2f} MB)")
    print("=" * 60)
