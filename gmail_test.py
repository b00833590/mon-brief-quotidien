from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from google.genai import types
from bs4 import BeautifulSoup
import json
from datetime import datetime
from playwright.sync_api import sync_playwright
import base64
import requests
import socket
import os
import sys
from dotenv import load_dotenv
socket.setdefaulttimeout(30)

# La console Windows par defaut (cp1252) plante sur un print() contenant un
# emoji (sujet d'email, etc.) : on force stdout/stderr en UTF-8 avec remplacement
# plutot que de laisser une UnicodeEncodeError interrompre tout le pipeline.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

load_dotenv()
GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/drive.readonly"
]

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

TOKEN_FICHIER = "token.json"

creds = None
if os.path.exists(TOKEN_FICHIER):
    creds = Credentials.from_authorized_user_file(TOKEN_FICHIER, SCOPES)

if not creds or not creds.valid:
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    elif os.environ.get("GITHUB_ACTIONS") == "true":
        # Pas de navigateur disponible en CI : on echoue vite et fort plutot que de
        # rester bloque sur un flow interactif impossible a completer.
        # Recuperation : relancer le flow interactif en local pour regenerer token.json,
        # puis mettre a jour le secret GMAIL_TOKEN_JSON (voir RUNBOOK.md).
        raise SystemExit(
            "Token Gmail OAuth invalide/absent et authentification interactive impossible en CI. "
            "Voir RUNBOOK.md pour la procedure de re-autorisation."
        )
    else:
        flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
        creds = flow.run_local_server(port=0, prompt="select_account")
    with open(TOKEN_FICHIER, "w") as f:
        f.write(creds.to_json())

service = build("gmail", "v1", credentials=creds)

# Construit la date du jour au format attendu par Gmail (YYYY/MM/DD)
aujourdhui_gmail = datetime.now().strftime("%Y/%m/%d")

query = (
    f'(from:team@aktionnaire.com OR from:arcos@mail.arcos.news OR from:FT@newsletters.ft.com '
    f'OR from:bourseko@mail.beehiiv.com OR from:@semafor.com OR from:markets@axios.com '
    f'OR from:fortune@mail.fortune.com OR from:hello@finimize.com OR from:squad@thedailyupside.com '
    f'OR from:Alan.Murray@dowjones.com '
    f'OR (from:noreply@news.bloomberg.com subject:"Money Stuff") '
    f'OR (from:access@interactive.wsj.com (subject:"Markets P.M." OR subject:"Markets A.M." OR subject:"What\'s News"))) '
    f'after:{aujourdhui_gmail} '
    f'-subject:(Welcome OR Confirm OR "Action Required" OR subscribed OR "Set a password")'
)
messages = []
try:
    results = service.users().messages().list(userId="me", q=query, maxResults=25).execute()
    messages = results.get("messages", [])
except Exception as e:
    print(f"Erreur recuperation des newsletters Gmail : {e}")


def extract_body(payload):
    plain_text = None
    html_text = None

    def search_parts(part):
        nonlocal plain_text, html_text
        if part["mimeType"] == "text/plain":
            data = part["body"].get("data")
            if data:
                plain_text = base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore")
        elif part["mimeType"] == "text/html":
            data = part["body"].get("data")
            if data:
                html_text = base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore")
        if "parts" in part:
            for sub_part in part["parts"]:
                search_parts(sub_part)

    search_parts(payload)

    if plain_text:
        return plain_text
    if html_text:
        soup = BeautifulSoup(html_text, "html.parser")
        return soup.get_text(separator=" ", strip=True)
    return "Contenu non trouve"


emails_data = []

for msg in messages:
    try:
        full_msg = service.users().messages().get(userId="me", id=msg["id"]).execute()
        headers = full_msg["payload"]["headers"]
        subject = next((h["value"] for h in headers if h["name"] == "Subject"), "Pas de sujet")
        sender = next((h["value"] for h in headers if h["name"] == "From"), "Inconnu")
        body = extract_body(full_msg["payload"])

        emails_data.append({"sender": sender, "subject": subject, "body": body})
    except Exception as e:
        print(f"Erreur lecture d'un email Gmail (id={msg.get('id')}) : {e}")

    print("---")
    print(f"De : {sender}")
    print(f"Sujet : {subject}")
    print(f"Apercu du contenu : {body[:200]}")

# --- Sources RSS (Bloomberg, The Economist) ---
import feedparser

FLUX_RSS = {
    "Bloomberg Markets": "https://feeds.bloomberg.com/business/news.rss",
    "The Economist": "https://www.economist.com/finance-and-economics/rss.xml",
}

NB_ARTICLES_RSS_MAX = 5


def get_articles_rss():
    """Recupere les derniers articles des flux RSS configures et les
    formate comme des 'emails' pour rester compatible avec le pipeline existant."""
    articles_rss = []
    for nom_source, url_flux in FLUX_RSS.items():
        try:
            flux = feedparser.parse(url_flux)
            if flux.bozo:
                print(f"Attention : flux RSS {nom_source} mal forme ou inaccessible.")
            entrees = flux.entries[:NB_ARTICLES_RSS_MAX]
            for entree in entrees:
                titre = entree.get("title", "Sans titre")
                resume = entree.get("summary", entree.get("description", ""))
                articles_rss.append({
                    "sender": nom_source,
                    "subject": titre,
                    "body": resume
                })
            print(f"{nom_source} : {len(entrees)} articles RSS recuperes")
        except Exception as e:
            print(f"Erreur recuperation RSS {nom_source} : {e}")
    return articles_rss


