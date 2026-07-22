# mon-brief-quotidien

Brief financier quotidien automatisé, agrégé depuis Gmail (newsletters), RSS, et le PDF de recherche
Natixis, résumé par Gemini, rendu en une page HTML statique et déployé sur Vercel.

## Portée de ce dépôt — important

**Mise à jour du 22/07/2026 : le pipeline vit maintenant dans ce dépôt et tourne dans le cloud.**
Ce dépôt contient le site statique généré (`index.html`), son template (`template.html`), **et le
pipeline Python complet** qui fait le scraping et appelle Gemini (`gmail_test.py`,
`requirements.txt`, `agenda_events.json`). Voir `RUNBOOK.md` pour l'exploitation du pipeline
automatisé (secrets, ré-autorisation Gmail si besoin, déclenchement manuel).

- `gmail_test.py` (~1000 lignes) : scraping Gmail + RSS + Natixis + Les Echos, appel Gemini,
  génération HTML, push Git.
- `.github/workflows/brief-quotidien.yml` — exécute le pipeline automatiquement à 8h et 13h heure
  de Paris, dans le cloud (GitHub Actions), indépendamment de toute machine locale allumée. Un job
  `gate` gère le décalage été/hiver (cron GitHub Actions toujours en UTC).
- `agenda_events.json` — mémoire persistante des événements d'agenda (dédoublonnage + expiration
  entre exécutions), re-committée à chaque run pour survivre aux runners GitHub Actions éphémères.
- `credentials.json`, `token.json`, `.env` — **non versionnés** (`.gitignore`, ce dépôt est
  public). Ne servent qu'aux exécutions manuelles locales. En CI, `token.json` est restauré à
  chaque run depuis le secret GitHub `GMAIL_TOKEN_JSON`, `GEMINI_API_KEY` depuis le secret du même
  nom — voir `RUNBOOK.md` pour la procédure de ré-autorisation si le refresh token expire.

Structure du dossier parent `Newsletters/` (hors Git, sans rapport avec ce dépôt) :
- `../refinitiv_stream.py` — pousse des cours live (Refinitiv/LSEG Workspace) vers le relais ticker
  (usage occasionnel/pro, distinct du flux Yahoo par défaut), inchangé.
- `../ticker-relay/` — petit repo Git séparé (aiohttp), déployé sur Render, qui sert les cours
  boursiers live consommés par le bandeau ticker du site, inchangé.
- Une copie historique de `gmail_test.py` existait aussi à cet endroit (utilisée par une tâche
  planifiée Windows locale, désactivée le 22/07/2026 au profit de l'automatisation cloud) — à
  considérer comme obsolète, la version qui fait foi est celle de ce dépôt.

## Stack technique

- **Frontend** : une seule page HTML statique (`index.html`, ~4200 lignes), CSS et JS vanilla
  inline, pas de framework ni de build (pas de `package.json`). Onglets, mode sombre, bandeau
  ticker, recherche de tickers.
- **Auth/prefs utilisateur** : Supabase (`supabaseClient`, clé publique en dur dans `index.html`) —
  login/signup email+mdp, table `preferences_utilisateur` pour la sélection et la vitesse du ticker.
- **Cours live** : bandeau ticker qui interroge `https://ticker-relay.onrender.com` (`/latest`,
  `/latest-custom`, `/search`) — service séparé (`../ticker-relay/server.py`, aiohttp, poll Yahoo
  Finance non-officiel toutes les 3s).
- **Génération du contenu** : Python (`gmail_test.py`, dans ce dépôt), libs clés : `google-genai`
  (Gemini), `google-api-python-client` (Gmail + Drive), `playwright` + `PyMuPDF`/`fitz` (PDF
  Natixis), `feedparser` (RSS), `BeautifulSoup`.
- **Déploiement** : Vercel (`mon-brief-quotidien.vercel.app`, confirmé via `Server: Vercel` dans les
  en-têtes HTTP), connecté au repo GitHub `mon-brief-quotidien`, déploiement automatique à chaque
  push sur `main` — pas de `vercel.json` dans le repo, donc la config (site statique, aucune
  commande de build, output = racine) est définie côté dashboard Vercel. (Corrigé le 2026-07-17 :
  ce fichier mentionnait Netlify par erreur — aucun site n'existe sur
  `mon-brief-quotidien.netlify.app`, qui renvoie 404.)

## Logique de scraping (dans `gmail_test.py`)

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
5. Tout le contenu texte est concaténé (`texte_complet`, 3000 caractères max par source) et envoyé
   à Gemini (`generer_briefing_json`) dans un unique prompt qui impose un format strict
   `"region :: categorie :: titre :: detail"` et une sortie JSON à 7 sections (Flash, Marchés,
   Macro, Corporate, Tech & IA, Briefing complet, Agenda).
6. **Agenda** : appel Gemini séparé (`get_agenda_enrichi`) avec `google_search` grounding, fusionné
   avec l'historique stocké dans `agenda_events.json` (dédoublonnage flou par mots-clés + expiration
   à 21 jours pour les dates approximatives, suppression des dates précises dépassées — voir
   `_dedupliquer_agenda_par_date` dans `gmail_test.py`).
