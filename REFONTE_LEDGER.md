# Refonte visuelle "Ledger" — état d'avancement

Ce document est la référence pour reprendre le travail de refonte visuelle de Mon Brief
Quotidien dans une nouvelle session Claude, exactement là où une session précédente s'est
arrêtée. Il est volontairement factuel (valeurs réelles du code, pas des intentions) — en cas de
doute, le code fait foi, pas ce fichier.

## 1. Contexte du projet

Le produit centralise plusieurs sources financières (Gmail, RSS, PDF Natixis) et les résume
quotidiennement via Gemini dans une page unique. Les retours utilisateurs étaient très positifs
sur le contenu, mais critiques sur l'esthétique : trop "IA générée", emojis partout, aucune
crédibilité financière, look de prototype plutôt que de produit premium.

Objectif de la refonte : transformer l'habillage visuel en quelque chose qui inspire
immédiatement confiance et sérieux (référence : Bloomberg Terminal, FT, Linear, Stripe
Dashboard — sans les copier), **sans toucher au cœur fonctionnel ni au pipeline de contenu**.

Voir `CLAUDE.md` dans ce dépôt pour l'architecture technique complète (répartition du code entre
ce dépôt Git et le dossier parent non versionné).

## 2. Découverte importante à connaître

Au début du travail de refonte, un audit complet du produit en production a débouché sur une
proposition de design system détaillée ("Ledger" : encre/papier/laiton, typographies
Fraunces/IBM Plex Sans/IBM Plex Mono, rayons ≤4px, quasi zéro ombre portée), livrée sous forme de
document de direction artistique.

**Mais au moment de passer à l'implémentation, `template.html` contenait déjà un travail non
commité substantiel** (rail de navigation latéral, ticker en chasse fixe, cartes `acc-item`,
badges de sentiment, mode sombre, emojis déjà remplacés par des SVG) — visiblement une tentative
antérieure d'exécuter le même brief, avec des choix concrets différents (voir §3). Plutôt que
d'écraser ce travail pour repartir des valeurs exactes du document de direction artistique, le
choix a été de **construire sur cette base existante** (moins risqué : elle est déjà compatible
avec ce que génère `gmail_test.py`) et d'aligner dessus les évolutions suivantes.

**Conséquence pratique : les valeurs de couleurs/typographies ci-dessous (§3) sont la seule
source de vérité. Ne pas essayer de faire correspondre le code aux hex exacts d'un document de
direction artistique antérieur — ce document a été superseded par l'implémentation réelle.**

## 3. Design system réellement implémenté (dans `template.html`)

**Attention, ces valeurs ont déjà dérivé une fois** : une version antérieure de ce document
documentait Newsreader/Plus Jakarta Sans/JetBrains Mono + accent or (`#b45309`) — ces valeurs
avaient déjà été remplacées dans le code (par quelqu'un/une session non documentée ici) par
Fraunces + IBM Plex Sans/Mono + laiton (`#8C6A2C`) avant même que la session actuelle ne commence
à y toucher. **Ce paragraphe reflète l'état après la dernière modification connue (voir §4,
point 5) — mais vérifie toujours `template.html` directement avant de t'y fier.**

- **Polices** : `--serif: 'Playfair Display'` (titres éditoriaux, en capitales), `--sans: 'IBM
  Plex Sans'` (interface/corps), `--mono: 'IBM Plex Mono'` (tous les chiffres — ticker, dates,
  badges, pourcentages). Chargées via Google Fonts (`<link>` dans le `<head>`, pas de
  self-hosting).