emails_data.extend(get_articles_rss())

from google import genai

import io
import fitz  # PyMuPDF

# --- Fonction Natixis (Morning Line Express, Fixed Income) ---

def get_dernier_article_natixis():
    # --- Étape 1 : trouver le dernier article (cette partie marche déjà, on la garde en requests classique) ---
    search_url = "https://www.research.natixis.com/Site/api/Publications"

    payload = {
        "universe": "FixedIncome",
        "authorId": None,
        "culture": "French",
        "isPublic": True,
        "pagination": {
            "orderBy": "ByDateHighest",
            "pageNumber": 1,
            "pageSize": 5
        },
        "publicationTypeName": "MORNING_LINE"
    }

    headers = {
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
    }

    try:
        response = requests.post(search_url, json=payload, headers=headers)
        response.raise_for_status()
        articles = response.json()["items"]
    except Exception as e:
        print(f"Erreur recherche du dernier article Natixis : {e}")
        return None

    if not articles:
        print("Aucun article Natixis trouve.")
        return None

    dernier_article = articles[0]

    titre = dernier_article["title"]
    date_publication = dernier_article["publishedAt"][:10]
    token_id = dernier_article["tokenId"]

    aujourdhui = datetime.now().strftime("%Y-%m-%d")
    if date_publication != aujourdhui:
        print(f"Pas d'article Natixis du {aujourdhui}, on prend celui du {date_publication} a la place.")

    print(f"Article Natixis retenu : '{titre}' ({date_publication})")

    # --- Étape 2 : Playwright visite la page et intercepte le PDF ---
    import urllib.parse
    page_url = f"https://www.research.natixis.com/Site/fr/fixedincome/latest-publications/publication/{urllib.parse.quote(token_id, safe='')}"

    pdf_bytes = None

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()

            # Attente deterministe de la reponse /api/File/ plutot qu'un sleep fixe :
            # sur un site lent (ou un run CI sur une IP moins bien traitee), un delai fixe
            # peut fermer le navigateur avant que la reponse reseau soit reellement arrivee.
            try:
                with page.expect_response(
                    lambda r: "/api/File/" in r.url, timeout=15000
                ) as info_reponse:
                    page.goto(page_url, wait_until="domcontentloaded", timeout=45000)
                reponse_pdf = info_reponse.value
                pdf_bytes = reponse_pdf.body()
                print(f"PDF Natixis intercepte via Playwright ({len(pdf_bytes)} octets)")
            except Exception as e:
                print(f"Erreur interception PDF (reponse /api/File/ non recue a temps) : {e}")

            browser.close()
    except Exception as e:
        print(f"Erreur Playwright lors de la recuperation Natixis (site lent ou indisponible) : {e}")
        return None

    if pdf_bytes is None:
        print("Impossible de recuperer le PDF Natixis via Playwright.")
        return None

    print(f"Premiers octets recus : {pdf_bytes[:20]}")

    import json as json_module
    import base64

    base64_str = json_module.loads(pdf_bytes.decode("utf-8"))
    pdf_bytes_decodes = base64.b64decode(base64_str)

    pdf_document = fitz.open(stream=pdf_bytes_decodes, filetype="pdf")

    texte_complet = ""
    for page_pdf in pdf_document:
        texte_complet += page_pdf.get_text()

    pdf_document.close()

    texte_complet = texte_complet.strip()

    # --- Nettoyage : on retire le disclaimer légal en début de document ---
    marqueur = "MARKET LINES"
    position = texte_complet.upper().find(marqueur)

    if position != -1:
        texte_nettoye = texte_complet[position:]
    else:
        # Si le marqueur n'est pas trouvé (mise en page différente un jour), on garde tout par sécurité
        texte_nettoye = texte_complet
        print("Attention : marqueur 'MARKET LINES' non trouve, texte Natixis garde en entier.")

    return {
        "titre": titre,
        "date": date_publication,
        "texte": texte_nettoye
    }

# --- Recherche du PDF Les Echos (lien Google Drive envoyé par email) ---
import re
from googleapiclient.http import MediaIoBaseDownload

drive_service = build("drive", "v3", credentials=creds)

query_echos = f"from:me subject:Echos after:{aujourdhui_gmail}"
messages_echos = []
try:
    results_echos = service.users().messages().list(userId="me", q=query_echos, maxResults=3).execute()
    messages_echos = results_echos.get("messages", [])
except Exception as e:
    print(f"Erreur recherche email Les Echos : {e}")

texte_echos = ""

print(f"Nombre d'emails Les Echos trouves : {len(messages_echos)}")

