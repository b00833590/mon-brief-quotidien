# mon-brief-quotidien

Brief financier quotidien automatisé, agrégé depuis Gmail (newsletters), RSS, et le PDF de recherche
Natixis, résumé par Gemini, rendu en une page HTML statique et déployé sur Netlify.

## Portée de ce dépôt — important

Ce dépôt Git ne contient **que le site statique généré** (`index.html`), son template
(`template.html`) et un JSON de secours (`indices_live.json`). **Le pipeline Python qui fait le
scraping et appelle Gemini ne fait pas partie de ce dépôt** : il vit un niveau au-dessus, dans le
dossier parent `Newsletters/` (hors Git ici), notamment dans `../gmail_test.py`. Si on cherche la
logique métier, c'est là qu'il faut aller — pas dans `index.html`.

Structure du dossier parent (non versionné dans ce repo) :
- `../gmail_test.py` — script principal, exécuté manuellement/planifié en local (~870 lignes) :
  scraping Gmail + RSS + Natixis + Les Echos, appel Gemini, génération HTML, push Git.
- `../credentials.json`, `../token.json` — OAuth Gmail/Drive (scopes `gmail.readonly`,
  `drive.readonly`). `token.json` est régénéré/rafraîchi automatiquement par le script.
- `../agenda_events.json` — mémoire persistante des événements d'agenda (dédoublonnage +
  expiration entre exécutions).
- `../refinitiv_stream.py` — pousse des cours live (Refinitiv/LSEG Workspace) vers le relais ticker
  (usage occasionnel/pro, distinct du flux Yahoo par défaut).
- `../ticker-relay/` — petit repo Git séparé (aiohttp), déployé sur Render, qui sert les cours
  boursiers live consommés par le bandeau ticker du site.

## Stack technique

- **Frontend** : une seule page HTML statique (`index.html`, ~4200 lignes), CSS et JS vanilla
  inline, pas de framework ni de build (pas de `package.json`). Onglets, mode sombre, bandeau
  ticker, recherche de tickers.
- **Auth/prefs utilisateur** : Supabase (`supabaseClient`, clé publique en dur dans `index.html`) —
  login/signup email+mdp, table `preferences_utilisateur` pour la sélection et la vitesse du ticker.
- **Cours live** : bandeau ticker qui interroge `https://ticker-relay.onrender.com` (`/latest`,
  `/latest-custom`, `/search`) — service séparé (`../ticker-relay/server.py`, aiohttp, poll Yahoo
  Finance non-officiel toutes les 3s).
- **Génération du contenu** : Python (`../gmail_test.py`), libs clés : `google-genai` (Gemini),
  `google-api-python-client` (Gmail + Drive), `playwright` + `PyMuPDF`/`fitz` (PDF Natixis),
  `feedparser` (RSS), `BeautifulSoup`, `yfinance`.
- **Déploiement** : Netlify, connecté au repo GitHub `mon-brief-quotidien`, déploiement
  automatique à chaque push sur `main` — pas de `netlify.toml` dans le repo, donc la config
  (site statique, aucune commande de build, publish = racine) est définie côté dashboard Netlify.

## Logique de scraping (dans `../gmail_test.py`)

1. **Gmail** (`service.users().messages().list`) : requête filtrée par expéditeurs (Aktionnaire,
   Arcos, FT, Semafor, Axios, Fortune, Finimize, The Daily Upside, WSJ, Bloomberg Money Stuff...),
   restreinte au jour même (`after:YYYY/MM/DD`), corps extrait en texte brut (fallback HTML→texte
   via BeautifulSoup).
2. **RSS** (`get_articles_rss`) : Bloomberg Markets + The Economist, 5 articles max par flux,
   reformatés comme des "emails" pour rester compatibles avec le pipeline existant.
3. **Les Echos** : cherche un email de moi-même (`from:me subject:Echos`) contenant un lien Google
   Drive, télécharge le PDF via l'API Drive, convertit les 6 premières pages en images PNG, et les
   envoie à Gemini Vision (`gemini-2.5-flash`) pour extraction directe (pas d'OCR classique).
4. **Natixis** (`get_dernier_article_natixis`) : appelle l'API JSON interne de
   `research.natixis.com` pour trouver la dernière publication "Morning Line Express"
   (`universe=FixedIncome`), puis utilise **Playwright** (Chromium headless) pour visiter la page
   et intercepter en vol la réponse réseau contenant le PDF (`/api/File/`, encodé en base64 dans un
   JSON) — pas de téléchargement direct par URL. Le texte est ensuite nettoyé en cherchant le
   marqueur `"MARKET LINES"` pour retirer le disclaimer légal.
5. **Indices marché** (`get_indices`, via `yfinance`) : calculés mais **actuellement non utilisés**
   — le résultat n'est injecté ni dans le prompt Gemini ni dans le HTML final (code mort à
   surveiller/nettoyer).
