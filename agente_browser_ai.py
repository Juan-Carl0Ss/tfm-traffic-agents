import requests
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import StaleElementReferenceException
import time
import json
import tempfile
import random

# Configuración de la API LLM
GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_API_KEY = "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"

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
        "- leer_correo: requiere campos 'proveedor', 'usuario', 'clave'\n\n"
        "Devuelve SOLO el JSON de la acción elegida. Sin texto adicional.\n"
        "Ejemplos válidos:\n"
        "{ \"tipo\": \"buscar_google\", \"termino\": \"últimas noticias de IA\" }\n"
        "{ \"tipo\": \"abrir_url\", \"url\": \"https://www.bbc.com/mundo\" }\n"
        "{ \"tipo\": \"mirar_youtube\", \"busqueda\": \"videos de ciberseguridad\" }\n"
        "{ \"tipo\": \"leer_correo\", \"proveedor\": \"gmail\", \"usuario\": \"tucorreo@gmail.com\", \"clave\": \"tu_clave\" }\n"
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

def leer_correo(driver, info):
    if info["proveedor"] == "gmail":
        driver.get("https://mail.google.com/")
        try:
            email_input = WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.ID, "identifierId"))
            )
            email_input.send_keys("u5985395570@gmail.com")
            driver.find_element(By.ID, "identifierNext").click()

            password_input = WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.NAME, "password"))
            )
            time.sleep(1)
            password_input.send_keys("tfmjuancarlos")
            driver.find_element(By.ID, "passwordNext").click()

            WebDriverWait(driver, 30).until(
                EC.presence_of_element_located((By.XPATH, "//table"))
            )
            print("📧 Ingresaste exitosamente al correo")

            try:
                primer_correo = driver.find_element(By.XPATH, "//table//tr[1]//span[@class='bog']")
                print("📨 Asunto del primer correo:", primer_correo.text)
            except:
                print("⚠️ No se pudo leer el asunto del primer correo")

        except Exception as e:
            print("❌ Error al intentar entrar al correo:", e)

def ejecutar_accion_browser(info):
    CHROMIUM_PATH = r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
    CHROMEDRIVER_PATH = r"C:\Users\juanc\Desktop\tfm\chromedriver.exe"
    options = Options()
    options.binary_location = CHROMIUM_PATH

    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--remote-debugging-port=9222")

    temp_profile_dir = tempfile.mkdtemp()
    options.add_argument(f"--user-data-dir={temp_profile_dir}")

    service = ChromeService(executable_path=CHROMEDRIVER_PATH)
    driver = webdriver.Chrome(service=service, options=options)

    try:
        if info["tipo"] == "buscar_google":
            driver.get("https://www.duckduckgo.com")
            try:
                aceptar_btn = WebDriverWait(driver, 5).until(
                    EC.element_to_be_clickable((By.XPATH, "//button[.//div[contains(text(),'Aceptar')]]"))
                )
                aceptar_btn.click()
            except:
                pass

            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.NAME, "q"))
            )
            search_box = driver.find_element(By.NAME, "q")
            search_box.send_keys(info["termino"])
            search_box.send_keys(Keys.RETURN)

            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "a[data-testid='result-title-a']"))
            )
            results = driver.find_elements(By.CSS_SELECTOR, "a[data-testid='result-title-a']")
            if results:
                driver.get(results[0].get_attribute("href"))
            else:
                print("⚠️ No se encontraron resultados.")

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
                return

            search_box = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.NAME, "search_query"))
            )
            search_box.send_keys(busqueda)
            search_box.send_keys(Keys.RETURN)

            def reproducir_primer_video(driver):
                for _ in range(5):
                    try:
                        WebDriverWait(driver, 10).until(
                            EC.presence_of_element_located((By.ID, "video-title"))
                        )
                        videos = driver.find_elements(By.ID, "video-title")
                        for v in videos:
                            href = v.get_attribute("href")
                            if href and "watch" in href:
                                driver.get(href)
                                return
                    except:
                        time.sleep(2)
                print("❌ No se encontró un video reproducible.")

            reproducir_primer_video(driver)
            time.sleep(30)

        elif info["tipo"] == "leer_correo":
            leer_correo(driver, info)

        else:
            print("⚠️ Acción desconocida:", info)

        time.sleep(5)

    except Exception as e:
        print("❌ Error al ejecutar acción:", e)

    finally:
        driver.quit()

# === MAIN LOOP ===
if __name__ == "__main__":
    accion = obtener_accion_json_llm()
    print("🔎 Acción decidida por la IA:", accion)
    if accion:
        ejecutar_accion_browser(accion)
