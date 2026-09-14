# Suivi des temps et dépenses

Application multi-projet de suivi des heures, des dépenses techniques et des pièces
justificatives, destinée à produire des récapitulatifs défendables devant un financeur.
Elle sépare explicitement ce qui est mesuré de ce qui est estimé, et signale les zones
grises avant transmission plutôt que de les lisser.

## Ce que couvre l'outil

Le temps passé est saisi ligne par ligne, une ligne correspondant au temps d'une seule
personne sur une seule séance. Chaque ligne porte une date, des horaires ou une durée
forfaitaire, un type de tâche, un livrable de rattachement, une part imputable au projet,
une source de trace et un statut de durée. Les dépenses techniques suivent la même logique :
catégorie, élément technique, quantité, unité, coût unitaire, statut du montant et référence
du justificatif.

Chaque projet dispose de son propre référentiel de types de tâche, de catégories de dépense
et d'acteurs. Créer un second projet n'emprunte rien au premier.

## Comptes et droits

Un compte peut être administrateur ou utilisateur ordinaire. L'administration gère les
comptes, les projets et les accès, et dispose d'une synthèse de tous les projets.

Sur chaque projet, un compte reçoit l'un des trois rôles suivants. Le gestionnaire voit et
modifie l'ensemble du projet, y compris les taux horaires et les référentiels. Le
contributeur ne voit et ne modifie que les lignes de la personne à laquelle il est rattaché,
et n'accède ni aux coûts des autres acteurs ni aux dépenses qu'il n'a pas engagées ; il
dispose en revanche de la synthèse de son propre périmètre et de son tableau de bord
individuel. Le lecteur consulte l'ensemble du projet sans rien modifier, ce qui convient à
un auditeur ou à un contrôleur.

Un contributeur doit obligatoirement être rattaché à un acteur du projet : sans ce
rattachement il ne verrait aucune ligne, et l'API refuse l'accès plutôt que de créer un
compte muet.

L'authentification repose sur un mot de passe haché par scrypt et sur une session signée
HMAC déposée dans un cookie httpOnly. Aucune bibliothèque externe n'intervient. Les mots de
passe créés depuis l'administration sont provisoires et affichés une seule fois, et leur
titulaire doit les remplacer à la première connexion.

## Règle de report des séances récurrentes

Une règle de récurrence matérialise une séance par mois sur une fenêtre donnée, par exemple
le premier lundi de chaque mois. Quand la date théorique tombe un jour férié, un week-end ou
une journée où la personne a déjà une autre ligne de temps, la séance glisse au premier jour
ouvrable libre. Un samedi renvoie au lundi, donc au premier jour ouvrable de la semaine
suivante. Le décalage est itératif : si le jour d'arrivée est lui-même férié ou occupé, la
recherche continue, dans la limite de trois semaines au-delà de laquelle la séance reste à sa
date théorique avec une note d'arbitrage. Plusieurs journées dans une même semaine sont
admises, seul le cumul de deux séances le même jour est écarté.

Le calendrier retenu est celui des onze jours fériés légaux français, fêtes mobiles
comprises : le dimanche de Pâques est calculé par l'algorithme grégorien anonyme, d'où
découlent le lundi de Pâques, l'Ascension et le lundi de Pentecôte. Une règle peut désactiver
le report.

La date théorique est conservée à côté de la date retenue et sert de clé d'idempotence :
regénérer une règle ne recrée jamais une séance déjà reportée à son point de départ.
Modifier une règle la rejoue intégralement, puisque le jour, le rang, la fenêtre et le report
peuvent tous déplacer les séances.

## Tableaux de bord

Trois sorties sont proposées depuis l'onglet des réglages. Le tableau individuel présente
l'effort d'un seul acteur. Le consolidé expose tous les acteurs et sert de pièce de remise au
financeur. La liasse rassemble en une archive le consolidé et un tableau par acteur ayant
déclaré du temps.

