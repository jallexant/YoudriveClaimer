# YouDrive Claimer

Application locale Windows, Python 3.12+ et SQLite. La collecte lit l'historique
de trajets par l'API de l'application Android officielle, depuis le PC, sans
téléphone et sans USB. La connexion s'ouvre dans le navigateur seulement quand
la session locale n'est plus valable. Aucun email ni accès Gmail.

## Portée

`sync` demande la liste complète des trajets du contrat, avec les points
d'intérêt. Cette liste n'a pas de paramètre de page : une réponse qui annonce
une suite interrompt l'import au lieu d'inventer une pagination. Les lignes
déjà importées depuis l'espace web (`web-visible:`) restent en place. Elles ne
sont pas fusionnées avec les trajets Android (`android:`), dont l'identité est
l'horodatage de départ renvoyé par le serveur.

La distance enregistrée est le nombre du champ `distance`, sans conversion :
l'unité n'est pas indiquée dans le contrat lu. Le premier `sync` réel doit
être comparé au nombre de trajets du mois affiché dans l'application.

Le mot de passe n'est jamais saisi dans le terminal. Le jeton de
rafraîchissement reste dans `data/`, hors Git.

## Installation PowerShell

Depuis le dossier du projet, Python minimum 3.12 :

```powershell
py -3.14 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e '.[dev]'
Copy-Item .env.example .env
.\.venv\Scripts\python.exe -m youdrive init
```

Python 3.14 est disponible sur ce PC. Ne recopiez pas le modèle sur un
`.env` déjà personnalisé. L'identifiant public de connexion est lu dans
l'APK déjà extraite, `research-private/apk/base.apk`. Ce dossier reste hors Git.
Aucun téléphone, ADB ou proxy TLS n'est utilisé.

## Connexion et synchronisation

```powershell
.\.venv\Scripts\python.exe -m youdrive login
.\.venv\Scripts\python.exe -m youdrive sync
```

`login` ouvre la page officielle dans le navigateur et enregistre un handler
utilisateur `fr.axa.youdrive` (HKCU, supprimable dans le registre). `sync`
renouvelle le jeton ; s'il est refusé, la même connexion est redemandée, puis
les trajets sont importés. Vous pouvez aussi double-cliquer
`scripts/Start-YouDrive.cmd`.

```powershell
.\.venv\Scripts\python.exe -m youdrive trips
.\.venv\Scripts\python.exe -m youdrive candidates
.\.venv\Scripts\python.exe -m youdrive status
```

- `init` crée les tables sans supprimer les données.
- `login` enregistre la session sans conserver le mot de passe.
- `sync` importe la liste Android en une transaction.
- `trips` affiche les trajets locaux, les plus anciens d'abord.
- `candidates` affiche scores connus < 100 sans réclamation existante et quota
  restant ; aucune réclamation n'est préparée ou envoyée.
- `status` affiche les compteurs et statuts.

Les imports répétés actualisent les lignes Android et conservent les
réclamations. Une réponse invalide, une identité dupliquée ou une liste
incomplète fait rejeter tout le lot. Les dates naïves sont lues en
Europe/Paris et stockées en UTC ; les heures ambiguës ou inexistantes au
changement d'heure sont refusées.

## Configuration et confidentialité

Variables d'environnement prioritaires sur `.env` :

| Variable | Défaut | Rôle |
|---|---|---|
| `YOUDRIVE_DB_PATH` | `data/youdrive.sqlite3` | SQLite |
| `YOUDRIVE_DAILY_CLAIM_LIMIT` | `3` | Quota positif |
| `YOUDRIVE_TIMEZONE` | `Europe/Paris` | Affichage et jour métier |
| `YOUDRIVE_LOG_LEVEL` | `INFO` | Logs JSON |

Les chemins partent du dossier courant. `.env`, `data/` et
`research-private/` sont exclus de Git. `data/android-session.json` contient
les jetons et n'est pas chiffré par cette application. Les journaux affichent
des événements fixes et des compteurs, sans identifiant de contrat, trajet,
jeton ou mot de passe. `trips` est une sortie locale volontaire.

## Modèle et règles

`Trip` stocke identité, début/fin, score facultatif, distance, durée en
secondes, événements, positions de départ/arrivée et dates
d'import/synchronisation. `Claim` lie un trajet unique à un statut
draft/pending/corrected/rejected/unknown, texte et réponse éventuels. Toute
réclamation, même brouillon, exclut le trajet des candidats. Le quota compte
les dates d'envoi dans le jour métier ; les brouillons non envoyés ne le
consomment pas. Aucun chemin d'envoi n'existe. `create_all` crée les tables
manquantes ; aucune migration n'est fournie.

## Vérification

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m ruff check src tests
```

Les tests utilisent des JSON fictifs et n'ouvrent ni le réseau, ni le
navigateur, ni le registre. Le premier contrôle réel est un `login` puis un
`sync` lancés par le titulaire : le nombre de trajets du mois doit
correspondre à l'application. Voir
[le dossier de recherche](docs/youdrive-api-research.md).
