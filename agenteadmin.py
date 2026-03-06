#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
v2.2.py - Multi-SSH con prechecks, fixes de auth, y reporte HTML/CSV.
"""
import json, time, pathlib, concurrent.futures as cf
import socket, errno, sys, os, logging, yaml, paramiko, csv, datetime, html
from paramiko.ssh_exception import AuthenticationException, SSHException, NoValidConnectionsError, BadHostKeyException

INVENTORY_FILE = "hosts.yaml"
LOG_DIR = pathlib.Path("logs"); LOG_DIR.mkdir(exist_ok=True)

# Debug de Paramiko
logging.basicConfig(filename="paramiko.log", level=logging.DEBUG)

BASE_COMMANDS = [
    "hostnamectl --static || hostname",
    "uptime -p || uptime",
    "ip -br a || ip a",
    "ss -tulpen || netstat -tulpen || true",
    "df -h -x tmpfs -x devtmpfs || df -h || true",  # tolerante
    "free -m || true",
    "systemctl --failed || true",
    "journalctl -p err -n 100 --no-pager || true",
]

def load_inventory(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        if not data: raise ValueError("El inventario está vacío.")
        if "hosts" not in data or not isinstance(data["hosts"], list):
            raise ValueError("Falta la clave 'hosts' o no es una lista.")
        for i, h in enumerate(data["hosts"]):
            if "host" not in h: raise ValueError(f"Entrada {i} sin 'host'.")
        return data
    except FileNotFoundError:
        sys.exit(f"[ERROR] No encuentro el inventario: {os.path.abspath(path)}")
    except yaml.YAMLError as e:
        sys.exit(f"[ERROR] YAML inválido en {path}: {e}")
    except ValueError as e:
        sys.exit(f"[ERROR] {e}")

def tcp_probe(ip, port=22, timeout=2.0):
    try:
        with socket.create_connection((ip, port), timeout=timeout) as sock:
            sock.settimeout(1.0)
            banner = ""
            try: banner = sock.recv(1024).decode(errors="ignore").strip()
            except socket.timeout: pass
            return {"state": "OPEN", "banner": banner}
    except ConnectionRefusedError:
        return {"state": "REFUSED", "banner": ""}
    except socket.timeout:
        return {"state": "TIMEOUT", "banner": ""}
    except OSError as e:
        if e.errno in (errno.EHOSTUNREACH, errno.ENETUNREACH, errno.ENETDOWN, errno.ETIMEDOUT):
            return {"state": "UNREACHABLE", "banner": ""}
        return {"state": "ERROR", "banner": "", "error": str(e)}

def _expand_path(p):
    if not p: return None
    return os.path.abspath(os.path.expanduser(os.path.expandvars(p)))

def _connect_with_prefs(client, ip, port, user, password, keyfile, allow_agent, look_for_keys):
    client.connect(
        ip, port=port, username=user, password=password, key_filename=keyfile,
        timeout=8, allow_agent=allow_agent, look_for_keys=look_for_keys, compress=True
    )

def run_host(host):
    name = host.get("name", host["host"])
    ip = host["host"]
    user = host.get("user", "kali")
    port = int(host.get("port", 22))
    keyfile_raw = host.get("keyfile")
    keyfile = _expand_path(keyfile_raw) if keyfile_raw else None
    password = host.get("password")
    use_sudo = bool(host.get("sudo", False))
    cmds = host.get("commands") or BASE_COMMANDS
    pulls = host.get("pull", [])
    allow_agent = host.get("allow_agent", True)
    look_for_keys = host.get("look_for_keys", True)

    result = {"host": name, "ip": ip, "ok": True, "errors": [], "precheck": None, "duration_s": None}
    t0 = time.time()

    # Precheck
    probe = tcp_probe(ip, port, timeout=2.0)
    result["precheck"] = probe
    if probe["state"] != "OPEN":
        result["ok"] = False
        result["errors"].append({"precheck": probe})
        result["duration_s"] = round(time.time() - t0, 2)
        return result

    # Auth prep
    if keyfile and not os.path.exists(keyfile):
        result["errors"].append({"config": f"keyfile_not_found:{keyfile}"})
        keyfile = None
    if password:
        allow_agent = False
        look_for_keys = False

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    # Conexión (con reintento si "Incorrect padding")
    try:
        try:
            _connect_with_prefs(client, ip, port, user, password, keyfile, allow_agent, look_for_keys)
        except SSHException as e:
            if "Incorrect padding" in str(e):
                _connect_with_prefs(client, ip, port, user, password, keyfile, False, False)
            else:
                raise e
    except AuthenticationException as e:
        result["ok"] = False; result["errors"].append({"connect": "AUTH_FAIL", "detail": str(e)})
        result["duration_s"] = round(time.time() - t0, 2); return result
    except NoValidConnectionsError as e:
        result["ok"] = False; result["errors"].append({"connect": "NO_VALID_CONNECTIONS", "detail": str(e)})
        result["duration_s"] = round(time.time() - t0, 2); return result
    except BadHostKeyException as e:
        result["ok"] = False; result["errors"].append({"connect": "BAD_HOST_KEY", "detail": str(e)})
        result["duration_s"] = round(time.time() - t0, 2); return result
    except SSHException as e:
        hint = "Posible llave privada corrupta o agente con entradas inválidas." if "Incorrect padding" in str(e) else None
        result["ok"] = False; result["errors"].append({"connect": "SSHException", "detail": str(e), "hint": hint})
        result["duration_s"] = round(time.time() - t0, 2); return result
    except Exception as e:
        result["ok"] = False; result["errors"].append({"connect": type(e).__name__, "detail": str(e)})
        result["duration_s"] = round(time.time() - t0, 2); return result

    # Comandos + logs JSONL
    log_file = LOG_DIR / f"{name}.jsonl"
    try:
        for cmd in cmds:
            real_cmd = f"sudo -n {cmd}" if use_sudo else cmd
            try:
                stdin, stdout, stderr = client.exec_command(real_cmd, timeout=25, get_pty=use_sudo)
                exit_status = stdout.channel.recv_exit_status()
                out = stdout.read().decode(errors="replace")
                err = stderr.read().decode(errors="replace")
                line = {"ts": time.time(), "host": name, "cmd": cmd, "exit": exit_status, "stdout": out, "stderr": err}
                with log_file.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(line, ensure_ascii=False) + "\n")
                if exit_status != 0:
                    result["errors"].append({"cmd": cmd, "exit": exit_status, "stderr": err.strip()[:200]})
            except Exception as e:
                result["errors"].append({"cmd": cmd, "error": str(e)})

        # SFTP opcional (ignora "No such file")
        if pulls:
            try:
                sftp = client.open_sftp()
                local_dir = LOG_DIR / name
                local_dir.mkdir(parents=True, exist_ok=True)
                for remote in pulls:
                    local = local_dir / pathlib.Path(remote).name
                    try:
                        sftp.get(remote, str(local))
                        with log_file.open("a", encoding="utf-8") as f:
                            f.write(json.dumps({"ts": time.time(),"host": name,"sftp": f"pulled:{remote}->{local}"}, ensure_ascii=False) + "\n")
                    except Exception as e:
                        eno = getattr(e, "errno", None)
                        if isinstance(e, FileNotFoundError) or eno == errno.ENOENT or "No such file" in str(e):
                            with log_file.open("a", encoding="utf-8") as f:
                                f.write(json.dumps({"ts": time.time(),"host": name,"sftp": f"skip_missing:{remote}"}, ensure_ascii=False) + "\n")
                        else:
                            result["errors"].append({"sftp": f"{remote}", "error": str(e)})
                sftp.close()
            except Exception as e:
                result["errors"].append({"sftp_open": str(e)})
    finally:
        client.close()
        result["duration_s"] = round(time.time() - t0, 2)
    return result

def write_reports(results):
    # CSV
    csv_path = LOG_DIR / "summary.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["host","ip","status","duration_s","errs","precheck_state","banner"])
        for r in results:
            status = "OK" if r["ok"] and not r["errors"] else ("WARN" if r["ok"] else "FAIL")
            pre = r.get("precheck", {}) or {}
            banner = pre.get("banner","")
            banner_snip = (banner[:60] + "…") if banner and len(banner) > 60 else banner
            w.writerow([r["host"], r["ip"], status, r["duration_s"], len(r["errors"]), pre.get("state"), banner_snip])

    # HTML
    html_path = LOG_DIR / "summary.html"
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    rows = []
    for r in results:
        status = "OK" if r["ok"] and not r["errors"] else ("WARN" if r["ok"] else "FAIL")
        color = {"OK":"#16a34a","WARN":"#f59e0b","FAIL":"#ef4444"}.get(status, "#64748b")
        pre = r.get("precheck", {}) or {}
        banner = html.escape(pre.get("banner",""))
        banner_snip = (banner[:80] + "…") if banner and len(banner) > 80 else banner
        errs_cnt = len(r["errors"])
        details = html.escape(json.dumps(r["errors"], ensure_ascii=False, indent=2))
        jsonl_link = f"{r['host']}.jsonl"
        host_dir = f"{r['host']}/"
        rows.append(f"""
        <tr>
          <td><b>{html.escape(r['host'])}</b></td>
          <td>{html.escape(r['ip'])}</td>
          <td><span style="color:{color};font-weight:600">{status}</span></td>
          <td style="text-align:right">{r['duration_s']}</td>
          <td style="text-align:right">{errs_cnt}</td>
          <td>{html.escape(pre.get('state',''))}</td>
          <td style="font-family:monospace">{banner_snip}</td>
          <td>
            <a href="{jsonl_link}">logs/{jsonl_link}</a>
            &nbsp;|&nbsp;<a href="{host_dir}">logs/{host_dir}</a>
            <details><summary>ver detalles</summary><pre>{details}</pre></details>
          </td>
        </tr>""")
    doc = f"""<!doctype html>