Ces fichiers sont des HTML autonomes : aucune feuille de style distante, aucun script, aucun
appel réseau, graphiques en SVG inline. Ils s'ouvrent hors ligne et s'impriment en PDF depuis
le navigateur. Chacun porte un anneau de répartition de l'effort, un histogramme mensuel
empilé par type de tâche, et pour le consolidé un plan de charge comparant les acteurs. Les
exports tabulaires restent disponibles au format CSV point-virgule avec BOM, lisibles
directement dans Excel en français.

## Direction visuelle

Fond gris clair, cartes blanches arrondies à ombre douce, palette saturée à cinq teintes
(bleu, vert, jaune, rouge, violet) reprise des pastilles de statut, avatars à initiales pour
les acteurs, grands nombres pour les totaux. Les couleurs ne portent jamais seules une
information : chaque pastille est légendée, chaque graphique doublé d'un tableau chiffré.

## En cas d'erreur 500

### Savoir quelle version tourne

Le démarrage écrit un bandeau dans les journaux :

```
Suivi des temps et dépenses, version 2.3.1, révision tableau-doublons-r6
```

Si ce bandeau n'apparaît pas, le service exécute encore une version antérieure et le
redéploiement n'a pas pris.

### Mise à niveau de la base

Les colonnes à ajouter ne sont plus listées à la main : elles sont déduites de
`Base.metadata`, donc toute colonne ajoutée au modèle est migrée d'office. Chaque ordre
`ALTER TABLE` a sa propre transaction, pour qu'un échec isolé n'annule pas les autres, ce
que Postgres ferait dans une transaction commune. Une colonne non nulle reprend le défaut
déclaré sur le modèle pour les lignes déjà en base ; sans défaut, elle est ajoutée nullable
plutôt que de faire échouer la migration.

Les journaux montrent le résultat, ligne par ligne :

```
Migration : colonne activites.origine_estimee ajoutée.
Schéma vérifié : toutes les colonnes attendues sont présentes.
```

Si un écart subsiste, il est nommé explicitement et `migration_manuelle.sql` s'exécute tel
quel dans la console Postgres de Railway pour le combler.

### Contrôles avant déploiement

== compilation ==
== doublons de définitions ==
  aucun
== routes en double ==
  aucune
== migration deduite du modele, pas d une liste a la main ==
  ok
== cohérence modèle, API et interface ==
ok     sérialisation d'un projet
ok     sérialisation d'un type
ok     sérialisation d'une personne
ok     sérialisation des lignes de temps
ok     sérialisation des dépenses
ok     sérialisation d'une récurrence
ok     contrôles de cohérence
ok     la validation reste distinguée de la mesure
ok     regroupement des recouvrements
ok     pas de faux positif sur les recouvrements

Tous les contrôles passent.
== interface : execution des fonctions de rendu ==
  ok     remplirSelects
  ok     rendreEntete
  ok     rendreRecap
  ok     rendreTemps
  ok     rendreDoublons
  ok     rendreBandeauValidation
  ok     rendreRec
  ok     rendreDep
  ok     rendrePers
  ok     rendreReglages
  ok     rendre (enchaînement complet)
  ok     resetAct
  ok     resetDep
  ok     resetPers
  ok     resetRec
  ok     rendreAdmin
  ok     litAct
  ok     litDep
  ok     litRec
  ok     la table contient les lignes et signale le recouvrement
  ok     le panneau d'arbitrage propose de retenir une ligne
  
  Toutes les fonctions de rendu s'exécutent.
== interface : identifiants et équilibrage ==
  ok

Tous les contrôles passent. enchaîne la compilation, la recherche de définitions et de routes en double,
la cohérence entre le modèle, l'API et l'interface, l'exécution de toutes les fonctions de
rendu de la page dans un DOM factice sous Node, puis l'équilibrage du JavaScript et la
présence des identifiants du DOM. Aucune base ni dépendance installée n'est requise.