- **Couleurs clé** (thème clair / thème sombre) :
  - Accent (bleu marine, plus laiton) : `--accent: #1A3A6B` / `#467CC8`
  - Fond page : `--bg: #F8F6F1` / `#0B0B09`
  - Fond carte : `--card-bg: #FFFFFF` / `#15150F`
  - Bandeau ticker : `--ticker-bg: #0B0B09` / `#060605` — **toujours sombre, y compris en thème
    clair** (contraste volontaire façon salle de marché), texte du ticker en blanc translucide
    fixe (pas les tokens `--text`/`--text-soft`, qui suivraient le thème et deviendraient
    illisibles sur fond toujours sombre).
  - Hausse : `--green: #006633` / `#00A854` — Baisse : `--red: #CC0000` / `#DD2222`. Le ticker et
    le bandeau "tendance du jour" utilisent des variantes plus vives et fixes (`#00CC66`/`#FF3300`)
    pour un effet "pouls du marché" plus intense que le reste du contenu, volontairement.
  - Régions (`.acc-region[title="..."]`, sélecteur par attribut, pas de classe dédiée) : USA
    `#1A3A6B`, Europe `#003399`, Asie `#7A1F1F`, Afrique `#5A4324`, Global `#2A2A2A` — badges
    pleins, pas de bordure.
  - Alias legacy présents (`--ink`, `--brass`, `--parchment`...) pour compat, tous dérivés des
    variables ci-dessus.
- **Rayons** : `--radius-sm: 1px`, `--radius-md: 2px`, `--radius-lg: 2px` — très serrés (angles
  quasi droits), plus stricts que les deux versions précédentes.
- **Ombres** : quasi supprimées (`--shadow-sm: none`), les cartes/lignes utilisent des filets
  (hairlines) plutôt que l'élévation.
- **Layout** : CSS Grid plein écran (`header` / `nav` (rail latéral 280px, repliable à 60px) /
  `search` / `main`), bascule en layout mobile empilé + barre de navigation basse sous 768px.
- **Composants clés et leurs classes** (contrat utilisé aussi par `gmail_test.py`, ne pas
  renommer sans mettre à jour le générateur Python) :
  - `.acc-item` / `.acc-summary` / `.acc-rank` / `.acc-region` / `.acc-pill` / `.acc-title` /
    `.acc-body` — ligne de brève en registre (accordéon natif `<details>/<summary>`), **plus une
    carte** depuis le point 5 du §4 : filets horizontaux, pas de bordure/ombre/radius par item,
    `.acc-rank` = carré marine plein, `.acc-region` = badge plein colore par region via
    l'attribut `title` deja pose par Python (`Global`/`USA`/`Europe`/`Asie`/`Afrique`).
  - `.sentiment-box` / `.sentiment-badge` (`.sent-up/.sent-down/.sent-neutral`) — bandeau Flash,
    **restructure en deux panneaux** depuis le point 5 du §4 : `.sentiment-badge` devient un
    panneau marine plein (mot de tendance en grand, ex. "Neutre"/"Haussier"/"Baissier") avec un
    liseret bas colore selon `.sent-*` ; `.sentiment-raison` devient le panneau clair a cote.
    Aucun nouveau champ de donnee requis — uniquement une restructuration visuelle des 2 memes
    enfants deja generes par Python.
  - `.tl-item` / `.tl-date` / `.tl-dot` / `.tl-content` et `.agenda-date-group` /
    `.agenda-event-row` — agenda groupé par date
  - `.ticker-item` — élément du bandeau de cours (chasse fixe, `tabular-nums`), désormais dans un
    wrapper `.ticker-viewport` (porte le masque de fondu) lui-même dans `.ticker-bar` (qui porte
    aussi `.ticker-fixed-label`, statique, "Marchés en direct" en rouge, visible ≥769px) —
    **si tu touches au ticker, ne remets pas le masque de fondu directement sur `.ticker-bar`**,
    il doit rester sur `.ticker-viewport` sinon l'étiquette fixe se fond aussi.
  - `.highlight-figure` / `.highlight-phrase` — mise en évidence des chiffres/phrases clés dans
    le texte généré par Gemini

## 4. Ce qui a été fait dans **cette session** (en plus de l'existant ci-dessus)

Toutes ces évolutions ont été faites **sans toucher à `gmail_test.py`** (aucun changement du
contrat de données/markup généré), donc à faible risque, et vérifiées via un serveur HTTP local
avant déploiement (voir §6).

