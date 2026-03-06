import json
import time
from pynput import keyboard, mouse

acciones = []
start_time = None

# Estado actual de teclas y botones pulsados (para combinaciones)
teclas_presionadas = set()
botones_presionados = set()

stop_program = False  # Flag para detener la grabación

def timestamp():
    return time.time() - start_time

# --- EVENTOS TECLADO ---
def on_key_press(key):
    try:
        if key not in teclas_presionadas:
            teclas_presionadas.add(key)
            acciones.append(["key_down", timestamp(), str(key)])
    except Exception:
        pass

def on_key_release(key):
    global stop_program
    try:
        if key in teclas_presionadas:
            teclas_presionadas.remove(key)
            acciones.append(["key_up", timestamp(), str(key)])
        # Parar grabación con ESC
        if key == keyboard.Key.esc:
            print("Grabación finalizada.")
            stop_program = True
            return False  # Detiene el listener del teclado
    except Exception:
        pass

# --- EVENTOS RATÓN ---
def on_click(x, y, button, pressed):
    try:
        if pressed:
            botones_presionados.add(button)
            acciones.append(["mouse_down", timestamp(), x, y, str(button)])
        else:
            if button in botones_presionados:
                botones_presionados.remove(button)
            acciones.append(["mouse_up", timestamp(), x, y, str(button)])
    except Exception:
        pass

def on_scroll(x, y, dx, dy):
    acciones.append(["scroll", timestamp(), x, y, dx, dy])

if __name__ == "__main__":
    print("Iniciando grabación... Presiona ESC para terminar.")
    start_time = time.time()

    with keyboard.Listener(on_press=on_key_press, on_release=on_key_release) as kl, \
         mouse.Listener(on_click=on_click, on_scroll=on_scroll) as ml:

        while not stop_program:
            time.sleep(0.1)

    # Guardar acciones en JSON
    with open("secuencia_astroflux_avanzado.json", "w") as f:
        json.dump(acciones, f, indent=2)

    print(f"Grabación guardada en secuencia_astroflux_avanzado.json")
