# Instructions pour Claude Code — Cockpit

Tu maintiens un outil industriel EVE Online local. L'utilisateur est francophone : réponds en français,
garde toute l'interface en français.

## Architecture
- `app/paths.py` : chemins compatibles script et .exe PyInstaller (données utilisateur dans `data/` à côté de l'exe).
- `app/settings.py` : réglages ; `distribution.json` (facultatif) fournit Client ID, corpo et structures communes.
- `app/sde.py` : téléchargement + parsing du SDE CCP (JSON Lines : types, groups, categories, blueprints).
- `app/esi.py` : client ESI (header `X-Compatibility-Date`, constante `COMPAT_DATE`), Fuzzwork, SSO PKCE, cache disque.
- `app/industry.py` : moteur de calcul. Toutes les formules EVE sont ici (docstring en tête de fichier).
- `app/opportunities.py` : scan industriel + arbitrage.
- `app/fits.py` : format EFT, fittings ESI, compétences requises (avec prérequis), temps d'entraînement.
- `app/doctrines.py` : doctrines perso (data/doctrines.json) et officielles corpo (distribution.json / doctrines_url).
- `app/pvp.py` : analyse D-scan, client zKillboard, niveau de menace, standings (classify / merge_standings).
- `app/galaxy.py` : carte (sécurité, itinéraires Dijkstra, ponts de saut, EVE-Scout, liens Dotlan).
- `app/winwin.py` : fenêtres EVE sous Windows (ctypes : liste, premier plan, PrintWindow) ; testé via un faux backend.
- `app/planetary.py` : planétaire (planètes par système, schémas P0 -> P4, analyse d'un rayon, meilleurs systèmes).
- `static/i18n.js` + `static/i18n-data.js` : traduction de l'interface (anglais par défaut).
- `site/` : site de présentation statique multilingue (build.py génère site/dist).
- `app/sounds.py` : sons d'alarme synthétisés en WAV (volume intégré).
- `app/alarm.py` : alarme local (capture d'écran mss + comptage de couleurs numpy) et intel (logs de chat UTF-16).
  Aucune interaction avec le client EVE : ne JAMAIS ajouter d'envoi de touches, de clics ou de lecture mémoire.
- `app/version.py` : version et notes de patch (source unique, affichée dans l'outil).
- `app/server.py` : API FastAPI + tâches de fond (scan, arbitrage, mise à jour SDE).
- `static/` : interface (HTML/CSS/JS sans framework).
- `tests/` : tests hors ligne avec un mini-SDE (`tests/fixture.py`).
- `app/selfcheck.py` : contrôle en conditions réelles (réseau).

## Règles
00. **Traductions** : l'interface est écrite en français (texte source) et traduite par `static/i18n.js` à partir de
    `static/i18n-data.js` (clé = texte français exact tel qu'affiché, `{n}` = nombre, `{x}` = texte libre). Tout nouveau
    texte d'interface doit recevoir sa traduction anglaise (obligatoire) et, si possible, ES/DE/RU. Vérification : passer
    l'outil en anglais et chercher les textes restés en français.
01. **Site** : `site/content_*.py` contient les textes du site par langue ; toute nouvelle fonction de l'outil reçoit
    une entrée dans les 5 langues (clé dans FEATURES_ORDER), puis `python site/build.py`.
0. **Versionnage obligatoire** : toute évolution livrée incrémente `VERSION` dans `app/version.py` (correctif : 1.2.1 ;
   fonctionnalité : 1.3.0) et ajoute une entrée EN TÊTE de `CHANGELOG` (date, titre, résumé, listes `added` / `changed`
   en français simple, du point de vue du joueur). Régénère ensuite `CHANGELOG.md` et mets à jour `version.json`
   s'il est publié. Une nouvelle permission ESI va dans `SCOPES` (esi.py) et se signale dans les notes de patch.
1. **Toujours** lancer `python -m pytest -q` après une modification ; tous les tests doivent passer.
2. Toute nouvelle formule ou correction de formule = un test dans `tests/test_engine.py` avec la valeur attendue
   calculée à la main dans le commentaire.
3. Ne jamais inventer une valeur de jeu (bonus, taxe, ID) : la vérifier dans la doc CCP / le SDE / ESI,
   ou la rendre réglable dans `settings.py`.
4. En cas de casse ESI : lire le changelog (developers.eveonline.com/docs/services/esi), adapter la route,
   puis relever `COMPAT_DATE` (jamais une date future).
5. En cas de casse SDE : regarder le nouveau schéma (developers.eveonline.com/static-data/tranquility/schema-changelog.yaml)
   et adapter `SDE.from_zip_bytes`, en gardant la compatibilité des clés (`_key`, noms localisés).
6. Ne pas ajouter de dépendance lourde sans raison. Pas de framework front.
7. Finir par `python -m app.selfcheck` si le réseau est disponible.

## Distribution
- `construire_exe.bat` (Windows) ou `.github/workflows/build-windows.yml` (GitHub Actions) produisent `Cockpit.exe`.
- SSO en PKCE : aucun secret embarqué, un seul Client ID partagé par toute la corpo est la méthode prévue par CCP.
- Toute ressource statique ajoutée doit l'être via `--add-data` dans les deux scripts de build.

## Idées d'évolution (backlog)
- Statistiques de fit (DPS, EHP, cap) : intégrer un moteur dogma, ou un lien vers un outil tiers.
- Killboard de la corpo (pertes/kills récents, pilotes les plus actifs) via zKillboard.
- Préparation d'op : ping Discord généré depuis une commande de flotte.
- Utiliser les jobs en cours pour signaler les slots libres et les jobs prêts à livrer dans la Production.
- Prise en compte des slots de science pour l'ISK/heure des T2.
- Historique des prix (graphique 90 jours) au clic sur une opportunité.
- Jobs et blueprints de corporation (scopes corpo supplémentaires).
- Sauvegarde de plans nommés (ex. une doctrine de flotte).