for msg in messages_echos:
    full_msg = service.users().messages().get(userId="me", id=msg["id"]).execute()
    corps_mail = extract_body(full_msg["payload"])

    match = re.search(r"drive\.google\.com/file/d/([a-zA-Z0-9_-]+)", corps_mail)

    if match:
        file_id = match.group(1)
        print(f"Lien Drive trouve, file_id : {file_id}")
        try:
            request = drive_service.files().get_media(fileId=file_id)
            fh = io.BytesIO()
            downloader = MediaIoBaseDownload(fh, request)
            done = False
            while not done:
                status, done = downloader.next_chunk()
                if status:
                    print(f"Telechargement Drive : {int(status.progress() * 100)}%")

            fh.seek(0)
            pdf_document = fitz.open(stream=fh.read(), filetype="pdf")

            # On ne prend que les premières pages (limite raisonnable pour Gemini + rapidité)
            NB_PAGES_MAX = 6
            images_pages = []
            for num_page in range(min(NB_PAGES_MAX, len(pdf_document))):
                page = pdf_document[num_page]
                pixmap = page.get_pixmap(dpi=150)
                images_pages.append(pixmap.tobytes("png"))

            pdf_document.close()
            print(f"PDF Les Echos converti en {len(images_pages)} images depuis Drive")

            # --- Demande à Gemini de lire directement les images ---
            client_vision = genai.Client(api_key=GEMINI_API_KEY)

            contenu_gemini = ["Voici des pages scannées du journal Les Echos. Extrais les points d'actualite economique et financiere les plus importants, sous forme de liste a puces courtes et factuelles, en francais."]
            for img_bytes in images_pages:
                contenu_gemini.append(types.Part.from_bytes(data=img_bytes, mime_type="image/png"))

            reponse_vision = client_vision.models.generate_content(
                model="gemini-2.5-flash",
                contents=contenu_gemini
            )
            texte_echos = reponse_vision.text.strip()

        except Exception as e:
            print(f"Erreur extraction PDF Les Echos depuis Drive : {e}")

if texte_echos:
    emails_data.append({
        "sender": "Les Echos",
        "subject": "Les Echos - Edition du jour",
        "body": texte_echos
    })
    print(f"Apercu Les Echos : {texte_echos[:200]}")
else:
    print("Aucun PDF Les Echos trouve aujourd'hui.")

# --- Natixis (Morning Line Express) ---
natixis = get_dernier_article_natixis()
if natixis:
    emails_data.append({
        "sender": "Natixis",
        "subject": f"Natixis - {natixis['titre']}",
        "body": natixis["texte"]
    })
    print(f"Apercu Natixis : {natixis['texte'][:200]}")

client = genai.Client(api_key=GEMINI_API_KEY)

# On assemble tous les mails en un seul texte pour le prompt
texte_complet = ""
for email in emails_data:
    texte_complet += f"\n\n--- Email de {email['sender']} ---\nSujet: {email['subject']}\n{email['body'][:3000]}"

