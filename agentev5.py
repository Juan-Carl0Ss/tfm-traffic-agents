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
from selenium.common.exceptions import TimeoutException

# === CONFIGURACIÓN ===
GROQ_API_KEY = "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"
CHROME_PATH = r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
CHROMEDRIVER_PATH = r"C:\Users\juanc\Desktop\tfm\chromedriver.exe"
GMAIL_USER = "u5985395570@gmail.com"
GMAIL_PASSWORD = "tfmjuancarlos"
DURACION_TOTAL_SEGUNDOS = 300
GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"

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
        "quiere revisar su correo electrónico",
        "quiere ver un streaming en vivo"
    ]
    perfil = random.choice(perfiles)
    intencion = random.choice(intenciones)
    prompt = (
        f"Eres un agente autónomo que simula el comportamiento de {perfil} que {intencion}.\n"
        "Debes elegir UNA acción para realizar en el navegador web.\n\n"
        "Opciones válidas:\n"
        "- buscar_google: requiere campo 'termino'\n"
        "- abrir_url: requiere campo 'url'\n"
        "- mirar_youtube: opcionalmente campo 'busqueda'\n"
        "- revisar_correo: no requiere campos adicionales\n"
        "- ver_streaming: opcionalmente campo 'plataforma' con valores 'twitch' o 'youtube'\n\n"
        "Además, incluye un campo \"delay\" (número entero en segundos entre 8 y 25) "
        "para indicar cuánto debería esperar el agente antes de la siguiente acción.\n\n"
        "Ejemplos válidos:\n"
        "{ \"tipo\": \"buscar_google\", \"termino\": \"últimas noticias de IA\", \"delay\": 15 }\n"
        "{ \"tipo\": \"abrir_url\", \"url\": \"https://www.bbc.com/mundo\", \"delay\": 10 }\n"
        "{ \"tipo\": \"mirar_youtube\", \"busqueda\": \"videos de ciberseguridad\", \"delay\": 20 }\n"
        "{ \"tipo\": \"revisar_correo\", \"delay\": 20 }\n"
        "{ \"tipo\": \"ver_streaming\", \"plataforma\": \"twitch\", \"delay\": 18 }"
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
        raw_content = response.json()
        print("📦 Respuesta completa del servidor:\n", raw_content)

        content = raw_content["choices"][0]["message"]["content"].strip()
        print("📦 Contenido generado:\n", content)

        if not content.startswith("{"):
            raise ValueError("La respuesta no parece ser JSON.")

        return json.loads(limpiar_surrogates(content))
    except Exception as e:
        print("❌ Error al obtener o parsear acción:", e)
        return None

def aceptar_cookies(driver):
    try:
        selectors = [
            "button[aria-label*='accept cookies']", "button[aria-label*='aceptar cookies']",
            "#onetrust-accept-btn-handler", ".onetrust-close-btn-ui",
            "button[data-purpose*='accept']", "button[data-cookiebanner*='accept']"
        ]
        for sel in selectors:
            els = driver.find_elements(By.CSS_SELECTOR, sel)
            for el in els:
                if el.is_displayed() and el.is_enabled():
                    el.click()
                    print(f"✅ Cookies: clic en selector '{sel}'")
                    time.sleep(1)
                    return True

        frases = [
            "aceptar todo", "aceptar y continuar", "aceptar y cerrar", "acepto", "aceptar",
            "aceptar cookies", "aceptar aviso de cookies", "aceptar todas las cookies",
            "consentir", "permitir", "sí, acepto", "si, acepto", "ok, acepto",
            "dar permiso", "conceder permiso", "continuar",
            "accept all", "accept cookies", "i agree", "allow all", "allow cookies", "got it"
        ]
        elements = driver.find_elements(By.XPATH, "//button|//a|//input[@type='button']")
        for el in elements:
            text = (el.text or el.get_attribute('value') or '').strip().lower()
            if any(fr in text for fr in frases) and el.is_displayed() and el.is_enabled():
                el.click()
                print(f"✅ Cookies: clic en '{text}'")
                time.sleep(1)
                return True

        iframes = driver.find_elements(By.TAG_NAME, "iframe")
        for iframe in iframes:
            try:
                driver.switch_to.frame(iframe)
                botones = driver.find_elements(By.XPATH, "//button | //div[@role='button']")
                for btn in botones:
                    txt = (btn.text or "").lower()
                    if "aceptar todo" in txt or "accept all" in txt:
                        btn.click()
                        print("✅ Consentimiento Google/YouTube aceptado")
                        time.sleep(2)
                        driver.switch_to.default_content()
                        return True
                driver.switch_to.default_content()
            except Exception:
                driver.switch_to.default_content()
                continue
    except Exception as e:
        print(f"⚠️ Error al aceptar cookies: {e}")
    return False

def youtube_click_random_organic_result(driver, only_live=False, timeout=10):
    """
    Hace clic en un resultado orgánico (no anuncio) de la página de resultados de YouTube.
    Si only_live=True, prioriza vídeos con overlay de EN DIRECTO / LIVE.
    """
    # Asegura aceptar cookies primero
    try:
        aceptar_cookies(driver)
    except Exception:
        pass

    # Hacemos un pequeño scroll para cargar más resultados
    for _ in range(random.randint(1, 3)):
        driver.execute_script("window.scrollBy(0, document.body.scrollHeight * 0.25);")
        time.sleep(random.uniform(0.8, 1.5))

    # En buscador, los resultados orgánicos están en ytd-video-renderer (los anuncios NO)
    candidatos = driver.find_elements(
        By.XPATH, "//ytd-video-renderer//a[@id='video-title' or @id='video-title-link']"
    )

    # Si se desea LIVE, filtramos por overlay de directo
    if only_live:
        vivos = []
        for a in candidatos:
            try:
                # Subimos al contenedor del resultado
                cont = a.find_element(By.XPATH, "./ancestor::ytd-video-renderer[1]")
                # Overlay LIVE/EN DIRECTO
                live_badge = cont.find_elements(
                    By.XPATH, ".//ytd-thumbnail-overlay-time-status-renderer[@overlay-style='LIVE']"
                )
                if live_badge:
                    vivos.append(a)
            except Exception:
                continue
        if vivos:
            candidatos = vivos

    # Si no hay orgánicos (raro), hacemos fallback a cualquier <a id=video-title> que NO esté dentro de un ad
    if not candidatos:
        candidatos = driver.find_elements(
            By.XPATH,
            "//a[@id='video-title' or @id='video-title-link']"
            "[not(ancestor::ytd-ad-slot-renderer) and not(ancestor::ytd-promoted-video-renderer)]"
        )

    if not candidatos:
        print("⚠️ No encontré resultados orgánicos en YouTube.")
        return False

    objetivo = random.choice(candidatos)
    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", objetivo)
    time.sleep(random.uniform(0.3, 0.8))
    objetivo.click()
    return True


def youtube_skip_preroll_if_any(driver, max_wait_seconds=20):
    """
    Si aparece anuncio pre-roll, intenta saltarlo en cuanto esté disponible.
    Devuelve True si detectó/intentó saltar anuncios, False si no hubo anuncios.
    """
    start = time.time()
    saw_ad = False
    while time.time() - start < max_wait_seconds:
        try:
            # Indicadores de anuncio en el player
            ad_showing = driver.find_elements(By.CSS_SELECTOR, ".ad-showing, .ytp-ad-player-overlay, .ytp-ad-module")
            if ad_showing:
                saw_ad = True
            # Botón "Saltar anuncio" (variantes modernas/clásicas y localizaciones ES/EN)
            skip_btn = WebDriverWait(driver, 2).until(EC.element_to_be_clickable((
                By.XPATH,
                "//button[contains(@class,'ytp-ad-skip-button') or contains(@class,'ytp-ad-skip-button-modern') or "
                "contains(., 'Saltar') or contains(., 'Skip')]"
            )))
            try:
                skip_btn.click()
            except Exception:
                driver.execute_script("arguments[0].click();", skip_btn)
            # Dar un respiro al player
            time.sleep(1.0)
            break
        except TimeoutException:
            # No hay botón todavía; esperamos un poco y reintentamos
            time.sleep(0.5)
    return saw_ad

def ejecutar_accion_browser(info, driver):
    try:
        if info["tipo"] == "mirar_youtube":
            driver.get(f"https://www.youtube.com/results?search_query={query.replace(' ', '+')}")
            time.sleep(2)
            aceptar_cookies(driver)

            if youtube_click_random_organic_result(driver, only_live=False):
                # Si hay pre-roll, intentar saltarlo
                youtube_skip_preroll_if_any(driver, max_wait_seconds=25)
            else:
                print("⚠️ Sin resultados orgánicos en YouTube.")

        elif info["tipo"] == "buscar_google":
            termino = info.get("termino", "").strip()
            driver.get("https://www.google.com/search?q=" + termino.replace(' ', '+'))
            time.sleep(2)
            aceptar_cookies(driver)
            resultados = driver.find_elements(By.CSS_SELECTOR, "div.g a")
            for a in resultados:
                href = a.get_attribute('href')
                if href and href.startswith('http') and 'google' not in href:
                    driver.get(href)
                    time.sleep(3)
                    break

        elif info["tipo"] == "abrir_url":
            driver.get(info["url"])
            time.sleep(2)
            aceptar_cookies(driver)

        elif info["tipo"] == "revisar_correo":
            driver.get("https://accounts.google.com/signin/v2/identifier?service=mail")
            try:
                WebDriverWait(driver, 15).until(
                    EC.presence_of_element_located((By.ID, "identifierId"))
                )
                input_usuario = driver.find_element(By.ID, "identifierId")
                input_usuario.clear()
                input_usuario.send_keys(GMAIL_USER)
                input_usuario.send_keys(Keys.ENTER)
                print("✅ Usuario introducido")

                WebDriverWait(driver, 15).until(
                    EC.presence_of_element_located((By.NAME, "Passwd"))
                )
                input_pw = driver.find_element(By.NAME, "Passwd")
                input_pw.clear()
                input_pw.send_keys(GMAIL_PASSWORD)
                input_pw.send_keys(Keys.ENTER)
                print("🔑 Contraseña introducida")

                WebDriverWait(driver, 25).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "tr.zA"))
                )
                aceptar_cookies(driver)
                driver.find_elements(By.CSS_SELECTOR, "tr.zA")[0].click()
                print("📬 Primer correo abierto")

            except Exception as e:
                print("❌ Error al revisar el correo:", e)

        elif info["tipo"] == "ver_streaming":
            plataforma = info.get("plataforma", "twitch").lower()

            def scroll_un_poco(driver, veces=3):
                for _ in range(veces):
                    driver.execute_script("window.scrollBy(0, document.body.scrollHeight * 0.3);")
                    time.sleep(random.uniform(1.2, 2.2))

            if plataforma == "twitch":
                # Abrir el directorio de directos ordenado por espectadores (DOM más estable que home)
                driver.get("https://www.twitch.tv/directory/all?sort=VIEWER_COUNT")
                time.sleep(3)
                aceptar_cookies(driver)
                scroll_un_poco(driver, veces=random.randint(2, 5))

                # Recoger enlaces aparentes a canales /<nombre>
                # Filtramos rutas cortas sin subrutas para evitar /directory /videos /p/ etc.
                candidatos = driver.find_elements(
                    By.XPATH,
                    "//a[starts-with(@href,'/') and " 
                    "not(contains(@href,'/directory')) and "
                    "not(contains(@href,'/videos')) and "
                    "not(contains(@href,'/p/')) and "
                    "not(contains(@href,'/profile')) and "
                    "string-length(@href) > 1 and "
                    "not(contains(@href,'/settings'))]"
                )

                hrefs = []
                for a in candidatos:
                    try:
                        h = a.get_attribute("href") or ""
                        # Nos quedamos con /<canal> (sin más /)
                        # y descartamos duplicados
                        if re.match(r"^https?://(www\.)?twitch\.tv/[A-Za-z0-9_]+/?$", h):
                            hrefs.append(h.rstrip("/"))
                    except Exception:
                        pass

                hrefs = list(set(hrefs))  # dedupe
                if hrefs:
                    url_canal = random.choice(hrefs)
                    driver.get(url_canal)
                    print(f"📺 Viendo stream aleatorio en Twitch: {url_canal}")
                    time.sleep(4)
                    # Si aparece el botón de reproducción/consentimiento, intentar clic
                    try:
                        aceptar_cookies(driver)
                        # Botón de reproducir overlay
                        play = WebDriverWait(driver, 5).until(
                            EC.presence_of_element_located((By.XPATH, "//button[contains(@data-a-target,'player-play-pause-button') or @aria-label='Play' or @aria-label='Reproducir']"))
                        )
                        if play.is_displayed() and play.is_enabled():
                            play.click()
                    except Exception:
                        pass
                else:
                    print("⚠️ No pude encontrar canales en el directorio. Intento con YouTube Live como respaldo.")
                    plataforma = "youtube"  # fallback

            if plataforma != "twitch":
                # Búsqueda aleatoria de directos en YouTube
                busqueda = random.choice([
                    "gaming en vivo", "noticias en vivo", "música en vivo",
                    "just chatting live", "esports live", "programación en vivo"
                ])
                # Filtro LIVE en resultados (&sp=EgJAAQ%3D%3D)
                driver.get(f"https://www.youtube.com/results?search_query={busqueda.replace(' ', '+')}&sp=EgJAAQ%253D%253D")
                time.sleep(2)
                aceptar_cookies(driver)

                if youtube_click_random_organic_result(driver, only_live=True):
                    youtube_skip_preroll_if_any(driver, max_wait_seconds=25)
                else:
                    print("⚠️ No encontré directos orgánicos en YouTube.")

    except Exception as e:
        print("❌ Error acción navegador:", e)

