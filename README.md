# Cockpit

**Le copilote du capsulier** : doctrines et intel PvP, alarme de local, carte de la galaxie, industrie. Pour EVE Online, sur ton PC.

Outil PvP et industriel pour EVE Online qui tourne sur ton PC. Au premier lancement, la page **Comment ça marche** explique tout en deux minutes.

**PvP**
- **Doctrines & fits** : les fits de la corpo rangés par doctrine et par rôle, prix sur deux marchés, compétences manquantes et temps d'entraînement pour chacun de tes personnages, envoi des fits en jeu en un clic, commande de flotte (Multibuy, stock déduit, ou fabrication), rapport pour Discord.
- **Intel pilotes (bêta, verrouillé)** : stats zKillboard des pilotes du local. En cours de validation : ne pas s'en servir en fleet pour l'instant.
- **Carte de la galaxie** : portes, ponts de saut de l'alliance, Thera/Turnur (EVE-Scout), kills/sauts/ratting de la dernière heure, souveraineté, position de tes persos, itinéraires (court, sûr, sans high-sec), liens Dotlan et zKillboard, destination envoyée en jeu.
- **Alarme local & intel** : bip quand un neutre, orange ou rouge entre en local (surveillance de la zone d'écran de ta liste du local), ou quand un canal d'intel annonce un système surveillé (lecture des logs du jeu).
- **Analyse D-scan** : composition de la flotte adverse, ce qui est sur grille, valeur, alertes (bulles, cynos, capitaux, logi, recons…).

**Industrie**
- **Planétaire (PI)** : toutes les planètes et ressources P0 dans un rayon de sauts, ce que tu peux produire de P1 à P4 avec ce qu'il y a autour de toi (valeur et marge par heure), l'arbre complet P4 → P0 et les meilleurs systèmes pour chaque produit.
- **Plan de production** d'un ou plusieurs produits : arbre complet avec icônes, choix automatique de la meilleure structure, jobs dans l'ordre, liste d'achats à coller dans le Multibuy du jeu.
- **Comparaison de deux marchés** (Jita / C-N…) dans la liste d'achats, transport inclus.
- **Ton stock déduit automatiquement**, sur plusieurs personnages et comptes, hangars perso et corpo. Tes blueprints (ME/TE réels) et tes compétences sont pris en compte.
- **Invention T2** : les 8 décrypteurs comparés.
- **Opportunités** : tout ce qui est fabricable, classé par ISK/jour réaliste.
- **Arbitrage** entre les 5 hubs.
- **Jobs en cours** de tous tes personnages.
- Noms d'objets en français (ou anglais, allemand, russe), aide et lexique intégrés.

---

## Tu avais déjà l'outil sous son ancien nom (EVE Indy Planner) ?

Copie le dossier **`data`** de l'ancien dossier dans le nouveau dossier `cockpit` (ou à côté de `Cockpit.exe`) : tu gardes tes réglages, personnages connectés, doctrines et alarme. Ton application EVE (Client ID) ne change pas.

## Installer

### Option 1 — Le fichier .exe (le plus simple)

Si quelqu'un de ta corpo t'a donné `Cockpit.exe` :

1. Mets-le dans un dossier à toi (par exemple `Documents\Cockpit`), avec `distribution.json` à côté s'il t'a été fourni.
2. Double-clique. Ton navigateur s'ouvre sur l'outil.
3. Windows peut afficher « Windows a protégé votre ordinateur » : c'est normal pour un programme non signé. Clique sur **Informations complémentaires** puis **Exécuter quand même**.

### Option 2 — Depuis le dossier source

1. Double-clique **`lancer.bat`**. Si Python est absent, il l'installe tout seul (Windows 10/11), puis te demande de relancer.
2. La première fois, l'installation prend 1 à 2 minutes, puis l'outil s'ouvre sur http://localhost:8765.

Dans les deux cas, **un assistant de démarrage** te guide au premier lancement : langue, marché, structure, connexion des personnages. Les données du jeu (≈ 100 Mo) se téléchargent toutes seules la première fois et après chaque patch CCP.

Garde la petite fenêtre noire ouverte pendant que tu utilises l'outil ; ferme-la pour l'arrêter.

---

## Connecter tes personnages

L'assistant (étape 5) te guide pas à pas avec des boutons « Copier ». En résumé :

1. Va sur https://developers.eveonline.com/applications, puis **Create application**.
2. Callback URL : `http://localhost:8765/callback`
3. Coche les 19 permissions listées dans l'assistant (affichées en capsules, un clic copie le nom) :
   `esi-assets.read_assets.v1`, `esi-assets.read_corporation_assets.v1`, `esi-corporations.read_divisions.v1`,
   `esi-characters.read_blueprints.v1`, `esi-skills.read_skills.v1`, `esi-skills.read_skillqueue.v1`,
   `esi-universe.read_structures.v1`, `esi-markets.structure_markets.v1`, `esi-industry.read_character_jobs.v1`,
   `esi-fittings.read_fittings.v1`, `esi-fittings.write_fittings.v1`, `esi-characters.read_contacts.v1`,
   `esi-corporations.read_contacts.v1`, `esi-alliances.read_contacts.v1`, `esi-location.read_location.v1`,
   `esi-location.read_ship_type.v1`, `esi-ui.write_waypoint.v1`, `esi-search.search_structures.v1`, `esi-ui.open_window.v1`
4. Colle le **Client ID** dans l'outil. Le secret n'est pas nécessaire.
5. Clique **Connecter un personnage**.

**Plusieurs personnages** : autant que tu veux. Même compte : reclique sur « Ajouter un personnage » et choisis-en un autre sur la page EVE. Autre compte : bouton **Personnage d'un autre compte**, qui copie un lien à coller dans une fenêtre de navigation privée (le site EVE garde sinon le compte déjà connecté).

**Version 1.6** : ajoute `esi-ui.open_window.v1` (ouvrir la fiche d'un personnage dans le jeu, page de dons), puis reconnecte.

**Version 1.4.2** : ajoute `esi-search.search_structures.v1` (import des ponts de l'alliance depuis ton personnage), puis reconnecte.

**Version 1.4** : ajoute `esi-location.read_location.v1`, `esi-location.read_ship_type.v1` et `esi-ui.write_waypoint.v1` (carte : position des persos et destination en jeu), puis reconnecte.

**Version 1.3** : ajoute aussi `esi-characters.read_contacts.v1`, `esi-corporations.read_contacts.v1` et `esi-alliances.read_contacts.v1` (standings), puis reconnecte.

**Tu avais créé ton application avant la version 1.2 ?** Ajoute-lui les 3 nouvelles permissions (`esi-skills.read_skillqueue.v1`, `esi-fittings.read_fittings.v1`, `esi-fittings.write_fittings.v1`) sur developers.eveonline.com, puis reconnecte tes personnages. L'outil indique lesquels sont concernés.

**Si l'outil t'a été fourni préconfiguré par ta corpo, il n'y a que l'étape 5.**

Sécurité : les accès sont stockés uniquement sur ton PC (dossier `data`). L'outil **lit** tes données et peut **enregistrer des fits** dans ta liste de fittings quand tu le demandes. Il ne peut rien acheter, déplacer ni lancer en jeu. Tu peux révoquer l'accès à tout moment sur le site EVE (rubrique *Third Party Applications*).

---

## Partager avec ta corpo (pour le directeur ou la personne qui distribue)

Le principe : **une seule application EVE pour tout le monde**. Avec la méthode PKCE prévue par CCP pour les applications installées, le Client ID n'est pas un secret. Chaque membre lance l'outil sur son propre PC et connecte ses propres personnages ; personne ne voit les données des autres.

1. Crée l'application EVE une fois (voir ci-dessus).
2. Copie `distribution.example.json` en `distribution.json` et remplis-le :
   ```json
   {
     "corp_name": "Section XIII",
     "esi_client_id": "le Client ID de l'application",
     "price_market": "jita",
     "lang": "fr",
     "structures": []
   }
   ```
   Astuce : configure tes structures communes dans l'outil, puis copie la liste `structures` depuis `data/settings.json` vers `distribution.json`. Les membres les auront d'office.
3. Fabrique le `.exe`, au choix :
   - **Sur ton PC Windows** : double-clique `construire_exe.bat`, puis récupère `dist\Cockpit.exe`.
   - **Sans rien installer, via GitHub** : mets le dossier dans un dépôt GitHub (privé de préférence). Dans l'onglet **Actions**, choisis « Construire l'exe Windows » puis **Run workflow**. L'exe se télécharge en fin de construction, avec `distribution.json` s'il est dans le dépôt.
4. Partage `Cockpit.exe` et `distribution.json` (Discord, Google Drive…). Les membres les mettent dans le même dossier et double-cliquent.

### Récupérer les fits de corpo existants

ESI (l'API de CCP) ne permet pas de lire les fits de corporation : aucun outil tiers ne peut les récupérer directement. La méthode : les exporter en fichier depuis le jeu, puis les importer.

1. En jeu, ouvre la fenêtre Fitting, puis la gestion des fits (bouton pour parcourir les fits enregistrés), onglet **Corporation**.
2. Sélectionne les fits (Maj+clic ou Ctrl+clic) et utilise l'export vers un fichier. Le jeu écrit un fichier **.xml**, en général dans `Documents\EVE\fittings`.
   Si ton client ne propose pas l'export depuis l'onglet corpo : copie d'abord les fits voulus dans tes fits personnels, puis exporte-les depuis l'onglet personnel.
3. Dans l'outil : Doctrines & fits → **Importer des fits (fichier)**, ou glisse le fichier sur la page.
4. Choisis le mode :
   - **Une doctrine par préfixe** : si les fits sont nommés « [Vexor] DPS », « Vexor - Logi »… l'outil crée une doctrine par préfixe.
   - **Tout dans une nouvelle doctrine**.
   - **Ajouter à une de mes doctrines**.
5. Vérifie l'aperçu (rôle deviné, lignes non reconnues, doublons), puis **Importer**.

Le même import accepte aussi les fichiers XML de Pyfa, du texte EFT (plusieurs fits à la suite) et les exports de doctrines de l'outil. Réimporter le même fichier ne crée pas de doublons. Ensuite, exporte tes doctrines pour les publier comme doctrines officielles (ci-dessous).

### Doctrines officielles de la corpo

Deux façons de donner les mêmes doctrines à tous les membres :

- **Simple** : dans l'outil, Doctrines & fits → **Exporter mes doctrines**, puis partage le fichier `.json` ; chacun fait **Importer un fichier**.
- **Automatique (recommandé)** : publie ce fichier exporté dans ton dépôt GitHub sous le nom `doctrines.json`, et mets son adresse « raw » dans `distribution.json` (`doctrines_url`). Chaque membre reçoit alors les doctrines au démarrage, marquées **Corpo** et non modifiables (il peut les dupliquer pour faire sa variante). Pour changer une doctrine, tu remplaces le fichier sur GitHub : tout le monde est à jour au prochain lancement, sans nouvel exe.

### Patchs et mises à jour

Chaque version a un numéro (1.2.0…) et ses notes de patch, visibles dans l'outil (menu **Notes de patch**) et dans `CHANGELOG.md`. Après une mise à jour, un bandeau propose de voir les nouveautés.

Pour prévenir la corpo qu'une nouvelle version existe : publie un `version.json` (modèle : `version.example.json`) et mets son adresse dans `distribution.json` (`update_manifest_url`). Quand le numéro publié est plus récent que celui installé, chaque membre voit « Le patch X est disponible » avec le lien de téléchargement.

Les données et réglages (dossier `data`) sont conservés d'une version à l'autre : il suffit de remplacer l'exe (ou les fichiers du dossier).

Certains antivirus signalent à tort les exe faits avec PyInstaller. Si ça arrive, l'option 2 (`lancer.bat`) fonctionne toujours.

---

## Langues

L'interface est en **anglais par défaut**. Le sélecteur en bas du menu propose EN, FR, ES, DE et RU.
- Anglais et français : complets.
- Espagnol, allemand, russe : menus, titres et boutons ; le reste s'affiche en anglais.
- Les traductions sont dans `static/i18n-data.js` (clé = texte français) : pour traduire davantage, il suffit d'y ajouter des lignes.

## Soutenir Cockpit (dons en ISK)

Page « Soutenir Cockpit » dans l'outil : portrait du personnage **Robapin**, bouton « Copier le nom » et bouton « Ouvrir sa fiche dans mon jeu » (ouvre directement sa fiche dans ton client ; il reste à faire clic droit sur le portrait → Donner de l'argent). Le personnage destinataire se change avec `donate_character` dans `distribution.json`. Nouvelle permission : `esi-ui.open_window.v1`.

## Site de présentation

Le dossier `site/` contient un site complet en 5 langues (accueil, une page par fonction, téléchargement, dons) :
1. Ouvre `site/build.py` et renseigne `DOWNLOAD_URL`, `SOURCE_URL` et `SITE_URL` (et `DONATE_CHARACTER` si besoin).
2. `python site/build.py` génère le site dans `site/dist/`.
3. Publication : mets le projet sur GitHub, puis Settings → Pages → Source : GitHub Actions. Le workflow `publish-site.yml` publie le site à chaque modification du dossier `site/`.
4. Les captures d'écran sont dans `site/assets/` : remplace-les par de vraies captures de ton jeu (mêmes noms de fichiers) pour un rendu encore meilleur — les icônes des objets n'apparaissent pas sur celles fournies.

## Alarme local & intel

La page Alarme explique tout à l'écran avec des étapes qui se cochent. En résumé :

**Alarme local** — te prévient quand un rouge, orange ou neutre arrive dans ton système, sans regarder le local. Trois étapes :
1. Lance EVE et ouvre la fenêtre du local, en liste (affichage compact conseillé).
2. **Prendre la photo**, puis encadre à la souris **toute la fenêtre du local, partie vide comprise**. L'outil affiche aussitôt ce qu'il voit (« 2 rouges, 1 orange, 0 neutre, 12 bleus ») et entoure chaque icône reconnue : vérifie que ça correspond.
3. Coche ce qui doit sonner (rouges, oranges, neutres) et **Démarrer l'alarme**.

Les icônes sont reconnues automatiquement, comme le ferait ton œil : la couleur exacte du carré (rouge, orange, gris neutre, bleus), un carré plein, et le signe blanc au centre (« – », « = », « + »). Le texte en couleur (messages système rouges du local, noms) est ignoré. Les pilotes déjà présents au démarrage ne sonnent pas, seuls les nouveaux arrivants. Les bleus ne sonnent jamais.

À savoir :
- **Neutres** : ils doivent avoir une icône dans le local. Active l'étiquette des pilotes neutres / sans standing dans les réglages de l'overview (onglet Apparence). Un pilote sans aucune icône est invisible pour l'alarme.
- **Local très peuplé** : agrandis la fenêtre pour que tout le monde soit visible. Un pilote caché en bas de la liste n'est pas vu.
- **Thème d'interface inhabituel** : dans « Réglages avancés », clique sur une couleur puis sur une de tes icônes pour imposer la teinte exacte.
- Par défaut, l'alarme suit le client EVE sur lequel tu joues. Les Réglages avancés permettent de surveiller toujours le même personnage, tous tes clients (multi-compte), ou une zone fixe de l'écran.
- L'outil ne clique rien, ne lit pas la mémoire du jeu et n'envoie rien au client ; CCP ne valide cependant pas officiellement ce type d'outil.

**Alarme intel** — te prévient quand un système proche est cité dans un canal d'intel.
1. En jeu : Échap → Paramètres → Chat → enregistrer le chat dans un fichier, puis rejoins tes canaux.
2. **Chercher mes canaux**, coche tes canaux d'intel.
3. Systèmes à surveiller : « Autour de [ta base], N sauts » → **Ajouter ces systèmes**. Mots-clés facultatifs (cyno, bubble…).
4. Démarre : les derniers messages lus s'affichent, preuve que la lecture marche.

**Son** — sur le PC (même navigateur fermé) ou dans le navigateur, volume réglable, un son au choix pour chaque type d'alerte (sirène, klaxon, sonar, cloche…), bouton ▶ pour écouter.

## Carte de la galaxie

- **Où veux-tu aller ?** : tape un système, le départ est la position de ton personnage (ou ta base, ou un autre système), puis **Tracer**. Trois choix de chemin : le plus court, le plus sûr, sans high-sec.
- **Molette** pour zoomer, **glisser** pour se déplacer, **clic** sur un système pour sa fiche (accès, kills, souveraineté, persos présents, liens Dotlan et zKillboard, destination en jeu).
- **Couleurs** : sécurité, kills, capsules, sauts, ratting de la dernière heure, souveraineté (une couleur par alliance, légende cliquable). Sur les calques d'activité, plus le rond est gros, plus il y en a.
- **Où ça ratte** : les 15 systèmes les plus actifs de la dernière heure à 5, 10 ou 15 sauts de ton personnage (ratting, kills ou trafic selon les couleurs choisies), pour savoir où chasser.
- **Itinéraire** : le plus court, le plus sûr, ou en évitant le high-sec ; systèmes à éviter ; ponts de saut ; Thera/Turnur. Le pilote automatique du jeu ne prend ni ponts ni trous de ver : suis la liste affichée.
- **Ponts de saut** : « Importer depuis mes personnages » lit les ponts Ansiblex auxquels ton personnage a accès (il doit être sur la liste d'accès des ponts de l'alliance). Sinon, colle la liste de ton alliance (« 1DQ1-A » T5ZI-S », une ligne par pont). Une corpo peut la fournir à tous via `distribution.json` (clé `map` → `jb_text` et `jump_bridges`).
- **Thera / Turnur** : données EVE-Scout (Signal Cartel), mises à jour par des volontaires.

## Configurer tes structures

Dans l'onglet **Structures**, ajoute chaque structure où tu produis : type, système, taxe et rigs. Pour les rigs, entre les valeurs de base (T1 : 2 % / 20 %, T2 : 2,4 % / 24 %) ; le bonus lowsec (×1,9) et nullsec/WH (×2,1) est appliqué automatiquement. Pour chaque job, l'outil prend la structure la moins chère.

Pour lire le marché d'une citadelle (C-N…), va dans **Réglages**, rubrique **Marchés de citadelle**. Il faut un personnage qui a accès à ce marché.

---

## Vérifier que tout fonctionne

Double-clique **`verifier.bat`**. Il lance les tests du moteur, puis vérifie en conditions réelles les données CCP, l'API, les prix et la cohérence d'un calcul complet (Raven et Hammerhead II comparés aux prix de Jita). Il te dit précisément ce qui ne va pas.

## D'où viennent les données

| Donnée | Source | Rafraîchissement |
|---|---|---|
| Objets, blueprints, noms traduits | SDE officiel CCP (developers.eveonline.com/static-data) | Vérifié à chaque lancement |
| Icônes et portraits | images.evetech.net (CCP) | Chargés par le navigateur |
| Prix ajustés, indices de coût | ESI (esi.evetech.net) | 1 h |
| Prix des hubs | market.fuzzwork.co.uk, avec repli automatique sur ESI | 15 min |
| Marché de citadelle, stock, jobs, blueprints, compétences | ESI avec connexion | 10 min ou à la demande |
| Volume vendu par jour | Historique ESI | 12 h |
| Statistiques des pilotes (intel) | zKillboard | 1 h |
| Compétences requises, slots | SDE CCP (dogma) | Avec les données du jeu |
| Carte (systèmes, portes) | SDE CCP | Avec les données du jeu |
| Kills, sauts, ratting par système | ESI (mis à jour par CCP chaque heure) | 10 min |
| Souveraineté | ESI | 1 h |
| Connexions Thera / Turnur | EVE-Scout | 5 min |

## Limites à connaître

- **Taxes** : vente, courtage et surtaxe SCC (4 % par défaut) sont à vérifier dans ton jeu, car elles changent directement la marge.
- **Catégories de rigs** : le rattachement d'un produit à une catégorie (petits vaisseaux T1, équipement…) est approximé par groupe d'objet. Si un résultat paraît faux, règle le rig sur « Tout ».
- **Invention** : le calcul suppose que tu as le BPO T1. Le temps d'invention n'entre pas dans l'ISK/heure.
- **Statistiques des fits** : l'outil ne calcule pas DPS, tank ou capaciteur (il faudrait réimplémenter le moteur de Pyfa). Utilise « Copier le fit (EFT, pour Pyfa) » pour ça.
- **Alarme écran** : sous Windows elle capture la fenêtre EVE même partiellement recouverte ; si ta carte graphique renvoie une image noire, elle se rabat sur la capture d'écran classique (la fenêtre doit alors être visible). Une fenêtre réduite n'est pas surveillée. Une liste du local trop petite (pilotes hors de la zone visible), une fenêtre recouverte, ou deux couleurs d'icônes trop proches donnent des alertes manquées ou en trop : règle la tolérance.
- **Intel** : la dangerosité vient de zKillboard. Un pilote qui ne tue jamais (cyno, éclaireur) apparaît « faible » mais peut être la vraie menace.
- **Temps d'entraînement** : calculé pour un compte Oméga, avec les attributs actuels (implants inclus) ; un remap ou des implants changent le résultat.
- **Arbitrage** : la quantité « dispo » compte tous les ordres, pas seulement ceux au meilleur prix. Regarde la profondeur du carnet en jeu avant d'acheter gros.

## Faire évoluer l'outil

Voir `CLAUDE.md` : ouvre le dossier avec Claude Code, demande l'évolution voulue (ou colle le rapport de `verifier.bat` si CCP a changé quelque chose). Le fichier lui donne l'architecture et l'oblige à repasser les tests.
