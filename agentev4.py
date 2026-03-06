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
CHROME_PATH = r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
CHROMEDRIVER_PATH = r"C:\Users\juanc\Desktop\tfm\chromedriver.exe"
GMAIL_USER = "u5985395570@gmail.com"  # Pon aquí tu correo de Gmail
GMAIL_PASSWORD = "tfmjuancarlos"      # Pon aquí tu contraseña de Gmail
DURACION_TOTAL_SEGUNDOS = 300
GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"

# Se trabaja siempre en la misma ventana del navegador

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
        "- mirar_youtube: opcionalmente campo 'busqueda'\n"
        "- revisar_correo: no requiere campos adicionales, abre tu bandeja de entrada\n\n"
        "Además, incluye un campo \"delay\" (número entero en segundos entre 8 y 25) "
        "para indicar cuánto debería esperar el agente antes de la siguiente acción.\n\n"
        "Ejemplos válidos:\n"
        "{ \"tipo\": \"buscar_google\", \"termino\": \"últimas noticias de IA\", \"delay\": 15 }\n"
        "{ \"tipo\": \"abrir_url\", \"url\": \"https://www.bbc.com/mundo\", \"delay\": 10 }\n"
        "{ \"tipo\": \"mirar_youtube\", \"busqueda\": \"videos de ciberseguridad\", \"delay\": 20 }\n"
        "{ \"tipo\": \"revisar_correo\", \"delay\": 20 }"
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

        # Validar que parezca un JSON antes de intentar parsear
        if not content.startswith("{"):
            raise ValueError("La respuesta no parece ser JSON.")

        return json.loads(limpiar_surrogates(content))
    except Exception as e:
        print("❌ Error al obtener o parsear acción:", e)
        return None

# Función mejorada para aceptar diferentes tipos de banners de cookies

def aceptar_cookies(driver):
    """
    Intenta aceptar banners de cookies tanto genéricos como los específicos de Google/YouTube.
    """
    try:
        # === INTENTO GENERAL (como ya tienes) ===
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

        # === CONSENTIMIENTO DE YOUTUBE / GOOGLE ===
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
            except Exception as e:
                driver.switch_to.default_content()
                continue
    except Exception as e:
        print(f"⚠️ Error al aceptar cookies: {e}")
    return False


def ejecutar_accion_browser(info, driver):
    try:
        if info["tipo"] == "mirar_youtube":
            query = info.get("busqueda", "").strip()
            driver.get(f"https://www.youtube.com/results?search_query={query.replace(' ', '+')}")
            time.sleep(2)
            aceptar_cookies(driver)
            WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((By.ID, "video-title"))
            ).click()
            time.sleep(4)

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
                # Esperar campo de email
                WebDriverWait(driver, 15).until(
                    EC.presence_of_element_located((By.ID, "identifierId"))
                )
                input_usuario = driver.find_element(By.ID, "identifierId")
                input_usuario.clear()
                input_usuario.send_keys(GMAIL_USER)
                input_usuario.send_keys(Keys.ENTER)
                print("✅ Usuario introducido")

                # Esperar campo de contraseña
                WebDriverWait(driver, 15).until(
                    EC.presence_of_element_located((By.NAME, "Passwd"))
                )
                input_pw = driver.find_element(By.NAME, "Passwd")
                input_pw.clear()
                input_pw.send_keys(GMAIL_PASSWORD)
                input_pw.send_keys(Keys.ENTER)
                print("🔑 Contraseña introducida")

                # Esperar bandeja de entrada
                WebDriverWait(driver, 25).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "tr.zA"))
                )
                aceptar_cookies(driver)

                # Abrir primer correo
                driver.find_elements(By.CSS_SELECTOR, "tr.zA")[0].click()
                print("📬 Primer correo abierto")

            except Exception as e:
                print("❌ Error al revisar el correo:", e)

    except Exception as e:
        print("❌ Error acción navegador:", e)


def simular_actividad(driver, delay):
    start = time.time()
    while time.time() - start < delay:
        accion = random.choice(["scroll", "pausa_corta"])
        if accion == "scroll":
            distancia = random.randint(100, 400)
            driver.execute_script(f"window.scrollBy(0, {distancia});")
            print(f"⬇️ Scroll {distancia}px")
            time.sleep(1)
        else:
            time.sleep(random.uniform(1, 2))


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