1. **Rail de navigation repliable en icônes** (desktop, ≥901px) — bouton de repli en haut du
   rail (`#navCollapseToggle`), 8 icônes SVG line-art minimalistes injectées en JS par
   `data-tab` (`flash`, `marches`, `macro`, `corporate`, `tech-ia`, `briefing-complet`,
   `agenda`, `indices-entreprises`), état replié persistant via `localStorage`
   (`navReplie`). Largeur repliée : 60px, labels/compteurs masqués.
2. **Priorisation visuelle du Flash** — les 2 premières brèves (déjà classées par ordre
   d'importance par Gemini) reçoivent une classe `.acc-item--top` (liseré de couleur catégorie +
   badge de rang accentué). Pas de nouvelle donnée inventée : uniquement une mise en valeur du
   rang déjà généré.
3. **Squelette de chargement du ticker** — le texte "Chargement..." initial est remplacé par 6
   blocs `.ticker-skeleton` animés (`@keyframes skeleton-shimmer`), désactivés si
   `prefers-reduced-motion`. Remplacés automatiquement par les vraies données dès leur arrivée.
4. **Navigation clavier étendue** — `j`/`k` (ou flèches ↓/↑) déplacent le focus entre les brèves
   de l'onglet actif (`.acc-summary`, `.agenda-date-summary`), `Entrée`/`Espace` ouvre/ferme
   (natif `<summary>`, gratuit). Anneau de focus visible ajouté (`:focus-visible`) qui n'existait
   pas auparavant. Ignoré si le focus est dans un champ de saisie.

5. **Port visuel d'une maquette de référence construite sur Replit** — l'utilisateur a construit
   une maquette (React + Vite + Tailwind, non connectée aux données, contenu codé en dur dans
   `src/lib/data.ts`) sur Replit et a explicitement demandé qu'elle serve de **référence visuelle
   uniquement** — pas un remplacement d'architecture (question posée et tranchée en session : voir
   le choix "Juste une référence visuelle"). Le pipeline Python et le contrat de markup n'ont
   **pas** été touchés. Ont été portés dans `template.html` (tokens CSS + quelques ajustements de
   markup statique, aucun changement dans `gmail_test.py`) :
   - Accent laiton → bleu marine, serif Fraunces → Playfair Display, rayons resserrés à ~2px
     (détails exacts en §3).
   - Ticker : fond toujours sombre (même en thème clair), étiquette fixe "Marchés en direct" en
     rouge, séparateurs par filet plutôt que puces bordées.
   - `.acc-item` : passage de carte (bordure/ombre/radius) à ligne de registre (filet horizontal
     uniquement), `.acc-rank` en carré marine plein, `.acc-region` en badge plein coloré par
     région (via l'attribut `title` déjà posé par Python — pas de nouvelle donnée).
   - `.sentiment-box` restructuré en deux panneaux (marine plein + papier clair) — cf. §3.
   - Titres de section (`h2.tab-title`) : double filet façon masthead (2px + hairline), capitales.
   Non porté (délibérément, hors scope "référence visuelle") : les tableaux "Indices Majeurs /
   Valeurs Phares" (nécessiteraient une vraie fonctionnalité de données, absente aujourd'hui —
   notre onglet "Indices & Entreprises" sert à choisir les indices du bandeau, pas à afficher un
   tableau de cours), et le contenu structuré résumé/impact/timestamp de la maquette Replit
   (nécessiterait de changer le prompt Gemini et le format JSON — évalué comme trop risqué pour un
   simple portage visuel).

