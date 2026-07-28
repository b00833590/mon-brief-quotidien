# RUNBOOK — Pipeline automatique (GitHub Actions)

Ce document couvre l'exploitation du pipeline `gmail_test.py` une fois qu'il tourne
automatiquement sur GitHub Actions (voir `.github/workflows/brief-quotidien.yml`),
2 fois par jour (8h/13h heure de Paris), indépendamment de toute machine locale.

## Architecture en un coup d'œil

- `gmail_test.py`, `requirements.txt`, `agenda_events.json` vivent maintenant **dans ce
  dépôt** (avant, ils vivaient dans le dossier parent non versionné — voir `CLAUDE.md`
  pour l'historique).
- Le workflow restaure `token.json` à partir du secret GitHub `GMAIL_TOKEN_JSON` au
  début de chaque exécution (le fichier n'est jamais committé — dépôt public).
- `GEMINI_API_KEY` est injectée via le secret GitHub du même nom.
- `credentials.json` n'est **pas** nécessaire en CI : le flow d'autorisation initiale
  (navigateur) n'est utilisé qu'en local ; en CI, on ne fait que rafraîchir le token
  existant via son `refresh_token`.
- `agenda_events.json` est re-committé à chaque exécution (mémoire de dédoublonnage/
  expiration de l'agenda) — sans ça, chaque exécution CI repartirait de zéro (runner
  éphémère).

## Symptôme : le workflow échoue avec "Token Gmail OAuth invalide/absent..."

Cause probable : le `refresh_token` stocké dans le secret `GMAIL_TOKEN_JSON` n'est
plus valide. Ça arrive si :
- l'accès a été révoqué manuellement (compte Google, page des accès tiers) ;
- l'écran de consentement OAuth du projet Google Cloud est en mode **Test** (les
  refresh tokens y expirent au bout de 7 jours) plutôt qu'en mode **Production** ;
- le token n'a pas été utilisé depuis plus de 6 mois (expiration normale de Google).

### Procédure de ré-autorisation

1. En local, dans `mon-brief-quotidien/`, vérifie que `credentials.json` est présent
   (sinon, le récupérer depuis la Google Cloud Console du projet OAuth concerné).
2. Supprime ou renomme le `token.json` local existant s'il est présent.
3. Lance `python gmail_test.py` en local — le flow interactif s'ouvre dans le
   navigateur (`InstalledAppFlow`), autorise l'accès, un nouveau `token.json` valide
   est écrit dans le dossier.
4. Copie le contenu intégral de ce nouveau `token.json` et remplace le secret GitHub :
   ```
   gh secret set GMAIL_TOKEN_JSON --repo b00833590/mon-brief-quotidien < token.json
   ```
5. Relance le workflow manuellement pour vérifier (onglet Actions → "Brief quotidien
   automatique" → "Run workflow", ou `gh workflow run brief-quotidien.yml`).

**Pour éviter de revivre ce problème** : si ce n'est pas déjà fait, faire passer
l'écran de consentement OAuth du projet Google Cloud correspondant de "Test" à
"Production" (ou au minimum "In production" sans vérification si l'app reste à usage
personnel) — ça supprime l'expiration à 7 jours des refresh tokens.

## Comment savoir si une exécution a eu lieu

- Onglet **Actions** du dépôt GitHub : historique des runs, avec le détail de chaque
  étape (utile pour voir à quelle étape ça a échoué : dépendances, token, scraping,
  Gemini, push...).
- Depuis le 28/07/2026, le workflow se déclenche toutes les 30 min entre 6h et 21h UTC
  (voir le commentaire dans le fichier de workflow) — plus de fenêtre stricte "8h ou
  13h Paris pile". L'étape "Verifier si un cycle a deja tourne pour ce creneau
  aujourd'hui" décide si un cycle est encore nécessaire aujourd'hui en comparant la
  date + le créneau (matin avant 12h / après-midi à partir de 12h, heure Paris) du
  dernier commit `"Mise a jour automatique"` à l'heure actuelle. La plupart des runs
  sont donc des runs très courts qui s'arrêtent juste après cette étape
  (`deja_fait=oui`, étapes suivantes marquées `skipped`) — c'est normal, pas une
  erreur : ça veut dire que le cycle du créneau en cours a déjà réussi.
- Un commit `"Mise a jour automatique du JJ/MM/AAAA HH:MM"` dans l'historique Git
  confirme qu'un cycle complet (scraping → Gemini → rendu → push) a réussi.
- **Incident connu (22/07/2026)** : un créneau planifié peut ne se déclencher ni à
  `:05` ni à `:35` — GitHub ne garantit aucune heure exacte pour un `schedule`.
- **Incident connu (26-28/07/2026)** : constaté que des runs `schedule` s'exécutent
  parfois avec plusieurs **heures** de retard (pas juste quelques minutes), ce qui
  faisait rater systématiquement l'ancienne fenêtre stricte "heure Paris == 8 ou 13"
  et a laissé le site sans contenu frais pendant ~2 jours sans qu'aucune erreur
  n'apparaisse dans les logs (les runs "en retard" se terminaient en succès après
  avoir simplement décidé de ne rien faire). Corrigé par le passage à un
  déclenchement toutes les 30 min + une vérification d'idempotence par
  date/créneau plutôt que par heure exacte (voir plus haut) — le pipeline se
  rattrape maintenant tout seul dans la journée même en cas de gros retard GitHub.
  Si un créneau (matin ou après-midi) venait quand même à manquer un jour entier,
  lancer manuellement via `gh workflow run` (voir ci-dessous).

## Lancer un cycle manuellement (sans attendre 8h/13h)

Depuis l'onglet Actions du dépôt, ou :
```
gh workflow run brief-quotidien.yml --repo b00833590/mon-brief-quotidien
```

## Quota Gemini épuisé (429 / RESOURCE_EXHAUSTED)

Le script s'arrête volontairement sans générer de brief ce jour-là (voir
`generer_briefing_json` dans `gmail_test.py`) — pas de retry automatique, le quota
se réinitialise le lendemain. Rien à faire, le prochain créneau (8h ou 13h) reprendra
normalement.
