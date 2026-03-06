import subprocess
import time
import random
import os
import pyautogui
import json

# === CONFIGURACIÓN ===

DISCORD_PATH = r"C:\Users\juanc\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Discord Inc\Discord.lnk"
STEAM_PATH = r"C:\Users\juanc\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Steam\Steam.lnk"
STEAM_GAME_ID = 489560  # Astroflux

TIEMPO_ESPERA_CARGA_JUEGO = 30  # segundos para que el juego cargue
RUTA_SECUENCIA = "secuencia_astroflux_avanzado.json"

MIN_TIEMPO_JUEGO = 180
MAX_TIEMPO_JUEGO = 480


SERVER_ICON_POS = (36, 107)        
VOICE_CHANNEL_POS = (165, 551)     

def unir_a_servidor_y_canal():
    print("🔗 Entrando a servidor de Discord...")
    pyautogui.moveTo(SERVER_ICON_POS[0], SERVER_ICON_POS[1], duration=0.8)
    pyautogui.click()
    time.sleep(3)  # espera que se cargue el servidor
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

        elif tipo == "scroll":
            # Opcional: puedes simular scroll aquí si quieres
            pass


def limpiar_tecla(tecla_str):
    # Limpia la cadena para que pyautogui la reconozca
    # Ejemplos:
    # "Key.space" -> "space"
    # "'a'" -> "a"
    tecla_str = tecla_str.replace("Key.", "").replace("'", "")
    # pyautogui usa nombres como "space", "enter", "shift"
    return tecla_str.lower()


def convertir_boton(boton_str):
    # Convierte la cadena de pynput a formato pyautogui
    # pynput usa "Button.left", "Button.right"
    if "left" in boton_str.lower():
        return "left"
    elif "right" in boton_str.lower():
        return "right"
    elif "middle" in boton_str.lower():
        return "middle"
    else:
        return "left"  # por defecto


def simular_tiempo_juego():
    tiempo = random.randint(MIN_TIEMPO_JUEGO, MAX_TIEMPO_JUEGO)
    print(f"🕹️ Simulando sesión de juego durante {tiempo} segundos (~{tiempo//60} min)...")
    time.sleep(tiempo)
    print("⏹️ Simulación de juego finalizada (puedes cerrarlo manualmente si lo deseas).")


if __name__ == "__main__":
    print("🧑‍💻 Simulador de Gamer iniciado...\n")

    lanzar_discord()
    time.sleep(random.randint(10, 20))
    
    unir_a_servidor_y_canal()

    lanzar_juego_steam(STEAM_GAME_ID)

    reproducir_secuencia()

    simular_tiempo_juego()

    print("\n🏁 Simulación de gamer completada.")
