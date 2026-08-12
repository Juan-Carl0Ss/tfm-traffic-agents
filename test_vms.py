#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_vms.py — Prueba de arranque de VMs y conectividad SSH.
Ejecuta esto ANTES de usar agenteadminavanzado.py para verificar
que VBoxManage funciona y las VMs son accesibles por SSH.
"""

import subprocess
import socket
import time

# ── Configuración (debe coincidir con agenteadminavanzado.py) ──
VBOXMANAGE = r"C:\Program Files\Oracle\VirtualBox\VBoxManage.exe"

VMS = [
    {"vm_name": "kali-linux-2023.1-virtualbox-amd64",   "host": "10.10.0.1", "port": 22, "user": "kali", "rol": "ADMIN"},
    {"vm_name": "kali-linux-2023.1-virtualbox-amd6_2",  "host": "10.10.0.2", "port": 22, "user": "kali", "rol": "SRV1"},
    {"vm_name": "kali-linux-2023.1-virtualbox-amd6_3",  "host": "10.10.0.3", "port": 22, "user": "kali", "rol": "SRV2"},
]

VM_BOOT_TIMEOUT  = 120  # segundos máximo esperando SSH
VM_POLL_INTERVAL = 5    # cada cuántos segundos sondear

# ──────────────────────────────────────────────────────────────

def check_vboxmanage():
    print("=" * 55)
    print("1. Verificando VBoxManage...")
    try:
        r = subprocess.run([VBOXMANAGE, "--version"], capture_output=True, text=True, timeout=10)
        if r.returncode == 0:
            print(f"   OK  VBoxManage v{r.stdout.strip()}")
            return True
        else:
            print(f"   ERROR: {r.stderr.strip()}")
            return False
    except FileNotFoundError:
        print(f"   ERROR: No encontrado en {VBOXMANAGE}")
        print("   Edita VBOXMANAGE en este script con la ruta correcta.")
        return False


def list_vms():
    print("\n2. VMs registradas en VirtualBox:")
    try:
        r = subprocess.run([VBOXMANAGE, "list", "vms"], capture_output=True, text=True, timeout=10)
        for line in r.stdout.strip().splitlines():
            print(f"   {line}")
    except Exception as e:
        print(f"   ERROR: {e}")


def get_vm_state(vm_name):
    try:
        r = subprocess.run(
            [VBOXMANAGE, "showvminfo", vm_name, "--machinereadable"],
            capture_output=True, text=True, timeout=15
        )
        for line in r.stdout.splitlines():
            if line.startswith("VMState="):
                return line.split("=", 1)[1].strip('"').lower()
    except Exception:
        pass
    return "desconocido"


def start_vm(vm_name):
    state = get_vm_state(vm_name)
    if state == "running":
        print(f"   Ya estaba en ejecución.")
        return True
    print(f"   Estado actual: {state}. Iniciando...", end="", flush=True)
    try:
        r = subprocess.run(
            [VBOXMANAGE, "startvm", vm_name, "--type", "gui"],
            capture_output=True, text=True, timeout=60
        )
        if r.returncode == 0:
            print(" OK")
            return True
        else:
            print(f" ERROR: {r.stderr.strip()}")
            return False
    except Exception as e:
        print(f" EXCEPCIÓN: {e}")
        return False


def wait_ssh(host, port, timeout=VM_BOOT_TIMEOUT):
    t0 = time.time()
    print(f"   Esperando SSH en {host}:{port} (max {timeout}s)...", end="", flush=True)
    while time.time() - t0 < timeout:
        try:
            with socket.create_connection((host, port), timeout=2):
                elapsed = int(time.time() - t0)
                print(f" ABIERTO en {elapsed}s")
                return True
        except Exception:
            print(".", end="", flush=True)
            time.sleep(VM_POLL_INTERVAL)
    print(f" TIMEOUT ({timeout}s)")
    return False


def test_ssh_banner(host, port):
    """Conecta TCP y lee el banner SSH para confirmar que es OpenSSH."""
    try:
        with socket.create_connection((host, port), timeout=3) as s:
            s.settimeout(2)
            banner = s.recv(256).decode(errors="ignore").strip()
            print(f"   Banner SSH: {banner}")
    except Exception as e:
        print(f"   No se pudo leer banner: {e}")


# ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 55)
    print("  TEST DE VMs — agenteadminavanzado")
    print("=" * 55)

    if not check_vboxmanage():
        print("\nCORRIGE la ruta a VBoxManage antes de continuar.")
        exit(1)

    list_vms()

    print("\n3. Arrancando y verificando cada VM:")
    print("=" * 55)

    resultados = []
    for vm in VMS:
        name = vm["vm_name"]
        host = vm["host"]
        port = vm["port"]
        rol  = vm["rol"]
        print(f"\n  [{rol}] {name}")
        arrancada = start_vm(name)
        if arrancada:
            time.sleep(2)  # pequeña espera antes de sondear
            ssh_ok = wait_ssh(host, port)
            if ssh_ok:
                test_ssh_banner(host, port)
        else:
            ssh_ok = False
        resultados.append((rol, name, host, arrancada, ssh_ok))

    print("\n" + "=" * 55)
    print("  RESUMEN")
    print("=" * 55)
    todo_ok = True
    for rol, name, host, arrancada, ssh_ok in resultados:
        vm_str  = "OK " if arrancada else "FAIL"
        ssh_str = "OK " if ssh_ok   else "FAIL"
        print(f"  [{rol:5s}] VM={vm_str}  SSH={ssh_str}  {host}  ({name})")
        if not arrancada or not ssh_ok:
            todo_ok = False

    print("=" * 55)
    if todo_ok:
        print("  Todas las VMs listas. Puedes ejecutar agenteadminavanzado.py")
    else:
        print("  Hay problemas. Revisa los errores arriba.")
    print("=" * 55)