prompt = f"""Tu es un assistant qui structure un briefing financier quotidien pour un professionnel de la finance.

REGLE ABSOLUE : TOUT le contenu genere (titres ET details, dans TOUTES les sections) doit etre
integralement en FRANCAIS, meme si les sources originales sont en anglais (FT, Semafor, etc.).
Traduis systematiquement, ne recopie jamais une phrase ou un titre en anglais tel quel.
Exception : les noms propres (entreprises, personnes, produits) restent inchanges, et les termes
financiers couramment utilises tels quels en francais (ex: "hedge fund", "private equity", "spread")
peuvent etre conserves si c'est l'usage standard.

IMPORTANT : les doubles asterisques (mise en valeur) ne s'appliquent JAMAIS au "titre", uniquement
au "detail". Le titre doit toujours etre du texte brut, sans aucun asterisque.

Dans chaque "detail" (sauf pour l'Agenda), mets en valeur avec des doubles asterisques a la fois :
1. Les chiffres-cles importants (pourcentages, montants, niveaux d'indices, dates precises)
2. Les bouts de phrase ou groupes de mots qui portent l'information essentielle pour comprendre
   l'actualite en un coup d'oeil (le fait principal, la cause, la consequence, la decision prise,
   le nom de l'acteur central de la nouvelle) — pas juste les nombres.

Par exemple : "**La Fed a maintenu ses taux inchanges** malgre des pressions inflationnistes, mais
Powell a signale **une possible baisse en septembre** face au ralentissement du marche de l'emploi,
qui a chute de **12%**."

Regles :
- Au total 3 a 6 mises en valeur maximum par actualite (chiffres + bouts de phrase confondus),
  pour ne pas surcharger le texte.
- Les bouts de phrase surlignes doivent rester courts (3 a 8 mots), jamais une phrase entiere.
- Ne surligne jamais un mot isole sans contexte (ex: pas juste "**Fed**", mais "**la Fed a maintenu
  ses taux**").
- Priorise ce qui permet de comprendre l'essentiel de l'actualite en lisant uniquement les parties
  surlignees, sans avoir a lire le detail complet.

IMPORTANT : ce briefing est exclusivement centre sur l'actualite financiere et economique
(marches, entreprises, banques centrales, macroeconomie, tech/IA sous l'angle business).
Si une source contient du contenu hors de ce champ (politique pure, societe, culture, sport...),
ignore-le completement, meme s'il semble interessant. Ne l'inclus dans aucune section.

Voici plusieurs emails/sources recus aujourd'hui (newsletters financieres et articles de recherche).
Ta mission : lire TOUT le contenu, puis le reorganiser par THEME, pas par source d'origine.
Ne mentionne jamais la newsletter d'origine dans les points (pas de "selon Arcos" ou "d'apres le FT").

REGLE IMPORTANTE : si plusieurs emails proviennent de la meme newsletter (meme expediteur/marque),
fusionne leurs informations naturellement dans les themes appropries, sans jamais creer de doublon
d'un meme sujet.

Pour CHAQUE actualite (dans toutes les sections), le format DOIT etre exactement :
"REGION :: CATEGORIE :: Titre court (6-10 mots) :: Detail factuel en 2-3 phrases maximum."

ou REGION est un des codes suivants (en minuscules) :
usa, europe, asie, afrique, global (utilise "global" si l'info concerne plusieurs regions ou le monde entier, pas une zone precise)

et CATEGORIE est un des codes suivants (en minuscules) :
geo (geopolitique), corp (corporate/entreprises), mkt-n (marches), macro (macroeconomie),
tech (technologie), ai (intelligence artificielle)

Les 4 parties sont separees par " :: " (deux points doubles entoures d'un espace avant ET apres,
jamais colles au texte). Respecte cet espacement de maniere identique et systematique sur
CHAQUE point, sans aucune exception, meme dans les points les plus longs.
Exemple : "usa :: macro :: Fed maintient ses taux inchanges :: Powell signale une possible baisse en septembre face au ralentissement de l'emploi. Les marches ont accueilli cette decision avec prudence."

REGLE CRITIQUE DE FORMAT JSON : n'utilise JAMAIS de guillemets droits (") a l'interieur des titres
ou des details, meme pour citer un mot ou une expression. Si tu as besoin de mettre un terme en
evidence ou de le citer, utilise des guillemets francais « comme ceci » a la place. Ne mets aucun
caractere " autre que ceux qui delimitent le JSON lui-meme.

Les sections (dans cet ordre) sont :
1. "Flash" : les 4 a 6 actualites les PLUS importantes, critiques ou sensibles de la journee, tous themes et regions confondus. Classe-les de la plus importante a la moins importante. Pour Flash specifiquement, le detail doit etre une SYNTHESE plus riche que les autres sections (3 a 5 phrases completes, dans tes propres mots), avec un maximum de chiffres precis (pourcentages, montants, niveaux d'indices, dates) et le contexte/les implications essentielles. Reste concis et informatif : ce n'est pas un article complet, juste un resume plus etoffe qu'une simple phrase.
2. "Marches" : mouvements des indices, taux, matieres premieres, tendances generales de marche, toutes regions.
3. "Macro" : politique monetaire, banques centrales, inflation, emploi, indicateurs macroeconomiques, toutes regions.
4. "Corporate" : resultats d'entreprises, fusions-acquisitions, IPO, actualites d'entreprises specifiques, toutes regions.
5. "Tech & IA" : actualites liees a la technologie, l'intelligence artificielle, les semi-conducteurs, toutes regions.
6. "Briefing complet" : synthese EXHAUSTIVE de TOUTES les informations du jour, sans limite de points. Pour cette section specifiquement, chaque detail doit etre TRES RICHE et DEVELOPPE : 4 a 6 phrases completes par actualite, avec tous les chiffres disponibles (montants, pourcentages, comparaisons historiques, contexte), les acteurs impliques, et les consequences ou implications potentielles. Cette section doit pouvoir se lire comme un vrai article de synthese, pas comme un resume.
7. "Agenda" : TOUS les evenements a venir mentionnes ou sous-entendus dans les sources, meme brievement : reunions de banques centrales (Fed, BCE, etc.), publications de resultats d'entreprises, sommets internationaux, elections, dates limites reglementaires, decisions politiques attendues. Cherche activement ces mentions. Pour l'Agenda UNIQUEMENT, le format est different des autres sections :
"DATE :: region :: cat :: Titre court de l'evenement (pas de phrase, juste le nom, 3-8 mots)"
ou DATE est au format "JJ/MM" (ex: "15/07") si une date precise est connue, ou un texte court
comme "Cette semaine", "Fin juillet", "Semaine du 14/07" si seule une periode approximative est connue.
Classe les evenements par ordre chronologique (le plus proche en premier).
Ne mets "Aucun evenement identifie" QUE si tu as vraiment cherche et rien trouve.

En plus des sections, fournis egalement un sentiment de marche global, sous la forme d'un objet separe.
Le sentiment doit etre TRES CONCIS : un label ("Haussier", "Baissier" ou "Neutre") et une raison
courte de MAXIMUM 2 phrases (pas plus).

Reponds UNIQUEMENT avec un JSON valide (rien d'autre, pas de ```json), structure exactement comme ceci :
{{
  "sentiment": {{"label": "Haussier", "raison": "Phrase courte 1. Phrase courte 2."}},
  "sections": [
    {{"source": "Flash", "points": ["region :: cat :: titre :: detail"]}},
    {{"source": "Marches", "points": ["region :: cat :: titre :: detail"]}},
    {{"source": "Macro", "points": ["region :: cat :: titre :: detail"]}},
    {{"source": "Corporate", "points": ["region :: cat :: titre :: detail"]}},
    {{"source": "Tech & IA", "points": ["region :: cat :: titre :: detail"]}},
    {{"source": "Briefing complet", "points": ["region :: cat :: titre :: detail"]}},
    {{"source": "Agenda", "points": ["date :: region :: cat :: titre court"]}},
  ]
}}

IMPORTANT : produis TOUJOURS les 7 sections dans cet ordre exact, meme si une section est vide.

Voici les sources a traiter :

{texte_complet}
"""
from google.genai import types as genai_types