Avant chaque déploiement, `./verifier.sh` enchaîne la compilation, la recherche de
définitions et de routes en double, la cohérence entre le modèle, l'API et l'interface, puis
l'équilibrage du JavaScript et la présence des identifiants du DOM. Ces contrôles tournent
sans base de données ni dépendance installée.

## Recouvrements

Deux lignes qui se chevauchent pour une même personne le même jour ne peuvent pas être
imputées toutes les deux. Le regroupement est transitif : trois entrées qui se recouvrent en
chaîne forment un seul groupe, pas deux. Les trois enregistrements du comité du 10 juin
cumulent ainsi 10,25 heures pour une demi-journée de 4,25 heures, soit six heures comptées en
trop.

L'onglet du temps passé affiche ces groupes en tête, avant la table, avec pour chaque ligne un
bouton qui la retient. Retenir une ligne ramène les autres à zéro pour cent d'imputation sans
les effacer : la réunion reste au dossier, elle sort du total, et une note datée et signée
consigne l'arbitrage sur chaque ligne concernée. La suppression définitive reste offerte pour
les scories d'agenda qui n'ont aucune valeur de preuve. Les lignes en recouvrement sont
surlignées dans la table, les lignes neutralisées apparaissent barrées et estompées, et deux
filtres permettent de n'afficher que les unes ou les autres.

## Validation des durées estimées

Une durée peut être relevée ou estimée. Le pilotage du projet, gestionnaire ou
administrateur, peut valider une estimation : elle bascule alors en durée retenue et compte
dans les totaux fermes. La bascule n'est jamais anonyme, l'identité du valideur et
l'horodatage sont enregistrés et apparaissent dans l'interface, dans les exports CSV et sur
le tableau de bord, sous la forme d'une mention datée à côté de la ligne.

La validation en masse porte sur les lignes actuellement affichées, filtres compris, de sorte
que la sélection soit celle que l'écran montre et non un lot invisible. Les lignes sans durée
sont écartées et signalées plutôt que validées à vide : valider zéro heure ne produirait aucune
information et brouillerait le compte. La dévalidation restitue le statut estimé et efface la
trace, et modifier manuellement une ligne pour la repasser en estimée annule sa validation.

Une réserve dédiée rappelle dans chaque récapitulatif combien d'heures retenues proviennent
d'une estimation validée, et par qui. Une estimation validée n'est pas un relevé horaire :
l'outil rend cette distinction visible plutôt que de la dissoudre dans un total unique.

## Artefacts du tableau de bord

Onze blocs composent les tableaux exportés : bandeau d'indicateurs, grand total engagé, anneau
de répartition par type de tâche, histogramme mensuel empilé, vue d'ensemble par statut de
durée, chronologie d'engagement des acteurs, tableau par type, plan de charge et tableau par
acteur, tableau des dépenses, détail des lignes et points à arbitrer. Le pilotage coche ceux
qu'il retient depuis l'onglet des réglages ; le choix est enregistré sur le projet et
s'applique au tableau individuel, au consolidé et à la liasse. Un paramètre d'URL `artefacts`
permet de produire ponctuellement une variante sans modifier le réglage.

La vue par statut range les lignes en quatre colonnes colorées, durées relevées, estimations
validées, estimations en attente et lignes à arbitrer, chacune avec son compte et son total
d'heures. La chronologie trace une piste par acteur de sa première à sa dernière ligne
déclarée, ponctuée des journées effectivement saisies.

## Contrôles automatiques

Le récapitulatif signale les chevauchements horaires pour une même personne, les séances
récurrentes coïncidant avec une réunion déjà tracée le même jour, les sessions à objet mixte
encore imputées à cent pour cent, les lignes sans durée, les taux horaires manquants, les
dépenses sans quantité ni tarif, les dépenses chiffrées sans justificatif, les estimations en
attente de validation, les heures retenues issues d'une estimation validée, les journées issues
d'un régime déclaré, les lignes tombant un jour férié et les séances effectivement reportées.
Ces réserves accompagnent les tableaux de bord exportés plutôt que d'en être retranchées.

