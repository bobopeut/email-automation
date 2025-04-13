import imaplib
import email
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import base64
import time
import cv2
import pytesseract
import numpy as np
import os

# Configuration Tesseract
pytesseract.pytesseract.tesseract_cmd = os.getenv('TESSERACT_CMD', '/usr/bin/tesseract')

# Compte email à visiter
EMAIL = "contact@technovr-leonard.fr"
DEFAULT_PASSWORD = "Leonard2025"
IMAP_SERVER = "ssl0.ovh.net"

def log_console(message):
    """Affiche des logs dans la console avec un timestamp."""
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {message}")

def resoudre_captcha(driver):
    try:
        log_console("🔍 Tentative de résolution du CAPTCHA...")
        img_element = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "div.captcha-container img"))
        )
        img_src = img_element.get_attribute("ng-src")

        # Détection de la couleur cible
        color_element = driver.find_element(By.CSS_SELECTOR, "a.submit-btn")
        color = color_element.get_attribute("style")
        rgb = color.split('(')[1].split(')')[0].split(',')
        target_color = (int(rgb[2]), int(rgb[1]), int(rgb[0]))

        img_data = img_src.split(',')[1]
        with open("captcha.png", "wb") as f:
            f.write(base64.b64decode(img_data))

        # Traitement de l'image pour trouver le texte
        image = cv2.imread('captcha.png')
        lower = np.array([max(0, c - 30) for c in target_color])
        upper = np.array([min(255, c + 30) for c in target_color])
        mask = cv2.inRange(image, lower, upper)
        result = cv2.bitwise_and(image, image, mask=mask)
        gray = cv2.cvtColor(result, cv2.COLOR_BGR2GRAY)
        _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

        text = pytesseract.image_to_string(thresh).strip()
        log_console(f"🔤 Texte extrait du CAPTCHA : {text}")

        # Saisie du texte et soumission
        input_field = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.ID, "capcha-input"))
        )
        input_field.clear()
        input_field.send_keys(text)
        log_console(f"🔍 Texte saisi dans le champ CAPTCHA : {text}")

        submit_button = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.ID, "capcha-submit"))
        )
        submit_button.click()
        log_console("🔍 CAPTCHA soumis.")

        # Vérification de la validation
        if verifier_validation(driver):
            log_console("✅ Validation réussie après résolution du CAPTCHA.")
            return True
        else:
            log_console("❌ Validation échouée après résolution du CAPTCHA.")
            return False
    except Exception as e:
        log_console(f"❌ Erreur lors de la résolution du CAPTCHA : {str(e)}")
        return False

def verifier_validation(driver):
    try:
        confirmation_msg = WebDriverWait(driver, 7).until(
            EC.presence_of_element_located((By.CLASS_NAME, "msg-confirmation"))
        )
        if "Vous êtes dorénavant dans ma liste de contacts confirmés" in confirmation_msg.text:
            log_console("✅ Validation réussie !")
            return True
        else:
            log_console("❌ Validation échouée.")
            return False
    except Exception:
        log_console("❌ Message de validation non trouvé.")
        return False

def traiter_email(imap, driver, email_id, email_message):
    try:
        log_console("🔍 Analyse de l'email pour extraction des liens...")
        liens = []
        if email_message.is_multipart():
            for part in email_message.walk():
                if part.get_content_type() == "text/html":
                    html_content = part.get_payload(decode=True).decode('utf-8', errors='ignore')
                    soup = BeautifulSoup(html_content, 'html.parser')
                    for lien in soup.find_all('a', href=True):
                        if "délivrer mon email" in lien.get_text().lower():
                            liens.append(lien['href'])
                            log_console(f"🔗 Lien trouvé : {lien['href']}")

        if not liens:
            log_console("❌ Aucun lien de délivrance trouvé.")
            return False

        for lien in liens:
            log_console(f"🌐 Ouverture du lien : {lien}")
            driver.get(lien)
            time.sleep(3)
            if verifier_validation(driver):
                return True
            for tentative in range(3):
                if resoudre_captcha(driver):
                    if verifier_validation(driver):
                        return True
            time.sleep(2)

        log_console("❌ Aucune validation réussie après plusieurs tentatives.")
        return False

    except Exception as e:
        log_console(f"❌ Erreur lors du traitement de l'email : {str(e)}")
        return False

def traiter_compte_email(email_adresse, driver):
    """Traite un seul compte email."""
    try:
        log_console(f"🔄 Connexion au compte : {email_adresse}")

        # Connexion au serveur IMAP
        imap = imaplib.IMAP4_SSL(IMAP_SERVER)
        imap.login(email_adresse, DEFAULT_PASSWORD)
        log_console(f"✅ Connexion réussie pour {email_adresse}")

        # Vérification des dossiers disponibles
        status, folders = imap.list()
        if status != "OK":
            log_console(f"❌ Impossible de récupérer les dossiers pour {email_adresse}")
            return

        log_console("📂 Dossiers disponibles :")
        for folder in folders:
            log_console(folder.decode())

        # Sélection de la boîte MailInBlack
        status, _ = imap.select('"INBOX.MailInBlack"')
        if status != "OK":
            log_console(f"❌ Échec de la sélection du dossier 'INBOX.MailInBlack' pour {email_adresse}")
            return

        # Rechercher les emails
        _, messages = imap.search(None, 'ALL')
        email_ids = messages[0].split()
        log_console(f"📨 {len(email_ids)} email(s) à traiter pour {email_adresse}")

        for email_id in email_ids:
            try:
                _, msg = imap.fetch(email_id, '(RFC822)')
                raw_email = msg[0][1]
                email_message = email.message_from_bytes(raw_email)

                if traiter_email(imap, driver, email_id, email_message):
                    # Supprimer l'email si validation réussie
                    imap.store(email_id, '+FLAGS', '\\Deleted')
                    imap.expunge()
                    log_console("🗑️ Email traité et supprimé.")
                else:
                    # Déplacer l'email en cas d'échec
                    log_console("❌ Déplacement de l'email dans 'Echecs_Mailinblack'.")
                    imap.copy(email_id, '"INBOX.Echecs_Mailinblack"')
                    imap.store(email_id, '+FLAGS', '\\Deleted')
                    imap.expunge()
            except Exception as e:
                log_console(f"❌ Erreur lors du traitement de l'email {email_id} : {str(e)}")

        log_console(f"✅ Tous les emails ont été traités pour {email_adresse}.")
        imap.logout()

    except Exception as e:
        log_console(f"❌ Erreur lors du traitement du compte {email_adresse} : {str(e)}")
    finally:
        try:
            imap.logout()
        except:
            pass

def main():
    try:
        log_console("🔄 Démarrage du script...")

        # Configuration du navigateur
        options = webdriver.ChromeOptions()
        options.add_argument('--headless')  # Exécuter en mode headless pour GitHub Actions
        options.add_argument('--disable-gpu')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        from selenium.webdriver.chrome.service import Service
        service = Service("/usr/bin/chromedriver")  # Assurez-vous que chromedriver est installé
        driver = webdriver.Chrome(service=service, options=options)
        log_console("✅ Navigateur Chrome lancé.")

        # Traiter le compte email
        traiter_compte_email(EMAIL, driver)

        log_console("✅ Compte email traité.")
    except Exception as e:
        log_console(f"❌ Erreur principale : {str(e)}")
    finally:
        try:
            driver.quit()
        except:
            pass

if __name__ == "__main__":
    main()
