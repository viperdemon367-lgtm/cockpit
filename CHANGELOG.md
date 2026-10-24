Notes de patch — Cockpit
Fichier généré depuis `app/version.py` (source unique, aussi affichée dans l'outil). Avant la version 1.5.0, l'outil s'appelait EVE Indy Planner.
Patch 1.6.2 — Site correctement traduit et publication automatique (2026-10-24)
Les captures du site s'affichent maintenant dans la langue de la page ; publication automatique de l'exe à chaque modification du programme.
Nouveautés
Site : système de captures d'écran par langue (site/assets/<langue>/), avec repli sur l'anglais quand une capture n'existe pas encore dans une langue donnée.
Captures en français ajoutées pour toutes les pages de fonctions.
Publication de l'exe automatique : le workflow se relance tout seul à chaque modification de app/, static/, tests/, run.py ou requirements.txt sur la branche main. Plus besoin de cliquer « Run workflow » à chaque mise à jour.
Améliorations
README : marche à suivre pour les mises à jour (sans manipulation GitHub/Cloudflare une fois configuré) et pour brancher un nom de domaine personnalisé, acheté chez Cloudflare ou ailleurs.
Patch 1.6.1 — Mise en ligne simplifiée (2026-10-24)
Publication automatique de Cockpit.exe sur GitHub, et guide pas à pas pour mettre le site en ligne gratuitement sur Cloudflare Pages avec ton propre nom de domaine.
Nouveautés
Nouveau workflow « Publier une version » : construit Cockpit.exe sous Windows et le publie en Release GitHub, à une adresse de téléchargement stable qui ne change jamais entre deux versions.
README : guide complet pour mettre le projet sur GitHub, publier l'exe automatiquement, héberger le site gratuitement sur Cloudflare Pages, et brancher un nom de domaine personnalisé.
Améliorations
site/build.py : les adresses de téléchargement et du dépôt se déduisent maintenant d'un seul réglage (GITHUB_REPO) à renseigner.
Patch 1.6.0 — Planétaire, multilingue et dons (2026-10-23)
Nouvelle section Planétaire (P0 → P4), interface en anglais par défaut avec 5 langues, page de dons et site de présentation.
Nouveautés
Planétaire (PI) : toutes les planètes et ressources P0 dans un rayon de sauts autour de ton personnage, de ta base ou d'un système ; produits P1 à P4 faisables à 100 % avec les ressources du rayon, avec prix et marge par heure ; arbre de production complet P4 → P0 avec quantités et types de planètes ; meilleurs systèmes pour chaque produit ; détail des planètes de chaque système.
Langues : interface en anglais par défaut, sélecteur EN / FR / ES / DE / RU en bas du menu. Anglais et français complets ; espagnol, allemand et russe pour les menus, titres et boutons (le reste s'affiche en anglais).
Soutenir Cockpit : page de don en ISK au personnage Robapin, avec bouton qui ouvre directement sa fiche dans ton jeu (nouvelle permission esi-ui.open_window.v1).
Site de présentation : accueil, une page par fonction, téléchargement et dons, en 5 langues, prêt à publier sur GitHub Pages.
Améliorations
Les données du jeu se retéléchargent une fois pour inclure les planètes et les schémas planétaires.
Patch 1.5.1 — Carte pour les chasseurs (2026-10-23)
Une couleur par alliance, des ronds qui montrent où ça ratte, des ponts animés ; l'intel pilotes passe en bêta.
Nouveautés
Carte : liste « Où ça ratte » (ou « Où ça se bat », « Où ça passe » selon les couleurs choisies) : les 15 systèmes les plus actifs de la dernière heure à 5, 10 ou 15 sauts de ton personnage, avec les kills et la distance en sauts.
Carte : légende de souveraineté avec le nombre de systèmes par alliance ; un clic met une alliance en évidence.
Améliorations
Souveraineté : une couleur bien distincte par alliance (les plus grandes ont les couleurs les plus contrastées) ; lecture tolérante des formats ESI, avec un message clair si CCP ne renvoie rien.
Calques d'activité : la taille du rond est proportionnelle à l'activité (ratting, kills, capsules, trafic) ; les systèmes les plus actifs sont dessinés au-dessus.
Ponts de saut : traits lumineux et animés, avec une étincelle qui parcourt chaque pont.
Carte plus légère : seule l'animation des ponts est recalculée en continu.
À l'ouverture, la carte cadre ton voisinage (6 sauts autour de ton personnage).
Intel pilotes : déplacé dans la section Bêta et verrouillé par défaut, en attendant d'être validé.
Patch 1.5.0 — L'outil devient Cockpit (2026-10-23)
Nouveau nom, et une alarme de local qui reconnaît les neutres quelle que soit la teinte de ton interface.
Nouveautés
Nouveau nom : Cockpit, le copilote du capsulier (PvP, intel, carte, industrie). L'exécutable s'appelle désormais Cockpit.exe.
Améliorations
Alarme local : les icônes sont reconnues par leur forme (carré plein, signe blanc au centre) et classées par famille de couleur. Un neutre plus sombre que prévu (transparence des fenêtres, taille d'interface) est maintenant détecté. Vérifié sur une capture réelle avec un neutre dans le local et du texte rouge partout.
Mise à jour depuis l'ancienne version : copie ton dossier « data » dans le dossier de Cockpit pour garder tes réglages.
Patch 1.4.2 — Alarme fiable et carte plus simple (2026-10-23)
L'alarme ne réagit plus au texte rouge du chat ; la carte part de la position de ton personnage et importe les ponts de l'alliance.
Nouveautés
Ponts de saut : bouton « Importer depuis mes personnages » qui lit les ponts Ansiblex auxquels ton personnage a accès (nouvelle permission de recherche de structures).
Carte : barre « Où veux-tu aller ? » ; le départ est proposé automatiquement (position de chaque personnage, ta base, ou un autre système) ; bouton « M'y emmener » sur chaque système.
Carte : ouverture centrée sur ton personnage, bouton « 📍 Moi », la carte se cadre sur le trajet tracé.
Améliorations
Alarme local : reconnaissance des vraies icônes de standing du jeu (couleur exacte du carré, carré plein, signe blanc au centre). Le texte rouge des messages système du local n'est plus confondu avec un rouge. Vérifié sur des captures réelles du client.
Carte : options (ponts, Thera, systèmes à éviter, affichage) rangées dans des menus ; résumé du trajet en une ligne ; « Destination en jeu » choisit le personnage du départ.
Souveraineté : prise en charge de la nouvelle route ESI de CCP.
Patch 1.4.1 — Alarme local simplifiée (2026-10-23)
L'alarme reconnaît toute seule les icônes rouges, oranges et neutres : il suffit d'encadrer le local une fois.
Nouveautés
Détection automatique des icônes de standing : l'outil repère les petites icônes carrées et les classe par couleur (rouge, orange, neutre, bleu ignoré), sans avoir à cliquer sur chaque couleur.
Après l'encadrement, l'outil affiche ce qu'il voit (« 2 rouges, 1 orange, 0 neutre, 12 bleus ») et entoure chaque icône reconnue sur la photo.
Choix simple de ce qui doit sonner : rouges, oranges, neutres.
Alertes exactes : « 1 rouge vient d'arriver », « 2 oranges viennent d'arriver ».
Améliorations
Configuration en 3 étapes : lancer EVE, prendre la photo et encadrer le local, démarrer. La fenêtre EVE à photographier est choisie automatiquement.
Le choix manuel des couleurs, le mode multi-compte et la zone fixe passent dans « Réglages avancés ».
Patch 1.4.0 — Carte de la galaxie et alarme repensée (2026-10-23)
Nouvelle carte de New Eden avec itinéraires et Dotlan ; alarme qui suit ta fenêtre EVE, sons au choix et volume réglable.
Nouveautés
Carte de la galaxie : tous les systèmes et toutes les portes de New Eden, zoom et déplacement, recherche, filtre par région.
Calques : sécurité, kills et capsules de la dernière heure, sauts, PNJ tués (ratting), souveraineté.
Fiche système : accès (portes et ponts), activité, propriétaire, personnages présents, liens Dotlan (système et carte de région) et zKillboard.
Itinéraires : le plus court, le plus sûr ou en évitant le high-sec, systèmes à éviter, ponts de saut de l'alliance, passage par Thera/Turnur ; kills sur le trajet ; lien Dotlan ; destination envoyée en jeu.
Connexions Thera et Turnur en direct (EVE-Scout).
Position et vaisseau de tes personnages sur la carte ; système de base.
Alarme local : suit la fenêtre EVE sur laquelle tu joues (ou un personnage précis, ou toutes tes fenêtres en multi-compte), même si la fenêtre change de place ; capture possible même quand la fenêtre est partiellement recouverte.
Alarme : 7 sons au choix par type d'alerte (rouge, orange, neutre, intel), volume réglable, écoute avant choix.
Alarme : bouton « Tester la détection maintenant » qui compte les icônes visibles.
Alarme intel : ajout en un clic de tous les systèmes à N sauts de ta base ; affichage des derniers messages lus pour vérifier que la lecture fonctionne.
Doctrines : guide pas à pas « Comment importer les fits de la corpo ».
Améliorations
Page Alarme réécrite : à quoi sert chaque alarme, étapes numérotées qui se cochent quand elles sont faites.
Trois nouvelles permissions EVE : position, vaisseau actuel, et définition de la destination en jeu. Ajoute-les à ton application EVE et reconnecte tes personnages.
Les données du jeu se retéléchargent une fois pour inclure la carte.
Patch 1.3.1 — Import des fits de corpo (2026-10-23)
Import en une fois d'un fichier de fits (XML du jeu ou de Pyfa, EFT, export de doctrines).
Nouveautés
Import de fichier de fits : XML exporté depuis la fenêtre de gestion des fits du jeu ou depuis Pyfa, texte EFT avec plusieurs fits, ou export de doctrines. Glisser-déposer accepté sur la page Doctrines.
Aperçu avant import : doctrine de destination, rôle, nombre de modules, lignes non reconnues, doublons.
Trois modes : une doctrine par préfixe (« [Vexor] DPS » ou « Vexor - Logi » → doctrine Vexor), tout dans une nouvelle doctrine, ou ajout à une doctrine existante.
Rôle deviné automatiquement : d'abord le nom du fit (logi, tackle, ewar, boost, scout…), sinon le type de vaisseau.
Les fits déjà présents (même vaisseau, mêmes modules) sont ignorés : on peut réimporter sans créer de doublons.
Améliorations
ESI ne donne pas accès aux fits de corporation (limite de CCP) : l'export de fichier depuis le jeu est la méthode pour les récupérer en masse.
Patch 1.3.0 — Alarme et standings (2026-10-23)
Bip quand un neutre, orange ou rouge entre en local ; standings réels dans l'intel ; choix du niveau de fabrication.
Nouveautés
Alarme local : l'outil surveille la zone de l'écran où se trouve ta liste du local et sonne quand une icône rouge, orange ou neutre apparaît. Tu choisis la zone à la souris et les couleurs en cliquant sur tes propres icônes ; la taille d'une icône est mesurée pour annoncer « 1 nouveau », « 2 nouveaux »…
Alarme intel : lecture des logs de tes canaux d'intel ; bip rouge quand un système surveillé est annoncé, orange pour un mot-clé (cyno, bubble…). Les « clr » sont ignorés.
Bip sur le PC (même navigateur fermé), son et notification dans le navigateur, journal des alertes.
Intel pilotes : tes vrais standings (personnels, corpo, alliance) colorent chaque pilote comme en jeu : rouge, orange, neutre, bleu.
Production : choix du niveau de fabrication (« jusqu'au niveau 1, 2, 3… », tout le reste est acheté), et bouton en haut de chaque colonne de l'arbre pour acheter ou fabriquer tout un niveau.
Améliorations
Trois nouvelles permissions EVE pour lire les contacts (perso, corpo, alliance) : ajoute-les à ton application EVE et reconnecte tes personnages.
Patch 1.2.0 — Patch PvP (2026-10-22)
Arrivée du module PvP : doctrines et fits de corpo, intel pilotes, analyse D-scan.
Nouveautés
Doctrines et fits : import au format EFT (copier-coller depuis le jeu ou Pyfa), plusieurs fits d'un coup, classement par rôle (DPS, logi, tackle…), prix du fit sur deux marchés.
Import des fits enregistrés en jeu et envoi d'un fit de doctrine dans la liste de fittings d'un personnage, en un clic.
« Qui peut voler quoi » : pour chaque personnage connecté, compétences manquantes et temps d'entraînement par fit, en tenant compte de la file d'entraînement. Liste des compétences manquantes copiable.
Commande de flotte : quantité par fit, liste d'achats totale (Multibuy), déduction du stock, envoi des coques et modules fabricables vers la Production.
Rapport de doctrine à coller sur Discord.
Doctrines officielles de corpo : fournies par distribution.json ou par un lien (mise à jour automatique pour tous les membres), export et import en un fichier.
Intel pilotes : colle la liste du local, regroupement par alliance et corpo, statistiques zKillboard (kills, pertes, dangerosité, solo/gang, vaisseaux favoris, activité récente).
Analyse D-scan : composition de la flotte adverse par classe, valeur estimée, alertes (bulles, cynos, capitaux, logistique, recons…).
Page « Comment ça marche » pour comprendre l'outil en deux minutes.
Notes de patch (cette page) et alerte de mise à jour disponible si la corpo publie une nouvelle version.
Améliorations
Permissions EVE affichées en capsules lisibles. Trois nouvelles permissions (compétences en file, lecture et écriture des fittings) : reconnecte tes personnages, l'outil indique lesquels.
Personnages : ajout simplifié de personnages sur plusieurs comptes EVE, corpo et alliance affichées, état de chaque connexion.
Menu réorganisé en sections : Prise en main, PvP, Industrie, Compte.
Patch 1.1.0 — Accessibilité (2026-10-22)
Icônes, français, assistant de démarrage et version .exe partageable en corpo.
Nouveautés
Icônes officielles des objets, blueprints et portraits des personnages.
Noms d'objets en français (ou anglais, allemand, russe) ; recherche dans les deux langues.
Assistant de démarrage pas à pas.
Plan de production de plusieurs produits à la fois.
Onglet « Mes jobs en cours ».
Aide intégrée et lexique.
Version .exe et configuration de corpo partagée (distribution.json).
Améliorations
Le stock ignore les modules montés et les vaisseaux assemblés ; noms réels des emplacements.
Patch 1.0.0 — Première version (2026-10-22)
Planificateur de production, invention, opportunités et arbitrage.
Nouveautés
Arbre de production complet, choix de la meilleure structure, liste d'achats Multibuy.
Comparaison de deux marchés, déduction du stock, invention avec décrypteurs.
Scan des opportunités industrielles et arbitrage entre hubs.
