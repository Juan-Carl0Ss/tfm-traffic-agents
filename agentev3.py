import requests
import time
import re
import json
import tempfile
import random
import undetected_chromedriver as uc
from datetime import datetime, timedelta
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# === CONFIGURACIÓN ===
GROQ_API_KEY = "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"
CHROME_PATH = r"C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe"
CHROMEDRIVER_PATH = r"C:\\Users\\juanc\\Desktop\\tfm\\chromedriver.exe"
DURACION_TOTAL_SEGUNDOS = 300
GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"

MAX_PESTANAS = 3

def limpiar_surrogates(texto):
    return re.sub(r'[\ud800-\udfff]', '', texto)

def obtener_accion_json_llm():
    perfiles = [
        "un estudiante de informática curioso",
        "una persona interesada en tecnología",
        "alguien que quiere ver un vídeo educativo",
        "un lector habitual de periódicos online",
        "una persona aburrida que busca algo interesante"
    ]
    intenciones = [
        "quiere ver un vídeo en YouTube",
        "quiere leer noticias actuales",
        "quiere visitar una página web interesante",
        "quiere aprender sobre un tema nuevo",
        "quiere navegar sin rumbo fijo",
        "quiere revisar su correo electrónico"
    ]
    perfil = random.choice(perfiles)
    intencion = random.choice(intenciones)
    prompt = (
        f"Eres un agente autónomo que simula el comportamiento de {perfil} que {intencion}.\n"
        "Debes elegir UNA acción para realizar en el navegador web.\n\n"
        "Opciones válidas:\n"
        "- buscar_google: requiere campo 'termino'\n"
        "- abrir_url: requiere campo 'url'\n"
        "- mirar_youtube: opcionalmente campo 'busqueda'\n\n"
        "Además, incluye un campo \"delay\" (número entero en segundos entre 8 y 25) "
        "para indicar cuánto debería esperar el agente antes de la siguiente acción.\n\n"
        "Ejemplos válidos:\n"
        "{ \"tipo\": \"buscar_google\", \"termino\": \"últimas noticias de IA\", \"delay\": 15 }\n"
        "{ \"tipo\": \"abrir_url\", \"url\": \"https://www.bbc.com/mundo\", \"delay\": 10 }\n"
        "{ \"tipo\": \"mirar_youtube\", \"busqueda\": \"videos de ciberseguridad\", \"delay\": 20 }\n"
    )
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }
    data = {
        "model": "meta-llama/llama-4-scout-17b-16e-instruct",
        "temperature": 0.9,
        "messages": [
            {"role": "system", "content": "Eres un agente que simula navegación real."},
            {"role": "user", "content": prompt}
        ]
    }
    try:
        response = requests.post(GROQ_API_URL, headers=headers, json=data)
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"].strip()
        print("📦 Respuesta bruta del LLM:\n", content)
        
        content_limpio = limpiar_surrogates(content)  # 💡 Elimina caracteres conflictivos
        return json.loads(content_limpio)
    except Exception as e:
        print("\u274c Error al obtener o parsear acción:", e)
        return None

def aceptar_cookies(driver):
    posibles_textos = [
        "aceptar", "acepto", "aceptar todo", "consentir", "permitir", "accept", "i agree", "got it", "ok",
        "aceptar cookies", "aceptar aviso de cookies", "aceptar todas las cookies", "aceptar todas las cookies",
        "aceptar cookies y continuar", "aceptar cookies y seguir navegando","permitir cookies", "permitir todas",
        "aceptar y continuar", "aceptar y leer gratis", "si", "aceptar y cerrar", "aceptar y continuar",
    ]
    try:
        botones = driver.find_elements(By.TAG_NAME, "button")
        for btn in botones:
            try:
                texto = btn.text.strip().lower()
                if any(pt in texto for pt in posibles_textos) and btn.is_displayed() and btn.is_enabled():
                    driver.execute_script("arguments[0].click();", btn)
                    time.sleep(2)
                    print("\u2705 Cookies aceptadas automáticamente.")
                    return True
            except Exception:
                continue
    except Exception:
        pass
    return False

