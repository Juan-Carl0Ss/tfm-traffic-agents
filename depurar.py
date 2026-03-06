import os
import time
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException

# ====== CREDENCIALES (usa tu correo y contraseña de Google) ======
GMAIL_USER = "u5985395570@gmail.com"
GMAIL_PASSWORD = "tfmjuancarlos"

# ====== TU USUARIO DE TWITTER (para el paso extra) ======
TWITTER_USERNAME = "@juancar61453952"  # el script quitará la @ automáticamente

# ====== RUTAS CHROME ======
CHROME_PATH = r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
CHROMEDRIVER_PATH = r"C:\Users\juanc\Desktop\tfm\chromedriver.exe"

# ====== PERFIL PERSISTENTE (para guardar sesión) ======
PROFILE_DIR = r"C:\Users\juanc\Desktop\tfm\chrome_profile_tfm"
os.makedirs(PROFILE_DIR, exist_ok=True)

def aceptar_cookies(driver):
    try:
        selectors = [
            "button[aria-label*='accept']", "button[aria-label*='aceptar']",
            "#onetrust-accept-btn-handler", ".onetrust-close-btn-ui",
            "button[data-cookiebanner*='accept']", "button[data-purpose*='accept']"
        ]
        for sel in selectors:
            for el in driver.find_elements(By.CSS_SELECTOR, sel):
                if el.is_displayed() and el.is_enabled():
                    try:
                        el.click(); time.sleep(0.3); return True
                    except Exception:
                        pass

        frases = [
            "aceptar", "aceptar todo", "continuar", "permitir",
            "accept", "accept all", "allow", "got it", "i agree"
        ]
        for el in driver.find_elements(By.XPATH, "//button|//a|//div[@role='button']"):
            txt = (el.text or el.get_attribute("aria-label") or "").strip().lower()
            if any(fr in txt for fr in frases) and el.is_displayed() and el.is_enabled():
                try:
                    el.click(); time.sleep(0.3); return True
                except Exception:
                    pass
    except Exception:
        pass
    return False

def is_twitter_logged_in(driver, timeout=6):
    try:
        driver.get("https://twitter.com/home")
        WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((By.XPATH, "//div[@data-testid='primaryColumn']"))
        )
        print("✅ Ya estás logueado en Twitter/X (sesión activa).")
        return True
    except TimeoutException:
        return False

def login_twitter_con_email_password(driver):
    """
    Login en Twitter/X con email (GMAIL_USER) y password (GMAIL_PASSWORD).
    Maneja el paso intermedio de 'teléfono o nombre de usuario' usando TWITTER_USERNAME.
    """
    driver.get("https://twitter.com/i/flow/login")
    time.sleep(2)
    aceptar_cookies(driver)

    try:
        # 1) Campo inicial: "Phone, email, or username"
        user_in = WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.XPATH, "//input[@name='text' or @autocomplete='username']"))
        )
        user_in.clear()
        user_in.send_keys(GMAIL_USER)
        user_in.send_keys(Keys.ENTER)
        print("📧 Email enviado")
        time.sleep(1.2)

        # 2) ¿Piden 'teléfono o nombre de usuario'?
        #    Si no aparece la contraseña en unos segundos, rellenamos el paso extra.
        try:
            WebDriverWait(driver, 4).until(
                EC.presence_of_element_located((By.XPATH, "//input[@name='password' or @type='password']"))
            )
            print("➡️ Password solicitado directamente (sin paso extra).")
        except TimeoutException:
            # Rellenar paso extra con tu @usuario (sin la @)
            sanitized_username = TWITTER_USERNAME.lstrip("@").strip()
            try:
                extra_in = WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.XPATH, "//input[@name='text' or @data-testid='ocfEnterTextTextInput']"))
                )
                extra_in.clear()
                extra_in.send_keys(sanitized_username)
                extra_in.send_keys(Keys.ENTER)
                print(f"🧩 Paso extra enviado con usuario: {sanitized_username}")
                time.sleep(1.2)
            except TimeoutException:
                print("⚠️ No apareció el campo del paso extra; continuando…")

        # 3) Contraseña
        pw_in = WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.XPATH, "//input[@name='password' or @type='password']"))
        )
        pw_in.clear()
        pw_in.send_keys(GMAIL_PASSWORD)

        # Botón "Iniciar sesión" o ENTER
        try:
            login_btn = driver.find_element(
                By.XPATH, "//span[normalize-space(text())='Iniciar sesión' or normalize-space(text())='Log in']/ancestor::*[@role='button'][1]"
            )
            driver.execute_script("arguments[0].click();", login_btn)
        except NoSuchElementException:
            pw_in.send_keys(Keys.ENTER)

        print("🔑 Contraseña enviada")
        time.sleep(2)

        # 4) Si hay challenge/2FA, se requiere intervención manual.
        if "challenge" in (driver.current_url or ""):
            print("⚠️ Se detectó un challenge/2FA. Completa manualmente una vez; quedará guardado en el perfil.")
            return False

        # 5) Esperar el timeline/home
        WebDriverWait(driver, 30).until(
            EC.presence_of_element_located((By.XPATH, "//div[@data-testid='primaryColumn']"))
        )
        print("✅ Sesión iniciada correctamente en Twitter/X.")
        return True

    except Exception as e:
        print(f"❌ Error en login con email/usuario/contraseña: {e}")
        return False

def navegar_twitter_un_poco(driver):
    try:
        driver.get("https://twitter.com/home")
        for _ in range(3):
            driver.execute_script("window.scrollBy(0, document.body.scrollHeight * 0.6);")
            time.sleep(1.1)
        print("👌 Navegación básica realizada.")
    except Exception as e:
        print(f"⚠️ Error navegando: {e}")

def main():
    options = uc.ChromeOptions()
    options.binary_location = CHROME_PATH
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-blink-features=AutomationControlled")
    # PERFIL PERSISTENTE (clave para no loguear cada vez)
    options.add_argument(f"--user-data-dir={PROFILE_DIR}")

    driver = uc.Chrome(
        driver_executable_path=CHROMEDRIVER_PATH,
        browser_executable_path=CHROME_PATH,
        options=options
    )

    try:
        if not is_twitter_logged_in(driver, timeout=5):
            ok = login_twitter_con_email_password(driver)
            if not ok:
                print("❌ No se pudo completar el login (¿challenge/2FA?).")
                return
        navegar_twitter_un_poco(driver)
    finally:
        time.sleep(2)
        driver.quit()

if __name__ == "__main__":
    main()
