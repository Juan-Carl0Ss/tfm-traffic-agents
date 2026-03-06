import subprocess
import time
import random
import os
import pyautogui
import json
import threading

# === CONFIGURACIÓN ===

DISCORD_PATH = r"C:\Users\juanc\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Discord Inc\Discord.lnk"
STEAM_PATH   = r"C:\Users\juanc\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Steam\Steam.lnk"
STEAM_GAME_ID = 489560  # Astroflux

TIEMPO_ESPERA_CARGA_JUEGO = 30  # segundos para que el juego cargue
RUTA_SECUENCIA = "secuencia_astroflux_avanzado.json"

MIN_TIEMPO_JUEGO = 180
MAX_TIEMPO_JUEGO = 480

SERVER_ICON_POS = (36, 107)
VOICE_CHANNEL_POS = (165, 551)

# ==== CONFIG DE VOZ (Discord) ====
TALK_KEY = "v"  # tecla PTT en Discord, o None si usas Voice Activity
VOICE_DEVICE_HINT = "CABLE Input"  # parte del nombre del dispositivo VB-CABLE
VOICE_SAMPLES_DIR = "voice_samples"  # carpeta con .wav
VOICE_MIN_GAP = 8
VOICE_MAX_GAP = 25
VOICE_MIN_LEN = 1.2
VOICE_MAX_LEN = 4.5

# === Módulos de audio opcionales ===
try:
    import numpy as np
    import sounddevice as sd
    import soundfile as sf
except Exception:
    np = None
    sd = None
    sf = None


# === FUNCIONES DISCORD ===
def unir_a_servidor_y_canal():
    print("🔗 Entrando a servidor de Discord...")
    pyautogui.moveTo(SERVER_ICON_POS[0], SERVER_ICON_POS[1], duration=0.8)
    pyautogui.click()
    time.sleep(3)
    print("🔉 Entrando a canal de voz...")
    pyautogui.moveTo(VOICE_CHANNEL_POS[0], VOICE_CHANNEL_POS[1], duration=0.8)
    pyautogui.click()
    time.sleep(3)
    print("✅ Conectado a canal de voz.")


def lanzar_discord():
    try:
        print("🟣 Abriendo Discord...")
        subprocess.Popen([DISCORD_PATH], shell=True)
        time.sleep(10)
        print("✅ Discord lanzado.")
    except Exception as e:
        print("❌ Error al abrir Discord:", e)


def lanzar_juego_steam(app_id):
    try:
        print(f"🎮 Abriendo juego Steam con ID {app_id}...")
        subprocess.Popen([STEAM_PATH, "-applaunch", str(app_id)], shell=True)
        print(f"⏳ Esperando {TIEMPO_ESPERA_CARGA_JUEGO} segundos para que cargue el juego...")
        time.sleep(TIEMPO_ESPERA_CARGA_JUEGO)
        print("✅ Juego cargado.")
    except Exception as e:
        print("❌ Error al abrir juego de Steam:", e)


def reproducir_secuencia(path=RUTA_SECUENCIA):
    try:
        with open(path, "r") as f:
            eventos = json.load(f)
    except Exception as e:
        print(f"❌ Error al cargar la secuencia: {e}")
        return

    print("🎬 Reproduciendo secuencia grabada...")
    start_time = time.time()

    for evento in eventos:
        tipo = evento[0]
        t = evento[1]
        espera = t - (time.time() - start_time)
        if espera > 0:
            time.sleep(espera)

        if tipo == "key_down":
            _, _, tecla = evento
            tecla = limpiar_tecla(tecla)
            pyautogui.keyDown(tecla)
            print(f"⌨️ Tecla presionada: {tecla}")

        elif tipo == "key_up":
            _, _, tecla = evento
            tecla = limpiar_tecla(tecla)
            pyautogui.keyUp(tecla)
            print(f"⌨️ Tecla soltada: {tecla}")

        elif tipo == "mouse_down":
            _, _, x, y, boton = evento
            boton_py = convertir_boton(boton)
            pyautogui.mouseDown(x=x, y=y, button=boton_py)
            print(f"🖱️ Botón {boton_py} pulsado en ({x},{y})")

        elif tipo == "mouse_up":
            _, _, x, y, boton = evento
            boton_py = convertir_boton(boton)
            pyautogui.mouseUp(x=x, y=y, button=boton_py)
            print(f"🖱️ Botón {boton_py} soltado en ({x},{y})")