## Déploiement sur Railway

1. Créer un projet Railway et y ajouter un service Postgres, ce qui renseigne `DATABASE_URL`.
2. Définir `SECRET_KEY` avec une chaîne aléatoire longue. Sans elle, une clé éphémère est
   générée à chaque démarrage et toutes les sessions tombent au redéploiement.
3. Définir `ADMIN_EMAIL`, et éventuellement `ADMIN_MOTDEPASSE`. À défaut, un mot de passe
   provisoire est généré au premier démarrage et affiché dans les journaux de déploiement.
4. Connecter le dépôt. Nixpacks détecte `requirements.txt`. La commande de démarrage figure
   dans `Procfile` et dans `railway.json`, la route de contrôle de santé est `/api/sante`.
5. Au premier démarrage, les tables sont créées, le compte d'administration est établi et le
   projet DEXTER4LLM est amorcé avec son contenu reconstitué. Un démarrage ultérieur sur une
   base déjà remplie n'écrase rien, et le mot de passe administrateur n'est jamais réécrit.

Variables facultatives : `COOKIE_SECURE=0` derrière un proxy sans HTTPS, `AUTORISER_REINIT=0`
pour verrouiller la réinitialisation une fois la saisie réelle engagée,
`DUREE_SESSION_HEURES` pour la durée des sessions.

La version multi-projet introduit un schéma nouveau. Sur une base issue de la version
précédente, lancez un démarrage unique avec `REINIT_SCHEMA=1` pour supprimer et recréer les
tables, puis retirez la variable. Cette opération est destructive.

## Exécution locale

```
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
COOKIE_SECURE=0 uvicorn app.main:app --reload
```

Sans `DATABASE_URL`, un fichier SQLite `dexter_suivi.db` est créé dans le répertoire courant.
L'interface est servie sur `http://127.0.0.1:8000/` et la documentation interactive de l'API
sur `/docs`.

## Jeu initial du projet DEXTER4LLM

Vingt-cinq séances reconstituées à partir de l'agenda de janvier à septembre 2026, avec
horaires et durées calculées. Une ligne supplémentaire pour la trace du 14 novembre 2025, sans
durée puisque la source ne la donne pas. Dix-sept acteurs issus des invitations. Sept lignes de
dépenses techniques amorcées avec leur unité mais sans quantité ni tarif, à renseigner depuis
les relevés réels. Deux règles de récurrence correspondant au régime déclaré : premier lundi de
chaque mois de juin 2025 à février 2026, puis premier vendredi de mars à septembre 2026, soit
seize séances de sept heures dont trois reportées.

## Modèle de données

`utilisateurs` porte les comptes, `projets` les projets et leurs paramètres, `acces` le
triplet compte, projet et rôle avec le rattachement facultatif à un acteur. `types_tache`,
`categories_depense`, `personnes`, `recurrences`, `activites` et `depenses` sont toutes
rattachées à un projet par clé étrangère avec suppression en cascade. `activites.valide_le` et
`activites.valide_par_id` portent la trace de validation, `projets.artefacts_tableau` la
sélection de blocs du tableau de bord. Les heures, les heures
imputées, les coûts et les montants sont calculés et jamais stockés, ce qui évite toute dérive
entre une valeur enregistrée et ses composantes.

## API

Les routes de projet sont préfixées par `/api/projets/{id}`. Elles couvrent l'état complet,
le récapitulatif, les lignes de temps, les dépenses, les acteurs, les récurrences, les
référentiels et les exports. Les routes d'administration sont préfixées par `/api/admin` et
couvrent les comptes, les projets, les accès et la synthèse inter-projets. Les routes
d'authentification sont `/api/connexion`, `/api/deconnexion`, `/api/moi` et
`/api/moi/mot-de-passe`.
