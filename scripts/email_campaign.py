#!/usr/bin/env python3
"""
VersePro — Script d'envoi de campagne email pour les églises
Édité par Selah Studios (selahstudios.ai@gmail.com)

Usage :
  1. Prévisualiser les emails sans les envoyer (Mode Test / Simulation) :
     python scripts/email_campaign.py --dry-run

  2. Envoyer réellement la campagne avec vos identifiants Gmail :
     export GMAIL_APP_PASSWORD="votre_mot_de_passe_d_application"
     python scripts/email_campaign.py --send

Pour générer un mot de passe d'application Gmail :
  1. Rendez-vous sur https://myaccount.google.com/apppasswords
  2. Créez un mot de passe d'application pour 'VersePro Mailing'
  3. Utilisez ce mot de passe de 16 caractères.
"""

import argparse
import csv
import email.message
import os
import smtplib
import sys
import time
from pathlib import Path

# Configuration de l'expéditeur
SENDER_NAME = "Selah Studios"
SENDER_EMAIL = "selahstudios.ai@gmail.com"
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587

CSV_FILE = Path(__file__).resolve().parent / "contacts_eglises.csv"
LOG_FILE = Path(__file__).resolve().parent / "campagne_envoyes.log"


def create_email_content(church_name: str, city: str, contact_name: str) -> tuple[str, str, str]:
    """Génère l'objet, la version texte et la version HTML de l'email de premier contact."""
    greeting = f"Bonjour {contact_name}," if contact_name and contact_name.strip() else f"Bonjour à toute l'équipe de {church_name},"
    
    subject = f"Une innovation pour la projection biblique de {church_name}"

    body_text = f"""{greeting}

Nous vous contactons de la part de Selah Studios, un studio technologique chrétien dédié à la conception de logiciels, d'applications modernes et de solutions d'intelligence artificielle au service de l'Église et de l'Évangile.

Chaque dimanche, pendant que la parole de Dieu est proclamée, l'équipe en régie accomplit un travail précieux mais souvent stressant : chercher les versets cités à la hâte, suivre les sauts de lecture et taper les références sans faire d'erreur devant l'assemblée.

Pour libérer vos régisseurs et rendre la prédication encore plus fluide, nous avons développé VersePro.

Comment fonctionne VersePro ?
• 🎙️ Détection vocale instantanée : Dès que le pasteur cite un passage (« Lisons dans Jean 3 verset 16... »), le verset s'affiche automatiquement en moins d'une seconde.
• 🧠 Intelligence contextuelle : Si le prédicateur évoque une histoire biblique sans donner le chapitre (« le fils prodigue », « les murailles de Jéricho »), le système retrouve immédiatement le texte.
• ⏩ Navigation en 1 clic : 10 boutons de versets voisins permettent de suivre les sauts de lecture du prédicateur sans rien retaper au clavier.
• 📱 Suivi mobile pour l'assemblée : Les fidèles peuvent scanner un QR code pour lire en temps réel les versets sur smartphone dans la traduction de leur choix.
• 🔌 Compatible avec votre matériel existant : Fonctionne directement avec votre vidéoprojecteur, OBS, vMix ou ProPresenter.

💡 À propos de Selah Studios & VersePro :
Selah Studios développe des outils numériques pour équiper les ministères chrétiens avec un niveau d'excellence technique et ergonomique maximal. VersePro est un projet 100 % gratuit pour les églises locales, conçu pour fonctionner en toute autonomie et hors-ligne.

Si votre équipe média souhaite découvrir le logiciel et faire un premier essai sans engagement pour un prochain culte, faites-le nous savoir en répondant simplement à cet email : nous vous transmettrons l'accès complet et le kit de démarrage régisseur.

Que le Seigneur bénisse abondamment votre assemblée et votre ministère à {city}.

Fraternellement en Christ,

L'équipe Selah Studios
selahstudios.ai@gmail.com
"""

    body_html = f"""<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="utf-8">
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; line-height: 1.6; color: #2d3748; background-color: #f7fafc; margin: 0; padding: 20px; }}
        .container {{ max-width: 600px; margin: 0 auto; background: #ffffff; border-radius: 12px; padding: 32px; border: 1px solid #e2e8f0; box-shadow: 0 4px 6px rgba(0,0,0,0.02); }}
        .header {{ border-bottom: 2px solid #3182ce; padding-bottom: 15px; margin-bottom: 24px; display: flex; align-items: center; justify-content: space-between; }}
        .brand {{ font-size: 22px; font-weight: 800; color: #1a202c; letter-spacing: -0.5px; }}
        .brand span {{ color: #3182ce; }}
        .tagline {{ font-size: 11px; color: #718096; text-transform: uppercase; letter-spacing: 0.8px; font-weight: 600; }}
        h2 {{ font-size: 16px; color: #2b6cb0; margin-top: 24px; }}
        ul {{ padding-left: 20px; margin: 12px 0; }}
        li {{ margin-bottom: 8px; font-size: 14.5px; }}
        .about-box {{ background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 14px 18px; margin: 20px 0; font-size: 13.5px; color: #4a5568; line-height: 1.5; }}
        .highlight-box {{ background: #ebf8ff; border-left: 4px solid #3182ce; padding: 14px 18px; border-radius: 4px; margin: 20px 0; font-size: 14px; color: #2b6cb0; }}
        .footer {{ margin-top: 32px; padding-top: 18px; border-top: 1px solid #e2e8f0; font-size: 13px; color: #718096; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div>
                <div class="brand">Verse<span>Pro</span></div>
                <div class="tagline">Par Selah Studios · Technologies pour l'Église</div>
            </div>
        </div>
        
        <p>{greeting}</p>
        
        <p>Nous vous contactons de la part de <strong>Selah Studios</strong>, un studio technologique chrétien dédié au développement de logiciels, d'applications modernes et de solutions d'intelligence artificielle conçus pour équiper l'Église et soutenir la proclamation de l'Évangile.</p>
        
        <p>Chaque dimanche, pendant que la parole de Dieu est proclamée, l'équipe en régie accomplit un travail précieux mais souvent stressant : chercher les versets cités à la hâte, suivre les sauts de lecture et taper les références sans faire d'erreur devant l'assemblée.</p>
        
        <p>Pour libérer vos régisseurs et rendre la prédication encore plus fluide, nous avons développé <strong>VersePro</strong>.</p>
        
        <h2>Comment fonctionne VersePro ?</h2>
        <ul>
            <li><strong>🎙️ Détection vocale instantanée</strong> : Dès que le prédicateur cite un passage (<em>« Lisons dans Jean 3 verset 16... »</em>), le verset s'affiche automatiquement en moins d'une seconde.</li>
            <li><strong>🧠 Intelligence contextuelle</strong> : Si le pasteur évoque une histoire biblique sans donner le chapitre (<em>« le fils prodigue »</em>, <em>« les murailles de Jéricho »</em>), le système retrouve immédiatement le bon passage.</li>
            <li><strong>⏩ Navigation rapide (10 versets voisins)</strong> : Des boutons interactifs permettent de suivre les sauts de lecture du prédicateur en 1 clic, sans rien retaper.</li>
            <li><strong>📱 Suivi mobile pour l'assemblée</strong> : Les fidèles scannent un QR code pour lire en temps réel les versets sur smartphone dans la traduction de leur choix.</li>
            <li><strong>🔌 Compatible avec votre régie</strong> : Fonctionne avec votre vidéoprojecteur salle, OBS, vMix et ProPresenter.</li>
        </ul>
        
        <div class="about-box">
            <strong>🕊️ Notre Vision chez Selah Studios :</strong> Mettre le meilleur de la technologie moderne, du design et de l'ingénierie logicielle au service des ministères chrétiens. VersePro est <strong>100 % gratuit pour les églises</strong> et conçu pour fonctionner en toute autonomie et hors-ligne le dimanche.
        </div>
        
        <p>Si votre équipe média souhaite découvrir le logiciel et faire un premier essai sans engagement pour un prochain culte, <strong>répondez simplement à cet email</strong> : nous vous transmettrons avec plaisir l'accès complet et le kit de démarrage régisseur.</p>
        
        <p>Que le Seigneur bénisse abondamment votre assemblée et votre ministère à {city}.</p>
        
        <div class="footer">
            <p>Fraternellement en Christ,<br>
            <strong>L'équipe Selah Studios</strong><br>
            <a href="mailto:selahstudios.ai@gmail.com" style="color: #3182ce; font-weight: 600;">selahstudios.ai@gmail.com</a></p>
        </div>
    </div>
</body>
</html>
"""
    return subject, body_text, body_html