def get_agenda_enrichi(texte_complet, client):
    """Genere l'agenda financier en utilisant la recherche web (Google Search grounding)
    en plus des sources emails, pour ne pas rater d'evenements a venir."""

    prompt_agenda = f"""Tu es un assistant qui construit un calendrier des evenements financiers
essentiels a venir (les 2-3 prochaines semaines), pour un professionnel de la finance.

Utilise a la fois :
1. Les sources emails ci-dessous (elles peuvent mentionner des evenements)
2. Une recherche web pour completer et verifier les dates exactes des evenements financiers
   majeurs a venir : reunions de banques centrales (Fed/FOMC, BCE, BoE, BoJ), publications
   de resultats d'entreprises importantes, indicateurs macro cles (emploi US, inflation, PIB),
   sommets economiques internationaux, elections avec impact marche.

Pour CHAQUE evenement, le format DOIT etre exactement :
"DATE :: region :: cat :: Titre court de l'evenement (pas de phrase, juste le nom, 3-8 mots)"

ou DATE est au format "JJ/MM" (ex: "15/07") si une date precise est connue, ou un texte court
comme "Cette semaine", "Fin juillet", "Semaine du 14/07" si seule une periode approximative est connue.
region est: usa, europe, asie, afrique, global
cat est: geo, corp, mkt-n, macro, tech, ai

Classe les evenements par ordre chronologique (le plus proche en premier).
Reponds UNIQUEMENT avec un JSON valide (rien d'autre), structure ainsi :
{{"points": ["date :: region :: cat :: titre", ...]}}

Sources emails du jour (pour contexte) :
{texte_complet[:3000]}
"""

    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt_agenda,
            config=genai_types.GenerateContentConfig(
                tools=[genai_types.Tool(google_search=genai_types.GoogleSearch())]
            )
        )
        texte = response.text.strip()
        texte = texte.replace("```json", "").replace("```", "").strip()
        agenda_data = json.loads(texte)
        print(f"Agenda enrichi : {len(agenda_data.get('points', []))} evenements trouves")
        return agenda_data.get("points", [])
    except Exception as e:
        print(f"Erreur generation agenda enrichi : {e}")
        return None

AGENDA_FICHIER = "agenda_events.json"