6. **Réplique fidèle du header et du widget "live" de la barre latérale** — l'utilisateur a
   demandé une correspondance exacte avec la maquette Replit (pas juste "dans l'esprit"), après
   avoir partagé le code source complet des composants. Header entièrement restructuré : barre
   d'accent marine à gauche (4px), wordmark "MON BRIEF" (gras) + "QUOTIDIEN" (normal) sur une
   ligne, recherche avec prompt "›" (plus icône loupe), fond translucide noir/blanc 5%, bloc
   date+heure combiné sur une ligne (`{{DATE}} / GÉNÉRÉ À {{HEURE}}`, tokens Python inchangés),
   bouton thème texte "DARK / LIGHT" (soulignement sur l'état actif) au lieu d'un bouton icône
   rond — JS de `toggleTheme()` réécrit en conséquence. Widget latéral : titre "Live marchés" avec
   point rouge pulsant (`.nav-summary-live-dot`), bloc "Tendance globale" agrandi et coloré selon
   le **vrai sentiment** (vert/rouge/gris) plutôt que toujours rouge comme dans la maquette (la
   maquette utilise du rouge fixe faute de données réelles — nous en avons, donc autant être
   honnête). Hauteur du header réduite à 56px desktop / 48px mobile.

7. **Sparklines dans le panneau "Résumé en direct" de la barre latérale** — contrairement à la
   maquette Replit (dont les sparklines utilisent des points fixes/fictifs, juste illustratifs),
   celles-ci tracent un **historique réel** accumulé côté client : `historiqueSpark` (objet en
   mémoire, clé = nom de l'indice, jusqu'à 20 valeurs) est alimenté à chaque tick du ticker déjà
   existant (`recupererTicker`, toutes les 1s). Tant qu'il n'y a pas au moins 2 points observés
   (juste après le chargement de la page), un trait neutre s'affiche à la place plutôt qu'un faux
   graphique. Choix délibéré : ne jamais afficher une tendance visuelle qui ne reflète pas des
   données réellement observées, sur un produit financier. Fonctions : `pointsSparkline()` et
   `afficherResumeBarres()` dans le `<script>` de `template.html`. Réinitialisé à chaque
   rechargement de page (pas de persistance entre sessions — acceptable pour un usage "coup d'œil
   du matin").

8. **Passe de fidélité exacte à la maquette de référence** — l'utilisateur a comparé
   côte-à-côte une capture du site déployé et une capture de la maquette Replit, et a demandé une
   correspondance exacte (pas juste "dans l'esprit"). Corrections :
   - `MARCHÉS EN DIRECT` (étiquette ticker) en majuscules forcées (`text-transform`).
   - Barre de recherche élargie (480px → 640px de large max), placeholder changé pour
     "RECHERCHER SYMBOLE OU MOT-CLÉ..." (au lieu de mentionner Ctrl+K, qui reste fonctionnel).
   - **Rail latéral simplifié** : icônes SVG par section **retirées** (l'utilisateur les a
     jugées superflues — la maquette de référence n'en a jamais eu, c'était un ajout perso non
     demandé). Largeur ouverte réduite 280px → 240px. Libellés des onglets en majuscules
     (`text-transform`). Le bouton de repli n'est plus un item de liste pleine largeur : c'est
     maintenant un petit bouton fantôme (26x26px) sorti de `.inner`, aligné à droite en haut du
     rail, centré quand replié à 44px — replié, tout le contenu de `.inner` et `.nav-summary`
     est masqué (plus de mode "icônes seules", qui n'a plus de sens sans icônes).
   - Titres de section (`h2.tab-title`) : le double filet (bordure 2px + hairline) se chevauchait
     visuellement (positionnement `::after` trop proche) — corrigé (`bottom: -8px` au lieu de
     `-3px`, clairement séparé maintenant).
   - **Méta à droite des titres de section**, absente jusqu'ici : "Synthèse du HH:mm" pour Flash
     (heure calculée côté client, comme dans la maquette), "{N} articles" pour les autres
     sections avec liste (compté côté client sur `.acc-item`), rien pour Agenda/Indices. Nouvelle
     IIFE dans le `<script>`, aucun changement Python.
   - Séparateur "—" ajouté entre nom et valeur dans chaque item du ticker (manquant).
   - Badge de compteur (`.nav-count`) sur l'onglet actif : pastille translucide blanche
     restaurée (perdue par erreur lors d'un nettoyage précédent dans la même session).
   - Chevron des brèves (`.acc-chevron`) : `▾` → `›` avec rotation 90° à l'ouverture (au lieu de
     `▴`/rotation 180°) — **seul changement Python de toute la refonte** (une ligne dans
     `gmail_test.py`, glyphe uniquement, aucun impact sur le contrat de données/JSON).
   Non corrigé, délibérément : la sous-ligne rouge courte sous "TENDANCE DU JOUR" dans le panneau
   marine (ex. "Pétrole & Tech sous pression") — la maquette la fabrique côté React sans donnée
   réelle correspondante ; nous n'avons que le paragraphe complet (`sentiment-raison`), pas de
   version courte. Fabriquer une fausse phrase courte serait malhonnête ; laisser le paragraphe
   complet dans le panneau clair est le choix retenu.

9. **Nouvelle passe de fidélité, à partir d'une capture d'écran cible fournie directement** (pas
   la maquette Replit en live cette fois, mais un screenshot statique "Site cible.png" comparé à
   une capture "Site actuel.png" du site déployé). Différences identifiées puis corrigées :
   - Barre de recherche resserrée (640px → 520px de large max), la cible est plus compacte que ce
     qui avait été élargi au point 8 ci-dessus.
   - **Marge gauche du contenu principal fortement réduite** : `main` centrait un bloc
     `max-width:1000px` par `margin:0 auto`, ce qui créait un gutter flottant (dépendant de la
     largeur de la fenêtre) bien plus large que sur la cible. Remplacé par `max-width:1200px;
     margin:0` (ancrage à gauche, contre la sidebar), plus fidèle à une mise en page éditoriale
     classique.
   - Flèches ▲/▼ ajoutées devant les pourcentages dans le bloc "Live Marchés" de la sidebar
     (`afficherResumeBarres()`) — le ticker principal (`afficherTicker()`) les avait déjà, seul le
     mini-ticker latéral en manquait.
   - Lignes de la liste d'actualités agrandies (padding vertical 13px → 19px) et titre agrandi
     (15.5px → 17px) pour matcher la densité de la cible.
   - **Catégorie de chaque brève (`.acc-pill`, ex. "Géopolitique", "Tech") transformée de badge
     coloré en texte gris nu précédé d'un séparateur `·`** — mais seulement dans les listes
     d'actualités (`.acc-summary .acc-pill`, via `!important` pour neutraliser la couleur inline
     posée par Python sans y toucher). Les badges colorés `.acc-pill` de l'agenda
     (`.agenda-event-row .acc-pill`) n'ont volontairement pas été touchés — non visibles sur la
     cible, scope limité au strict nécessaire.
   - **"Synthèse du HH:mm" retirée du titre Flash** (décision explicite de l'utilisateur, assumée
     comme déviation par rapport à la cible qui, elle, affiche cette mention).
   - **Vitesse par défaut du bandeau ticker passée de 26s à 34s** (décision explicite de
     l'utilisateur, sans rapport avec le screenshot) — CSS (`@keyframes`/`.ticker-track`) + tous
     les fallbacks JS (`localStorage`, Supabase, curseur de réglage) mis à jour en cohérence.
   Délibérément non fait : la courte phrase de tendance sous l'état ("Pétrole & Tech sous
   pression" sur la cible) n'a pas été ajoutée, faute de donnée réelle correspondante côté
   pipeline — un seul paragraphe complet existe (`sentiment-raison`), pas de version courte.
   Fabriquer cette phrase aurait été malhonnête sur un produit financier (même principe qu'au
   point 7 ci-dessus pour les sparklines). Écart visuel assumé avec la cible sur ce point précis.
   Vérifié avant/après : JS extrait valide (`node --check`), balises HTML équilibrées, prévisualisé
   via le serveur HTTP local (jamais `file://`), mode sombre et ouverture d'accordéon testés —
   aucune régression fonctionnelle.

10. **Retrait du liseré coloré des 2 premières brèves du Flash + restauration du compteur
    d'articles.** `.acc-item--top` (priorisation visuelle ajoutée au point 2) affichait un
    `box-shadow` coloré à gauche des 2 premières brèves du Flash — retiré à la demande explicite
    de l'utilisateur (règle `.acc-item--top { box-shadow: ... }` supprimée ; le badge de rang
    accentué de `.acc-item--top .acc-rank` n'a pas été touché, non concerné par la demande). Par
    ailleurs, le retrait de "Synthèse du HH:mm" au point 9 avait eu un effet de bord non voulu :
    `flash` avait été ajouté à `SANS_META`, ce qui supprimait aussi le compteur "N articles" du
    titre Flash (alors que tous les autres onglets l'ont). Corrigé en retirant `flash` de
    `SANS_META` — Flash affiche maintenant son compteur d'articles comme les autres onglets, sans
    réintroduire la mention d'heure.

11. **Optimisation de l'affichage mobile.** Testé à largeur réelle de téléphone (390px) via une
    iframe de test dédiée (la fenêtre du navigateur de l'outil ne descend pas sous ~784px dans cet
    environnement — technique de contournement à réutiliser si besoin : `<iframe style="width:
    390px; height:844px">` pointant vers le fichier de prévisualisation, qui a son propre contexte
    de viewport indépendant de la fenêtre). 4 problèmes trouvés et corrigés dans
    `@media (max-width: 768px)` :
    - **Bug critique — bouton de thème inaccessible** : le bloc date/heure + `DARK`/`LIGHT`
      débordaient de 142px hors du viewport (mesuré via `getBoundingClientRect()`), invisibles à
      cause de `overflow-x: hidden` sur `body`. Corrigé en passant `header .top` en
      `flex-wrap: wrap` (`height: auto` au lieu de `48px` fixe) : le header s'affiche désormais sur
      2 lignes sur mobile (logo + icône recherche en haut, date/thème alignés à droite en dessous).
    - **Recherche rendue accessible sur mobile** : `header .header-search` était masquée
      (`display: none`) sans aucune alternative. Ajout d'un bouton loupe `#mobileSearchToggle`
      (visible uniquement ≤768px) qui bascule la classe `mobile-search-active` sur `body` : la
      barre de recherche apparaît alors en pleine largeur sur sa propre ligne, avec focus
      automatique sur `#searchInput`.
    - **Bloc "Tendance du jour" empilé verticalement** (`.sentiment-box { flex-direction: column }`
      sur mobile) — la largeur minimale du panneau navy (`clamp(180px, 30%, 260px)` en desktop)
      forçait ce panneau à occuper environ la moitié de la largeur sur un écran de téléphone,
      écrasant le paragraphe de résumé à côté.
    - **Catégorie de l'agenda non tronquée** : `.agenda-event-row .acc-pill` avait une largeur fixe
      de 90px en desktop, tronquant "GÉOPOLITIQUE" en "GÉOPOLITIQU…" sur mobile. Passé à
      `width: auto` dans le bloc mobile.
    Vérifié après coup : JS extrait valide, balises équilibrées, testé Flash/Agenda/Indices &
    Entreprises/mode sombre à 390px réels (pas juste en forçant les media queries sur une fenêtre
    large, qui aurait masqué les problèmes de débordement).

### Bug réel trouvé et corrigé pendant cette session

Le bouton de repli du rail (`#navCollapseToggle`, point 1 ci-dessus) n'a pas de `data-tab`. Le
code JS existant sélectionnait `#navTabs button` **sans filtrer sur `[data-tab]`** à plusieurs
endroits (sélection de l'onglet par défaut au chargement, attachement des clics) — du coup
`boutons[0]` devenait ce bouton de repli au lieu du bouton "Flash", et cassait l'onglet actif par
défaut. **Corrigé partout** : tous les `document.querySelectorAll('#navTabs button')` du fichier
utilisent maintenant `'#navTabs button[data-tab]'`. À garder en tête si un nouveau bouton sans
`data-tab` est ajouté dans `#navTabs` un jour.

## 5. État du roadmap (par rapport à l'audit initial)

- **Quick wins** (emojis supprimés, chasse fixe sur les chiffres, badges normalisés, rayons
  réduits) — **fait**, avant cette session (présent dans le `template.html` déjà trouvé).
- **Intermédiaire** (rail de nav, thèmes clair/sombre, composantisation, squelettes de
  chargement, mise en avant du Flash) — **fait**.
- **Avancé** : navigation clavier j/k — **fait**. Restent non traités si utile un jour :
  système de graphiques dédié (aucun graphique n'existe actuellement dans le produit — pas
  demandé explicitement, à évaluer avec l'utilisateur avant de s'y lancer), audit
  d'accessibilité WCAG AA formel (contraste vérifié au cas par cas mais pas d'audit systématique
  outillé), documentation du design system en tant que page dédiée.

## 6. Comment prévisualiser sans rien casser (important)

`template.html` contient des placeholders (`{{DATE}}`, `{{HEURE}}`, `{{NAV_LINKS}}`,
`{{SECTIONS}}`) remplis uniquement par `gmail_test.py`. Pour prévisualiser un changement de
`template.html` **sans relancer tout le pipeline** (coûte du quota Gmail/Gemini et pousse sur
Git) :

1. Extraire `{{DATE}}`/`{{HEURE}}`/`{{NAV_LINKS}}`/`{{SECTIONS}}` déjà rendus dans le
   `index.html` actuel (regex sur les mêmes marqueurs que le template), et les réinjecter dans le
   `template.html` modifié pour produire un fichier de prévisualisation autonome.
2. **Ne pas ouvrir ce fichier en `file://` direct** dans le navigateur de l'outil — il se rend en
   "static snapshot" et n'exécute pas le JavaScript (piège rencontré cette session). Servir via
   un petit serveur HTTP local à la place :
   - Config déjà créée : `Newsletters/.claude/launch.json`, entrée `"static-preview"`
     (`python -m http.server 8934 --bind 127.0.0.1`).
   - Démarrer via l'outil de preview avec `name: "static-preview"`, puis naviguer vers
     `http://localhost:8934/<fichier-de-preview>.html`.
3. Pour un test d'interaction fiable (clics, focus clavier), passer par `javascript_tool` en
   inspection plutôt que par les coordonnées d'écran — le clic par coordonnées et les
   captures d'écran se sont montrés peu fiables dans cet environnement.
4. Toujours vérifier au minimum : équilibrage des balises (`div`/`span`/`svg`/`button`...),
   syntaxe JS (`node --check` sur le contenu du `<script>` extrait).

## 7. Comment déployer pour de vrai

```
cd "Newsletters"
python gmail_test.py
```

- Tourne ~2-5 minutes (Gmail, RSS, PDF Natixis via Playwright, appel Gemini, rendu HTML).
- Fait automatiquement `git add`/`commit`/`push` **mais uniquement sur `index.html`** (pas
  `template.html`, qui reste "modifié, non commité" en permanence — c'est normal, voir
  `CLAUDE.md`, ce n'est pas un oubli).
- Le push déclenche le redéploiement automatique sur Vercel.
- **Ne jamais lancer ce script sans confirmation explicite de l'utilisateur dans le message en
  cours** — il pousse sur un dépôt public et consomme du quota Gemini/Gmail limité.
- Bug déjà corrigé à connaître : la console Windows (cp1252) plantait sur `print()` si un sujet
  d'email contenait un emoji — fixé par `sys.stdout.reconfigure(encoding='utf-8',
  errors='replace')` en tête de `gmail_test.py`.

## 8. Pièges d'environnement rencontrés (pour gagner du temps)

- L'outil de capture d'écran (`computer` / `screenshot`) time-out fréquemment dans cet
  environnement — ne pas s'appuyer dessus pour vérifier un rendu. Préférer `read_page`,
  `get_page_text`, `read_console_messages`, `javascript_tool` (inspection uniquement, jamais
  pour implémenter).
- L'outil Bash a occasionnellement renvoyé une erreur transitoire de type "classifier
  unavailable" pendant cette session — PowerShell a servi de repli fiable dans ces cas-là.
- Les fichiers `preview_ledger*.html` à la racine de `Newsletters/` sont des aperçus jetables,
  pas des artefacts à maintenir.