def ejecutar_accion_browser(info, driver):
    try:
        driver.execute_script("window.open('about:blank', '_blank');")
        driver.switch_to.window(driver.window_handles[-1])
        time.sleep(1)

        if info["tipo"] == "mirar_youtube":
            driver.get("https://www.youtube.com")
            time.sleep(2)
            aceptar_cookies(driver)
            busqueda = info.get("busqueda") or info.get("termino", "").strip()
            if busqueda:
                try:
                    search_box = WebDriverWait(driver, 10).until(
                        EC.presence_of_element_located((By.NAME, "search_query"))
                    )
                    search_box.clear()
                    search_box.send_keys(busqueda)
                    search_box.send_keys(Keys.RETURN)
                    WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, "video-title")))
                    videos = driver.find_elements(By.ID, "video-title")
                    for video in videos:
                        href = video.get_attribute("href")
                        if href and href.startswith("https://www.youtube.com/watch"):
                            driver.get(href)
                            time.sleep(3)
                            aceptar_cookies(driver)

                            try:
                                # Esperar que cargue el reproductor
                                play_btn = WebDriverWait(driver, 10).until(
                                    EC.presence_of_element_located((By.CLASS_NAME, 'ytp-play-button'))
                                )
                                estado = play_btn.get_attribute("aria-label")
                                print(f"🎯 Estado del botón de reproducción: {estado}")
                                
                                # Si no está reproduciendo, hacer clic
                                if estado and "reproducir" in estado.lower() or "play" in estado.lower():
                                    driver.execute_script("arguments[0].click();", play_btn)
                                    print("▶️ Video iniciado con clic.")
                                else:
                                    print("ℹ️ El video ya estaba reproduciéndose.")
                            except Exception as e:
                                print("⚠️ Error accediendo al botón de reproducción:", e)
                                try:
                                    # Alternativa: enviar tecla 'k' (play/pause)
                                    body = driver.find_element(By.TAG_NAME, "body")
                                    body.send_keys("k")
                                    print("⌨️ Tecla 'k' enviada para iniciar reproducción.")
                                except Exception as e2:
                                    print("❌ No se pudo iniciar con tecla 'k' tampoco:", e2)

                            # Simula estar viendo el video como una persona real
                            tiempo_video = random.randint(45, 120)
                            print(f"🎥 Simulando visualización del video durante {tiempo_video} segundos...")
                            start_video = time.time()
                            while time.time() - start_video < tiempo_video:
                                accion = random.choice(["scroll", "pausa", "mouse_suave"])
                                if accion == "scroll":
                                    driver.execute_script("window.scrollBy(0, arguments[0]);", random.randint(-100, 100))
                                    print("🖱️ Scroll suave en página del video")
                                    time.sleep(random.uniform(2, 4))
                                elif accion == "mouse_suave":
                                    driver.execute_script("window.scrollBy(0, arguments[0]);", random.randint(-20, 20))
                                    time.sleep(1)
                                else:
                                    time.sleep(random.uniform(3, 6))
                            break
                except:
                    pass
        elif info["tipo"] == "buscar_google":
            driver.get("https://duckduckgo.com")
            time.sleep(2)
            aceptar_cookies(driver)
            try:
                search_box = WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.NAME, "q")))
                search_box.clear()
                search_box.send_keys(info["termino"])
                search_box.send_keys(Keys.RETURN)
                WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "a[data-testid='result-title-a']"))
                )
                results = driver.find_elements(By.CSS_SELECTOR, "a[data-testid='result-title-a']")
                if results:
                    href = results[0].get_attribute("href")
                    driver.get(href)
                    time.sleep(3)
                    aceptar_cookies(driver)
                    driver.execute_script("window.scrollBy(0, 400);")
                    time.sleep(2)
                    enlaces = driver.find_elements(By.XPATH, "//a[@href and string-length(@href) > 10]")
                    enlaces_validos = [e for e in enlaces if e.is_displayed() and e.is_enabled()]
                    if enlaces_validos:
                        enlace = random.choice(enlaces_validos)
                        try:
                            driver.execute_script("arguments[0].scrollIntoView(true);", enlace)
                            time.sleep(1)
                            driver.execute_script("arguments[0].click();", enlace)
                            time.sleep(3)
                        except Exception as e:
                            print("⚠️ Error al hacer clic con JS:", e)
            except Exception as e:
                print("❌ Error buscando en Google:", e)

        elif info["tipo"] == "abrir_url":
            url = info["url"]
            driver.get(url)
            time.sleep(2)
            aceptar_cookies(driver)
            driver.execute_script("window.scrollBy(0, 400);")
            time.sleep(2)

        # Si hay demasiadas pestañas, cierra la más antigua (excepto la base)
        if len(driver.window_handles) > MAX_PESTANAS:
            a_cerrar = driver.window_handles[1]
            driver.switch_to.window(a_cerrar)
            driver.close()
            driver.switch_to.window(driver.window_handles[0])

    except Exception as e:
        print("❌ Error ejecutando acción en navegador:", e)
        if len(driver.window_handles) > 1:
            driver.close()
            driver.switch_to.window(driver.window_handles[0])