6. Tout le contenu texte est concaténé (`texte_complet`, 3000 caractères max par source) et envoyé
   à Gemini (`generer_briefing_json`) dans un unique prompt qui impose un format strict
   `"region :: categorie :: titre :: detail"` et une sortie JSON à 7 sections (Flash, Marchés,
   Macro, Corporate, Tech & IA, Briefing complet, Agenda).
7. **Agenda** : appel Gemini séparé (`get_agenda_enrichi`) avec `google_search` grounding, fusionné
   avec l'historique stocké dans `agenda_events.json` (dédoublonnage + expiration à 21 jours pour
   les dates approximatives, suppression des dates précises dépassées).
8. Le JSON est rendu en HTML (accordéons, timeline pour l'agenda) et injecté dans
   `template.html` (placeholders `{{DATE}}`, `{{HEURE}}`, `{{NAV_LINKS}}`, `{{SECTIONS}}`) pour
   produire `index.html`.
9. `pousser_vers_git()` fait `git add`/`commit`/`push` automatiquement depuis le dossier du repo —
   c'est l'origine des commits `"Mise a jour automatique du ..."` dans l'historique de ce dépôt.
   C'est aussi ce push qui déclenche le redéploiement Netlify.

## Points de fragilité connus

- **Quota Gemini journalier** : `generer_briefing_json` distingue une 503 (erreur serveur
  temporaire, retry 3x avec 20s de pause) d'une 429/`RESOURCE_EXHAUSTED` (quota épuisé) — dans ce
  dernier cas le script s'arrête directement (`SystemExit(1)`) **sans générer de brief ce jour-là**,
  pas de fallback ni de retry différé.
- **Clé API Gemini** : anciennement codée en dur dans `../gmail_test.py` et `../test.py` — corrigé,
  elle vit maintenant dans `../.env` (`GEMINI_API_KEY`, ignoré par `../.gitignore`), chargée via
  `python-dotenv` (`load_dotenv()` + `os.environ["GEMINI_API_KEY"]`). La clé Supabase dans
  `index.html` reste en dur mais c'est une clé publique (`sb_publishable_...`), donc son exposition
  côté client est normale.
- **Scraping Natixis fragile à plusieurs niveaux** : dépend (a) du format de l'API JSON interne de
  research.natixis.com, (b) de l'interception réseau Playwright d'une requête précise
  (`/api/File/`) — si le site change de mécanisme de chargement du PDF, l'interception échoue
  silencieusement (`pdf_bytes is None` → retourne `None`, pas d'erreur bloquante), et (c) du
  marqueur textuel `"MARKET LINES"` pour nettoyer le disclaimer — une refonte de mise en page côté
  Natixis casserait ce nettoyage sans lever d'exception.
- **Les Echos dépend d'un forward manuel** : le script cherche un email envoyé par moi-même
  (`from:me subject:Echos`) contenant un lien Drive — si l'email n'est pas transféré ce jour-là,
  la section est simplement absente, sans alerte.
- **Pipeline exécuté en local, pas en CI** : `gmail_test.py` tourne sur la machine de l'utilisateur
  (planifié ou manuel), pas via GitHub Actions ou un cron cloud — si la machine est éteinte ou le
  token Gmail OAuth expire sans refresh token valide, il faut relancer le flow `InstalledAppFlow`
  interactif (ouverture navigateur) pour ré-autoriser.
- **`yfinance` / API Yahoo Finance non-officielle** utilisée à la fois par `get_indices()` (mort,
  cf. ci-dessus) et par `../ticker-relay/server.py` pour le ticker live — API non documentée,
  peut changer ou rate-limiter sans préavis.
- **`ticker-relay` sur Render (plan gratuit probable)** : peut se mettre en veille après inactivité
  → premier appel lent ou échec transitoire au réveil du service, visible côté utilisateur comme un
  ticker figé ou vide.
- **`indices_live.json`** à la racine du repo semble être un instantané figé (dernière maj
  03/07/2026) et **n'est plus lu par `index.html`**, qui interroge directement `ticker-relay` côté
  client — probablement un résidu à supprimer plutôt qu'une source de données active.
- **Push Git non robuste** : si `git push` échoue (conflit, credentials expirés...), l'erreur est
  seulement loguée (`except subprocess.CalledProcessError`) — le nouveau `index.html` reste généré
  localement mais non déployé, sans retry automatique avant la prochaine exécution planifiée.