def charger_agenda_stocke():
    """Charge les evenements d'agenda deja connus depuis le disque."""
    if os.path.exists(AGENDA_FICHIER):
        try:
            with open(AGENDA_FICHIER, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []


def sauvegarder_agenda_stocke(evenements):
    with open(AGENDA_FICHIER, "w", encoding="utf-8") as f:
        json.dump(evenements, f, ensure_ascii=False, indent=2)


def parser_date_evenement(date_txt):
    """Tente de parser une date au format JJ/MM. Retourne None si le format
    n'est pas reconnu (date approximative en texte libre, ex: 'Fin juillet')."""
    import re
    match = re.match(r"^(\d{1,2})/(\d{1,2})$", date_txt.strip())
    if not match:
        return None
    jour, mois = int(match.group(1)), int(match.group(2))
    aujourdhui = datetime.now().date()
    try:
        date_evt = datetime(aujourdhui.year, mois, jour).date()
        if (aujourdhui - date_evt).days > 60:
            date_evt = datetime(aujourdhui.year + 1, mois, jour).date()
        return date_evt
    except ValueError:
        return None


MOTS_VIDES_AGENDA = {
    "de", "du", "des", "et", "la", "le", "les", "l", "un", "une", "au", "aux",
    "en", "pour", "sur", "a", "d", "the", "of", "and", "jour", "j",
    # Bruit generique de communiques financiers (FR/EN), non discriminant :
    # une fois retire, ce qui reste (nom d'entreprise, code pays, indicateur)
    # est ce qui identifie vraiment l'evenement.
    "resultats", "resultat", "trimestriels", "trimestriel", "semestriels",
    "semestriel", "rapport", "publication", "earnings", "report",
    "corporation", "corp", "inc", "sa", "se", "plc", "ltd", "nv", "ag",
    "group", "groupe", "conference", "presse", "preliminaire", "flash",
    "hebdomadaire", "hebdomadaires", "nouvelles", "demandes", "national",
    "nationale", "international", "internationale", "indice", "taux",
    "q1", "q2", "q3", "q4", "t1", "t2", "t3", "t4", "s1", "s2",
}

# Quelques concepts recurrents que Gemini traduit/abrege differemment d'une
# execution a l'autre (FR/EN, sigle/mot entier) : uniformises en un token
# commun avant comparaison, sinon la similarite de mots-cles ne les rapproche
# jamais (ex. "CPI" vs "Indice des Prix a la Consommation").
SYNONYMES_PHRASES_AGENDA = [
    (r"\broyaume\s*uni\b", "uk"),
    (r"\br\s*u\b", "uk"),
    (r"\bipc\b", "cpi"),
    (r"\binflation\b", "cpi"),
    (r"\bprix\s+a\s+la\s+consommation\b", "cpi"),
]


def _mots_cles_agenda(titre):
    """Normalise un titre d'evenement d'agenda en un ensemble de mots-cles
    comparables (minuscules, sans accents/ponctuation, sans mots vides, avec
    quelques synonymes uniformises)."""
    import re
    import unicodedata
    # Le ticker entre parentheses ("Alphabet (GOOG)" vs "Alphabet (GOOGL)")
    # varie d'une reformulation a l'autre sans changer l'evenement : ignore.
    titre = re.sub(r"\([^)]*\)", " ", titre)
    texte = unicodedata.normalize("NFKD", titre.lower())
    texte = "".join(c for c in texte if not unicodedata.combining(c))
    texte = re.sub(r"[^a-z0-9\s]", " ", texte)
    texte = re.sub(r"\s+", " ", texte).strip()
    for motif, remplacement in SYNONYMES_PHRASES_AGENDA:
        texte = re.sub(motif, remplacement, texte)
    return {m for m in texte.split() if m and m not in MOTS_VIDES_AGENDA}


def _sont_doublons_agenda(titre_a, titre_b, seuil=0.45):
    """Similarite de Jaccard sur les mots-cles significatifs : deux titres
    reformules pour le meme evenement (ex. 'Decision taux BCE' vs 'BCE
    decision de taux d'interet') partagent l'essentiel de leurs mots-cles,
    meme si Gemini regenere le texte differemment a chaque execution."""
    mots_a, mots_b = _mots_cles_agenda(titre_a), _mots_cles_agenda(titre_b)
    if not mots_a or not mots_b:
        return False
    intersection = mots_a & mots_b
    union = mots_a | mots_b
    return (len(intersection) / len(union)) >= seuil


def _dedupliquer_agenda_par_date(entrees, seuil=0.45):
    """Regroupe par date exacte les entrees dont le titre a ete reformule
    d'une execution a l'autre pour le meme evenement (l'egalite stricte de
    _points_existants_ ne le detecte pas), et ne garde qu'un representant par
    groupe : le plus ancien, en preferant un titre non corrompu (sans
    caractere de remplacement d'encodage) si le groupe en contient un.
    Le regroupement reste limite a une meme date exacte pour ne jamais fondre
    deux etapes reellement distinctes d'un meme evenement multi-jours
    (ex. 'Debut reunion FOMC' et 'Decision taux FOMC' le lendemain)."""
    from collections import defaultdict
    par_date = defaultdict(list)
    for entree in entrees:
        morceaux = entree["point"].split(" :: ", 3)
        date_txt = morceaux[0].strip() if len(morceaux) == 4 else entree["point"]
        par_date[date_txt].append(entree)

    resultat = []
    for groupe in par_date.values():
        clusters = []
        for entree in groupe:
            morceaux = entree["point"].split(" :: ", 3)
            titre = morceaux[3] if len(morceaux) == 4 else entree["point"]
            for cluster in clusters:
                morceaux_ref = cluster[0]["point"].split(" :: ", 3)
                titre_ref = morceaux_ref[3] if len(morceaux_ref) == 4 else cluster[0]["point"]
                if _sont_doublons_agenda(titre, titre_ref, seuil):
                    cluster.append(entree)
                    break
            else:
                clusters.append([entree])

        for cluster in clusters:
            cluster.sort(key=lambda e: ("�" in e["point"], e["premiere_apparition"]))
            resultat.append(cluster[0])

    return resultat


def fusionner_et_nettoyer_agenda(nouveaux_points, jours_expiration_texte=21):
    """Fusionne les evenements du jour avec ceux deja stockes, supprime les
    doublons (stricts et reformules), retire les evenements dont la date
    precise est depassee, et retire les evenements a date approximative
    devenus trop anciens."""
    aujourdhui = datetime.now().date()
    stockes = charger_agenda_stocke()
    points_existants = {e["point"]: e for e in stockes}

    for point in nouveaux_points:
        if point not in points_existants:
            points_existants[point] = {
                "point": point,
                "premiere_apparition": aujourdhui.isoformat()
            }

    conserves = []
    for entree in _dedupliquer_agenda_par_date(list(points_existants.values())):
        morceaux = entree["point"].split(" :: ", 3)
        date_txt = morceaux[0].strip() if len(morceaux) == 4 else ""
        date_evt = parser_date_evenement(date_txt)

        if date_evt is not None:
            if date_evt >= aujourdhui:
                conserves.append(entree)
        else:
            premiere = datetime.fromisoformat(entree["premiere_apparition"]).date()
            if (aujourdhui - premiere).days <= jours_expiration_texte:
                conserves.append(entree)

    sauvegarder_agenda_stocke(conserves)

    def cle_tri(entree):
        morceaux = entree["point"].split(" :: ", 3)
        date_txt = morceaux[0].strip() if len(morceaux) == 4 else ""
        date_evt = parser_date_evenement(date_txt)
        return (0, date_evt) if date_evt is not None else (1, entree["premiere_apparition"])

    conserves.sort(key=cle_tri)
    return [e["point"] for e in conserves]

from google.genai import types as genai_types

def generer_briefing_json(client, prompt, tentatives_max=3, delai_secondes=20):
    """Appelle Gemini et parse le JSON, avec retry en cas de JSON malforme
    ou d'erreur serveur temporaire (503 - high demand). Detecte separement
    le quota journalier epuise (429), qui ne se resout pas par un retry."""
    import time
    from google.genai.errors import ServerError, ClientError

    for tentative in range(1, tentatives_max + 1):
        try:
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
                config=genai_types.GenerateContentConfig(
                    response_mime_type="application/json"
                )
            )
            texte_json = response.text.strip()
            return json.loads(texte_json)
        except ClientError as e:
            if getattr(e, "code", None) == 429 or "RESOURCE_EXHAUSTED" in str(e):
                print("Quota Gemini journalier épuisé, réessaie demain")
                raise SystemExit(1)
            raise
        except ServerError as e:
            print(f"Tentative {tentative}/{tentatives_max} - Erreur serveur Gemini (503) : {e}")
            if tentative == tentatives_max:
                raise
            print(f"Nouvelle tentative dans {delai_secondes} secondes...")
            time.sleep(delai_secondes)
        except json.JSONDecodeError as e:
            print(f"Tentative {tentative}/{tentatives_max} - Erreur JSON : {e}")
            print(f"Reponse brute recue : {texte_json[:2000]}")
            if tentative == tentatives_max:
                raise

data = generer_briefing_json(client, prompt)

# --- Enrichissement de l'Agenda avec recherche web, fusionne avec l'historique ---
agenda_points_nouveaux = get_agenda_enrichi(texte_complet, client) or []
agenda_points_fusionnes = fusionner_et_nettoyer_agenda(agenda_points_nouveaux)
for section in data["sections"]:
    if section["source"].lower() == "agenda":
        section["points"] = agenda_points_fusionnes if agenda_points_fusionnes else ["Aucun evenement identifie"]