def limpiar_tecla(tecla_str):
    return tecla_str.replace("Key.", "").replace("'", "").lower()


def convertir_boton(boton_str):
    if "left" in boton_str.lower():
        return "left"
    elif "right" in boton_str.lower():
        return "right"
    elif "middle" in boton_str.lower():
        return "middle"
    else:
        return "left"


def simular_tiempo_juego():
    tiempo = random.randint(MIN_TIEMPO_JUEGO, MAX_TIEMPO_JUEGO)
    print(f"🕹️ Simulando sesión de juego durante {tiempo} segundos (~{tiempo//60} min)...")
    time.sleep(tiempo)
    print("⏹️ Simulación de juego finalizada (puedes cerrarlo manualmente si lo deseas).")


# === MÓDULO DE VOZ (Discord) ===
def find_output_device(name_hint: str = VOICE_DEVICE_HINT):
    if not sd:
        return None
    for idx, d in enumerate(sd.query_devices()):
        if d.get("max_output_channels", 0) > 0 and name_hint.lower() in d.get("name", "").lower():
            return idx
    return None


def _play_array_to_device(audio, samplerate: int, device_index: int):
    if not sd:
        print("⚠️ sounddevice no instalado.")
        return
    sd.play(audio, samplerate=samplerate, device=device_index, blocking=True)


def tts_like_babble(seconds: float, samplerate: int = 16000):
    if not np:
        return None
    n = int(seconds * samplerate)
    w = np.random.randn(n).astype(np.float32)
    k = max(3, int(0.008 * samplerate))
    kernel = np.ones(k, dtype=np.float32) / k
    y = np.convolve(w, kernel, mode='same')
    env = np.clip(
        np.sin(np.linspace(0, np.pi * random.uniform(1.5, 4.0), n)) +
        0.5 * np.sin(np.linspace(0, np.pi * random.uniform(3.0, 8.0), n) + np.pi/4), 0, 1
    )
    y *= env * random.uniform(0.15, 0.35)
    y += 1e-4 * np.random.randn(n).astype(np.float32)
    return y


def discord_voice_emitter(stop_event: threading.Event):
    if not sd:
        print("ℹ️ No hay librerías de audio instaladas, no se generará voz.")
        return

    dev = find_output_device()
    if dev is None:
        print("⚠️ No encontré dispositivo de salida 'CABLE Input'.")
        return
    print(f"🔊 Usando dispositivo de salida idx={dev} (VB-CABLE)")

    while not stop_event.is_set():
        time.sleep(random.uniform(VOICE_MIN_GAP, VOICE_MAX_GAP))
        dur = random.uniform(VOICE_MIN_LEN, VOICE_MAX_LEN)
        babble = tts_like_babble(dur)
        if babble is None:
            continue

        if TALK_KEY:
            pyautogui.keyDown(TALK_KEY)
        try:
            _play_array_to_device(babble, 16000, dev)
        finally:
            if TALK_KEY:
                pyautogui.keyUp(TALK_KEY)
        time.sleep(0.2)


# === MAIN ===
if __name__ == "__main__":
    print("🧑‍💻 Simulador de Gamer iniciado...\n")

    lanzar_discord()
    time.sleep(random.randint(10, 20))

    unir_a_servidor_y_canal()

    lanzar_juego_steam(STEAM_GAME_ID)

    reproducir_secuencia()

    # Arranca voz en Discord
    voice_stop = threading.Event()
    voice_thread = threading.Thread(target=discord_voice_emitter, args=(voice_stop,), daemon=True)
    voice_thread.start()

    simular_tiempo_juego()

    voice_stop.set()
    time.sleep(0.2)

    print("\n🏁 Simulación de gamer completada.")
