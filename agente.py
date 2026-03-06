import requests
import time
import json
import tempfile
import random
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import StaleElementReferenceException

# === Configuración de la API ===
GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_API_KEY = "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"

# === Función que decide qué hacer (acción de la IA) ===
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
        "quiere navegar sin rumbo fijo"
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
        "Devuelve SOLO el JSON de la acción elegida. Sin texto adicional.\n"
        "Ejemplos válidos:\n"
        "{ \"tipo\": \"buscar_google\", \"termino\": \"últimas noticias de IA\" }\n"
        "{ \"tipo\": \"abrir_url\", \"url\": \"https://www.bbc.com/mundo\" }\n"
        "{ \"tipo\": \"mirar_youtube\", \"busqueda\": \"videos de ciberseguridad\" }\n"
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
        return json.loads(content)
    except Exception as e:
        print("❌ Error al obtener o parsear acción:", e)
        return None

# === Función que ejecuta la acción en el navegador ===
def ejecutar_accion_browser(info):
    chrome_path = r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
    chromedriver_path = r"C:\Users\juanc\Desktop\tfm\chromedriver.exe"

    options = uc.ChromeOptions()
    options.binary_location = chrome_path
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-dev-shm-usage")
    temp_profile_dir = tempfile.mkdtemp()
    options.add_argument(f"--user-data-dir={temp_profile_dir}")

    driver = uc.Chrome(
        driver_executable_path=chromedriver_path,
        browser_executable_path=chrome_path,
        options=options
    )

    try:
        if info["tipo"] == "buscar_google":
            driver.get("https://duckduckgo.com")
            try:
                aceptar_btn = WebDriverWait(driver, 5).until(
                    EC.element_to_be_clickable((By.XPATH, "//button[.//div[contains(text(),'Aceptar')]]"))
                )
                aceptar_btn.click()
                time.sleep(1)
            except:
                pass

            WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.NAME, "q")))
            search_box = driver.find_element(By.NAME, "q")
            search_box.clear()
            search_box.send_keys(info["termino"])
            search_box.send_keys(Keys.RETURN)

            try:
                WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "a[data-testid='result-title-a']"))
                )
                results = driver.find_elements(By.CSS_SELECTOR, "a[data-testid='result-title-a']")
                time.sleep(2)
                if results:
                    href = results[0].get_attribute("href")
                    print("🔗 Entrando directamente al enlace:", href)
                    driver.get(href)
                else:
                    print("⚠️ No se encontraron resultados para hacer clic.")
            except Exception as e:
                print("⚠️ Error al hacer clic en el primer resultado:", e)

        elif info["tipo"] == "abrir_url":
            driver.get(info["url"])

        elif info["tipo"] == "mirar_youtube":
            driver.get("https://www.youtube.com")
            try:
                WebDriverWait(driver, 5).until(
                    EC.element_to_be_clickable((By.XPATH, "//button[.//span[contains(text(),'Aceptar todo')]]"))
                ).click()
            except:
                pass

            busqueda = info.get("busqueda") or info.get("termino", "").strip()
            if not busqueda:
                print("🔍 No se especificó término de búsqueda.")
                return

            try:
                search_box = WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.NAME, "search_query"))
                )
                search_box.clear()
                search_box.send_keys(busqueda)
                search_box.send_keys(Keys.RETURN)
            except StaleElementReferenceException:
                search_box = WebDriverWait(driver, 5).until(
                    EC.presence_of_element_located((By.NAME, "search_query"))
                )
                search_box.clear()
                search_box.send_keys(busqueda)
                search_box.send_keys(Keys.RETURN)

            def reproducir_primer_video(driver):
                for intento in range(5):
                    try:
                        WebDriverWait(driver, 10).until(
                            EC.presence_of_element_located((By.ID, "video-title"))
                        )
                        videos = driver.find_elements(By.ID, "video-title")
                        for video in videos:
                            href = video.get_attribute("href")
                            if href and href.startswith("https://www.youtube.com/watch"):
                                print("▶️ Reproduciendo primer video:", href)
                                driver.get(href)
                                WebDriverWait(driver, 10).until(
                                    EC.presence_of_element_located((By.CLASS_NAME, 'html5-video-player'))
                                )
                                time.sleep(2)
                                try:
                                    play_btn = WebDriverWait(driver, 5).until(
                                        EC.element_to_be_clickable((By.CLASS_NAME, 'ytp-play-button'))
                                    )
                                    play_btn.click()
                                except:
                                    pass
                                return True
                    except Exception:
                        time.sleep(1)
                print("❌ No se pudo reproducir un video.")
                return False

            reproducir_primer_video(driver)
            time.sleep(30)

        else:
            print("⚠️ Acción desconocida:", info)

        time.sleep(6)

    except Exception as e:
        print("❌ Error al ejecutar acción:", e)

    finally:
        driver.quit()

# === Ejecución principal ===
if __name__ == "__main__":
    accion = obtener_accion_json_llm()
    print("🔎 Acción decidida por la IA:", accion)
    if accion:
        ejecutar_accion_browser(accion)