REGIONS = {
    "usa": {"label": "USA", "code": "US"},
    "europe": {"label": "Europe", "code": "EU"},
    "asie": {"label": "Asie", "code": "ASIA"},
    "afrique": {"label": "Afrique", "code": "AFR"},
    "global": {"label": "Global", "code": "GLOBAL"},
}

# Palette categorielle "Ledger" — desaturee, distincte de l'accent de marque (brass)
# et des couleurs semantiques (gain/loss). Reservee aux puces de categorie.
CATEGORIES = {
    "geo": {"label": "Géopolitique", "couleur": "#6E6C63"},
    "corp": {"label": "Corporate", "couleur": "#5B7553"},
    "mkt-n": {"label": "Marchés", "couleur": "#8C6A2C"},
    "macro": {"label": "Macro", "couleur": "#3E5C76"},
    "tech": {"label": "Tech", "couleur": "#9C5B45"},
    "ai": {"label": "IA", "couleur": "#9C5B45"},
}


def slugifier(texte):
    texte = texte.lower()
    texte = texte.replace("&", "").replace(" ", "-")
    while "--" in texte:
        texte = texte.replace("--", "-")
    return texte.strip("-")


def parser_point(point):
    """Extrait (region, categorie, titre, detail) depuis 'region :: cat :: titre :: detail'.
    Tolerant aux variations d'espaces autour du separateur (:: , ::, :: etc.)."""
    import re
    morceaux = re.split(r'\s*::\s*', point.strip(), maxsplit=3)
    if len(morceaux) == 4:
        region, cat, titre, detail = morceaux
        region = region.strip().lower()
        cat = cat.strip().lower()
        if region not in REGIONS:
            region = "global"
        if cat not in CATEGORIES:
            cat = "mkt-n"
        return region, cat, titre.strip(), detail.strip()
    # Filet de securite si le format ne correspond toujours pas
    return "global", "mkt-n", point.strip(), ""


def mettre_en_valeur_chiffres(texte):
    """Convertit **texte** en <strong> stylee : classe 'highlight-figure' si le
    contenu porte un chiffre (montant, pourcentage, date...), sinon classe
    'highlight-phrase' pour les bouts de phrase-cles textuels."""
    import re

    def remplacer(match):
        contenu = match.group(1)
        if re.search(r'\d', contenu):
            return f'<strong class="highlight-figure">{contenu}</strong>'
        return f'<strong class="highlight-phrase">{contenu}</strong>'

    return re.sub(r'\*\*(.+?)\*\*', remplacer, texte)


def rendre_accordeon(points, numerote=False):
    items_html = ""
    for rang, point in enumerate(points, start=1):
        region, cat, titre, detail = parser_point(point)
        cat_info = CATEGORIES[cat]
        region_info = REGIONS[region]
        badge_rang = f'<span class="acc-rank">{rang}</span>' if numerote else ""
        detail_html = mettre_en_valeur_chiffres(detail)
        items_html += f"""
        <details class="acc-item" style="--cat-couleur:{cat_info['couleur']}">
          <summary class="acc-summary">
            {badge_rang}
            <span class="acc-region" title="{region_info['label']}">{region_info['code']}</span>
            <span class="acc-pill" style="background:{cat_info['couleur']}22;color:{cat_info['couleur']}">{cat_info['label']}</span>
            <span class="acc-title">{titre}</span>
            <span class="acc-chevron">›</span>
          </summary>
          <div class="acc-body">{detail_html}</div>
        </details>
        """
    return f'<div class="acc-list">{items_html}</div>'


def rendre_timeline_agenda(points):
    """Groupe les événements de l'agenda par date dans des menus déroulants (details/summary).
    Ne conserve que les dates au format jour par jour (ex: DD/MM ou DD/MM/YYYY)."""
    import re
    from collections import defaultdict
    evenements_par_date = defaultdict(list)
    pattern_date = re.compile(r'^\d{1,2}/\d{1,2}(/\d{2,4})?$')
    
    # 1. Parcourir et grouper par date
    for point in points:
        morceaux = point.split(" :: ", 3)
        if len(morceaux) == 4:
            date_txt, region, cat, titre = morceaux
        else:
            continue
            
        date_txt = date_txt.strip()
        if not pattern_date.match(date_txt):
            continue
            
        region = region.strip().lower()
        cat = cat.strip().lower()
        titre = titre.strip()
        
        evenements_par_date[date_txt].append({
            "region": region,
            "cat": cat,
            "titre": titre
        })
        
    # 2. Conserver l'ordre chronologique d'origine des dates
    dates_ordonnees = []
    for point in points:
        morceaux = point.split(" :: ", 3)
        if len(morceaux) == 4:
            d = morceaux[0].strip()
            if pattern_date.match(d) and d not in dates_ordonnees:
                dates_ordonnees.append(d)
            
    # 3. Générer le HTML final
    groups_html = ""
    for idx, date_txt in enumerate(dates_ordonnees):
        evs = evenements_par_date[date_txt]
        if not evs:
            continue
            
        rows_html = ""
        for ev in evs:
            cat_info = CATEGORIES.get(ev["cat"], CATEGORIES["mkt-n"])
            region_info = REGIONS.get(ev["region"], REGIONS["global"])
            
            rows_html += f"""
            <div class="agenda-event-row" style="--cat-couleur:{cat_info['couleur']}">
              <span class="acc-region" title="{region_info['label']}">{region_info['code']}</span>
              <span class="acc-pill" style="background:{cat_info['couleur']}22;color:{cat_info['couleur']};flex-shrink:0;">{cat_info['label']}</span>
              <span class="tl-title">{ev['titre']}</span>
            </div>
            """
            
        # Tous les groupes de dates restent fermes par defaut (l'utilisateur
        # deplie lui-meme celui qui l'interesse) — ne pas rouvrir la date du
        # jour automatiquement a chaque clic sur l'onglet Agenda.
        groups_html += f"""
        <details class="agenda-date-group">
          <summary class="agenda-date-summary">
            <span class="agenda-date-badge">{date_txt}</span>
            <span class="agenda-date-count">{len(evs)} { 'événement' if len(evs) == 1 else 'événements' }</span>
            <span class="agenda-date-chevron">▾</span>
          </summary>
          <div class="agenda-date-content">
            {rows_html}
          </div>
        </details>
        """
        
    return f'<div class="agenda-groups-list">{groups_html}</div>'