def simular_actividad(driver, delay):
    start = time.time()
    while time.time() - start < delay:
        accion = random.choice(["scroll", "pausa"])
        if accion == "scroll":
            distancia = random.randint(100, 300)
            driver.execute_script(f"window.scrollBy(0, {distancia});")
            print(f"⬇️ Scroll {distancia}px")
        time.sleep(random.uniform(2, 5))

if __name__ == "__main__":
    fin = datetime.now() + timedelta(seconds=DURACION_TOTAL_SEGUNDOS)
    options = uc.ChromeOptions()
    options.binary_location = CHROME_PATH
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    temp_dir = tempfile.mkdtemp()
    options.add_argument(f"--user-data-dir={temp_dir}")
    driver = uc.Chrome(
        driver_executable_path=CHROMEDRIVER_PATH,
        browser_executable_path=CHROME_PATH,
        options=options
    )

    while datetime.now() < fin:
        print(f"🕒 Ejecutando nueva acción ({datetime.now().strftime('%H:%M:%S')})")
        accion = obtener_accion_json_llm()
        if accion:
            print("🔎 Acción decidida por la IA:", accion)
            ejecutar_accion_browser(accion, driver)
            delay = accion.get("delay", random.randint(8, 25))
            print(f"⏳ Simulando actividad durante {delay} segundos...")
            simular_actividad(driver, delay)
        else:
            print("⚠️ No se pudo obtener acción.")
            time.sleep(5)

    driver.quit()