7. Le JSON est rendu en HTML (accordéons, timeline pour l'agenda, tous les groupes de dates fermés
   par défaut) et injecté dans `template.html` (placeholders `{{DATE}}`, `{{HEURE}}`,
   `{{NAV_LINKS}}`, `{{SECTIONS}}`) pour produire `index.html`.
8. `pousser_vers_git()` fait `git add`/`commit`/`push` automatiquement (avec 3 tentatives en cas
   d'échec réseau transitoire) — c'est l'origine des commits `"Mise a jour automatique du ..."`
   dans l'historique de ce dépôt. C'est aussi ce push qui déclenche le redéploiement Vercel.

## Points de fragilité connus

- **Quota Gemini journalier** : `generer_briefing_json` distingue une 503 (erreur serveur
  temporaire, retry 3x avec 20s de pause) d'une 429/`RESOURCE_EXHAUSTED` (quota épuisé) — dans ce
  dernier cas le script s'arrête directement (`SystemExit(1)`) **sans générer de brief ce jour-là**,
  pas de fallback ni de retry différé.
- **Clé API Gemini** : anciennement codée en dur dans `gmail_test.py` et `../test.py` (dossier
  parent) — corrigé, elle vit dans `.env` en local (`GEMINI_API_KEY`, ignoré par `.gitignore`,
  chargé via `python-dotenv`) et dans le secret GitHub Actions `GEMINI_API_KEY` en CI. La clé
  Supabase dans `index.html` reste en dur mais c'est une clé publique (`sb_publishable_...`), donc
  son exposition côté client est normale.
- **Scraping Natixis fragile à plusieurs niveaux** : dépend (a) du format de l'API JSON interne de
  research.natixis.com, (b) de l'interception réseau Playwright d'une requête précise
  (`/api/File/`) — si le site change de mécanisme de chargement du PDF, l'interception échoue
  silencieusement (`pdf_bytes is None` → retourne `None`, pas d'erreur bloquante), et (c) du
  marqueur textuel `"MARKET LINES"` pour nettoyer le disclaimer — une refonte de mise en page côté
  Natixis casserait ce nettoyage sans lever d'exception.
- **Les Echos dépend d'un forward manuel** : le script cherche un email envoyé par moi-même
  (`from:me subject:Echos`) contenant un lien Drive — si l'email n'est pas transféré ce jour-là,
  la section est simplement absente, sans alerte.
- **Pipeline exécuté dans le cloud (GitHub Actions), pas sur une machine locale** (depuis le
  22/07/2026 — voir `RUNBOOK.md`) : tourne indépendamment de toute machine allumée, à 8h/13h heure
  de Paris. Point de fragilité résiduel : si le `refresh_token` Gmail stocké dans le secret
  `GMAIL_TOKEN_JSON` devient invalide (révocation, expiration à 7 jours si l'écran de consentement
  OAuth est encore en mode "Test"), le workflow échoue avec un message explicite — voir `RUNBOOK.md`
  pour la procédure de ré-autorisation (flow interactif local, puis mise à jour du secret).
- **`ticker-relay` sur Render (plan gratuit probable)** : peut se mettre en veille après inactivité
  → premier appel lent ou échec transitoire au réveil du service, visible côté utilisateur comme un
  ticker figé ou vide.
- **Cron GitHub Actions et changement d'heure** : le job `gate` du workflow compare l'heure locale
  Paris réelle (`TZ=Europe/Paris`) à 4 déclenchements UTC candidats pour absorber le décalage
  été/hiver — les 2 exécutions "hors créneau" par jour se terminent normalement après le seul job
  `gate` (quelques secondes, gratuit), ce n'est pas un dysfonctionnement.