def simular_actividad(driver, delay_segundos):
    start = time.time()
    while time.time() - start < delay_segundos:
        accion = random.choice(["scroll", "click", "mover_mouse", "pausa_corta"])
        if accion == "scroll":
            scroll_dist = random.randint(-300, 300)
            driver.execute_script(f"window.scrollBy(0, {scroll_dist});")
            print(f"⬇️ Scroll {scroll_dist}px")
            time.sleep(random.uniform(1, 3))
        elif accion == "click":
            enlaces = driver.find_elements(By.XPATH, "//a[@href and string-length(@href) > 10]")
            enlaces_validos = [e for e in enlaces if e.is_displayed() and e.is_enabled()]
            if enlaces_validos:
                enlace = random.choice(enlaces_validos)
                href = enlace.get_attribute("href")
                print(f"🔗 Click en enlace: {href}")
                try:
                    driver.execute_script("arguments[0].scrollIntoView(true);", enlace)
                    time.sleep(1)
                    driver.execute_script("arguments[0].click();", enlace)
                    time.sleep(random.uniform(3, 6))
                except Exception as e:
                    print("⚠️ Error al hacer click:", e)
            else:
                time.sleep(2)
        elif accion == "mover_mouse":
            for _ in range(random.randint(3, 6)):
                scroll_y = random.randint(-50, 50)
                driver.execute_script(f"window.scrollBy(0, {scroll_y});")
                time.sleep(0.5)
        elif accion == "pausa_corta":
            time.sleep(random.uniform(1, 2))

if __name__ == "__main__":
    fin = datetime.now() + timedelta(seconds=DURACION_TOTAL_SEGUNDOS)

    options = uc.ChromeOptions()
    options.binary_location = CHROME_PATH
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-dev-shm-usage")
    temp_profile_dir = tempfile.mkdtemp()
    options.add_argument(f"--user-data-dir={temp_profile_dir}")

    driver = uc.Chrome(
        driver_executable_path=CHROMEDRIVER_PATH,
        browser_executable_path=CHROME_PATH,
        options=options
    )

    while datetime.now() < fin:
        print(f"\n🕒 Ejecutando nueva acción ({datetime.now().strftime('%H:%M:%S')})")
        accion = obtener_accion_json_llm()
        if accion:
            print("🔎 Acción decidida por la IA:", accion)
            ejecutar_accion_browser(accion, driver)
            delay = accion.get("delay", random.randint(10, 20))
            print(f"⏳ Simulando actividad durante {delay} segundos...")
            simular_actividad(driver, delay)
        else:
            print("⚠️ No se pudo obtener acción.")
            time.sleep(5)

    driver.quit()