def load_sent_log() -> set[str]:
    """Charge la liste des emails déjà contactés pour éviter les doublons."""
    if not LOG_FILE.exists():
        return set()
    return set(LOG_FILE.read_text(encoding="utf-8").splitlines())


def record_sent_log(email_address: str):
    """Enregistre un email comme envoyé."""
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"{email_address}\n")


def run(dry_run: bool = True):
    if not CSV_FILE.exists():
        print(f"❌ Fichier contacts introuvable : {CSV_FILE}")
        sys.exit(1)

    sent_emails = load_sent_log()
    contacts = []

    with open(CSV_FILE, mode="r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            contacts.append(row)

    print(f"📋 {len(contacts)} contacts chargés depuis {CSV_FILE.name}")
    print(f"✉️ Mode : {'SIMULATION (Dry-Run)' if dry_run else 'ENVOI RÉEL'}")
    print("=" * 60)

    password = os.environ.get("GMAIL_APP_PASSWORD", "").strip()
    # Nettoyage automatique des espaces et espaces insécables (\xa0) copiés depuis Google
    password = password.replace(" ", "").replace("\xa0", "").replace("\t", "").strip()
    server = None

    if not dry_run:
        if not password:
            print("❌ Erreur : La variable d'environnement GMAIL_APP_PASSWORD est obligatoire pour l'envoi réel.")
            print("Définissez-la avec : export GMAIL_APP_PASSWORD='votre_mot_de_passe'")
            sys.exit(1)
        print("🔗 Connexion au serveur SMTP Gmail...")
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(SENDER_EMAIL, password)
        print("✅ Connecté et authentifié avec succès sur Gmail !")

    envoyes = 0
    ignores = 0

    try:
        for idx, contact in enumerate(contacts, 1):
            email_addr = (contact.get("email") or "").strip()
            church_name = (contact.get("nom_eglise") or "votre assemblée").strip()
            city = (contact.get("ville") or "votre ville").strip()
            contact_name = (contact.get("contact") or "").strip()

            if not email_addr or "@" not in email_addr:
                print(f"⚠️ [{idx}/{len(contacts)}] Ignoré : email invalide pour {church_name}")
                ignores += 1
                continue

            if email_addr.lower() in sent_emails and not dry_run:
                print(f"⏩ [{idx}/{len(contacts)}] Déjà envoyé à {email_addr} ({church_name})")
                ignores += 1
                continue

            subject, text_content, html_content = create_email_content(church_name, city, contact_name)

            if dry_run:
                print(f"\n🔍 [SIMULATION {idx}/{len(contacts)}] Pour : {email_addr} ({church_name} - {city})")
                print(f"   Objet : {subject}")
                print(f"   Salutation : Bonjour {contact_name or church_name}")
            else:
                msg = email.message.EmailMessage()
                msg["Subject"] = subject
                msg["From"] = f"{SENDER_NAME} <{SENDER_EMAIL}>"
                msg["To"] = email_addr
                msg.set_content(text_content)
                msg.add_alternative(html_content, subtype="html")

                server.send_message(msg)
                record_sent_log(email_addr.lower())
                print(f"✅ [{idx}/{len(contacts)}] Email envoyé avec succès à : {email_addr} ({church_name})")
                envoyes += 1
                # Temporisation anti-spam (2 secondes entre chaque envoi)
                time.sleep(2.0)

    finally:
        if server:
            server.quit()
            print("🔒 Déconnexion SMTP effectuée.")

    print("=" * 60)
    if dry_run:
        print(f"🎉 Simulation terminée : {len(contacts)} contacts vérifiés. Prêt pour l'envoi réel !")
    else:
        print(f"🎉 Campagne terminée : {envoyes} emails envoyés, {ignores} ignorés/déjà envoyés.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Campagne d'emails VersePro pour les églises")
    parser.add_argument("--send", action="store_true", help="Active l'envoi réel des emails")
    parser.add_argument("--dry-run", action="store_true", default=True, help="Mode simulation sans envoi (par défaut)")
    args = parser.parse_args()

    is_send = args.send
    run(dry_run=not is_send)