sentiment = data.get("sentiment", {"label": "Neutre", "raison": ""})
sentiment_classes = {"haussier": "sent-up", "baissier": "sent-down", "neutre": "sent-neutral"}
sentiment_classe = sentiment_classes.get(sentiment.get("label", "").lower(), "sent-neutral")

sentiment_raison_html = mettre_en_valeur_chiffres(sentiment.get('raison', ''))
sentiment_html = f"""
<div class="sentiment-box">
  <span class="sentiment-badge {sentiment_classe}">{sentiment.get('label', 'Neutre')}</span>
  <span class="sentiment-raison">{sentiment_raison_html}</span>
</div>
"""

nav_links = ""
tab_panels_html = ""

for i, section in enumerate(data["sections"]):
    nom_section = section["source"]
    slug = slugifier(nom_section)
    points = section["points"]

    nav_links += f'<button data-tab="{slug}">{nom_section}</button>\n'

    est_flash = nom_section.lower() == "flash"
    est_marches = nom_section.lower() == "marches"
    est_agenda = nom_section.lower() == "agenda"

    if est_agenda:
        contenu_panel = rendre_timeline_agenda(points)
    else:
        contenu_panel = rendre_accordeon(points, numerote=est_flash)

    bloc_sentiment = sentiment_html if (est_flash or est_marches) else ""

    tab_panels_html += f"""
    <div class="tab-panel" data-tab="{slug}">
      <h2 class="tab-title">{nom_section}</h2>
      {bloc_sentiment}
      {contenu_panel}
    </div>
    """

with open("template.html", "r", encoding="utf-8") as f:
    template = f.read()

# Jours/mois en francais formates a la main : independant de la locale du systeme
# (fr_FR.UTF-8/French_France ne sont pas garantis installes sur un runner Linux CI).
JOURS_FR = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
MOIS_FR = ["janvier", "fevrier", "mars", "avril", "mai", "juin", "juillet", "aout",
           "septembre", "octobre", "novembre", "decembre"]

maintenant = datetime.now()
date_str = f"{JOURS_FR[maintenant.weekday()]} {maintenant.day:02d} {MOIS_FR[maintenant.month - 1]} {maintenant.year}".capitalize()
heure_str = maintenant.strftime("%Hh%M")

html_final = (
    template
    .replace("{{DATE}}", date_str)
    .replace("{{HEURE}}", heure_str)
    .replace("{{NAV_LINKS}}", nav_links)
    .replace("{{SECTIONS}}", tab_panels_html)
)

with open("index.html", "w", encoding="utf-8") as f:
    f.write(html_final)

print("\nPage HTML generee avec succes !")

# --- Push automatique vers GitHub (declenche le redeploiement Vercel) ---
import subprocess

def pousser_vers_git():
    import time

    try:
        # agenda_events.json est inclus : sur un runner GitHub Actions ephemere,
        # c'est le seul moyen pour la memoire de dedoublonnage/expiration de
        # l'agenda de survivre d'une execution a l'autre.
        subprocess.run(["git", "add", "index.html", "agenda_events.json"], check=True)
        message_commit = f"Mise a jour automatique du {datetime.now().strftime('%d/%m/%Y %H:%M')}"
        resultat_commit = subprocess.run(
            ["git", "commit", "-m", message_commit],
            capture_output=True, text=True
        )
        if "nothing to commit" in resultat_commit.stdout:
            print("Aucun changement a pousser (contenu identique au precedent).")
            return
    except subprocess.CalledProcessError as e:
        print(f"Erreur lors du commit Git : {e}")
        return

    # Le push peut echouer sur un pepin reseau transitoire (surtout en CI) : on retente
    # quelques fois avec un court delai avant d'abandonner et de signaler l'echec.
    tentatives_max = 3
    for tentative in range(1, tentatives_max + 1):
        resultat_push = subprocess.run(
            ["git", "push"], capture_output=True, text=True
        )
        if resultat_push.returncode == 0:
            print("Push Git effectue avec succes, le site va redeployer automatiquement.")
            return
        print(f"Echec du push Git (tentative {tentative}/{tentatives_max}) : {resultat_push.stderr}")
        if tentative < tentatives_max:
            time.sleep(10)

    raise SystemExit(
        "Push Git abandonne apres plusieurs tentatives : le site n'a PAS ete redeploye. "
        f"Derniere erreur : {resultat_push.stderr}"
    )

pousser_vers_git()