<html lang="es"><head><meta charset="utf-8">
<title>Resumen SSH</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
body{{font-family:system-ui,Segoe UI,Roboto,Helvetica,Arial,sans-serif;background:#0b1020;color:#e5e7eb;margin:0;padding:24px}}
h1{{font-size:20px;margin:0 0 6px}}
small{{color:#94a3b8}}
table{{width:100%;border-collapse:collapse;margin-top:16px;background:#0f172a;border-radius:12px;overflow:hidden}}
th,td{{padding:10px 12px;border-bottom:1px solid #1f2937;vertical-align:top}}
th{{text-align:left;background:#111827;position:sticky;top:0}}
tr:hover td{{background:#0b1226}}
code,pre{{background:#0b1226;border:1px solid #1f2937;border-radius:8px;padding:8px;display:block;white-space:pre-wrap}}
a{{color:#60a5fa;text-decoration:none}}
a:hover{{text-decoration:underline}}
summary{{cursor:pointer;color:#93c5fd}}
</style></head><body>
<h1>Resumen SSH</h1>
<small>Generado: {now} | Carpeta: logs/</small>
<table>
  <thead>
    <tr>
      <th>Host</th><th>IP</th><th>Status</th><th>Duración (s)</th>
      <th>Errores</th><th>Precheck</th><th>Banner</th><th>Artefactos</th>
    </tr>
  </thead>
  <tbody>
    {''.join(rows)}
  </tbody>
</table>
</body></html>"""
    with html_path.open("w", encoding="utf-8") as f:
        f.write(doc)
    return {"csv": str(csv_path), "html": str(html_path)}

def main():
    inv = load_inventory(INVENTORY_FILE)
    hosts = inv["hosts"]
    max_workers = min(8, len(hosts)) or 1
    print(f"Inventario: {len(hosts)} hosts. Logs -> {LOG_DIR}/ | Paramiko debug: paramiko.log")
    results = []
    with cf.ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = [ex.submit(run_host, h) for h in hosts]
        for fut in cf.as_completed(futures):
            r = fut.result(); results.append(r)
            status = "OK" if r["ok"] and not r["errors"] else ("WARN" if r["ok"] else "FAIL")
            pre = r.get("precheck", {}) or {}
            banner = pre.get("banner", "")
            banner_snip = (banner[:40] + "...") if banner and len(banner) > 43 else banner
            print(f"[{status}] {r['host']} ({r['ip']}) {r['duration_s']}s errs={len(r['errors'])} precheck={pre.get('state')} {banner_snip}  {r['errors']}")
    paths = write_reports(results)
    print(f"Reportes: {paths['html']}  |  {paths['csv']}")

if __name__ == "__main__":
    main()