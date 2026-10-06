# YouDrive Claimer

Application locale Windows, Python 3.12+ et SQLite. La collecte lit les trajets
affichés par l'application YouDrive sur le téléphone, branché en USB. Les
réclamations sont préparées comme brouillons Gmail. Aucun message n'est envoyé.

## Portée

`sync` ouvre YouDrive, attend l'écran et le relance jusqu'à trois fois s'il
se ferme ou tarde à s'afficher, puis affiche l'onglet Trajets et lit les cartes
du plus récent au plus ancien. Elle s'arrête au premier trajet `phone:` déjà en base.
Sans trajet connu, ou avec `sync --full`, elle va jusqu'au bas de la liste.
Chaque défilement doit laisser au moins une carte de l'écran précédent visible ;
sinon la liste remonte un peu, pour ne sauter aucune carte. Une carte illisible ou une
liste qui ne se stabilise pas annule tout l'import. Sans `--full`, les lignes déjà
en base, y compris les anciennes lignes `web-visible:`, ne sont pas modifiées. L'identité
d'un trajet téléphone est `phone:` plus une empreinte de la date, des heures,
de la distance et des adresses, sans le score : une correction de score met à
jour la même ligne. Les adresses restent dans la base locale et ne sont pas
recopiées dans le texte du mail. Pour chaque score inférieur à 100, `sync`
ouvre le détail et enregistre une capture dans `data/screenshots/`. `drafts`
insère cette capture dans le corps du brouillon, réduite à la largeur du message.

Le téléphone doit être déverrouillé, le débogage USB autorisé, et YouDrive déjà
connecté. `adb` est pris dans le `PATH`, sinon dans le SDK Android
(`%LOCALAPPDATA%\Android\Sdk\platform-tools\adb.exe`). `YOUDRIVE_ADB` peut
indiquer un autre exécutable. Seul l'appareil USB est utilisé (`adb -d`).

## Installation PowerShell

Depuis le dossier du projet, Python minimum 3.12 :

```powershell
py -3.14 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e '.[dev]'
Copy-Item .env.example .env
.\.venv\Scripts\python.exe -m youdrive init
```

Ne recopiez pas le modèle sur un `.env` déjà personnalisé. Le numéro de contrat
et le fichier client Google restent dans `.env`, hors Git.

## Synchronisation

```powershell
.\.venv\Scripts\python.exe -m youdrive sync
.\.venv\Scripts\python.exe -m youdrive trips
.\.venv\Scripts\python.exe -m youdrive candidates
.\.venv\Scripts\python.exe -m youdrive status
```

Vous pouvez aussi double-cliquer `scripts/Start-YouDrive.cmd`.

- `init` crée les tables sans supprimer les données.
- `sync` importe les cartes de l'écran Trajets en une transaction et capture
  le détail des scores inférieurs à 100.
- `sync --full` relit toute la liste et complète les trajets manquants. Les lignes
  déjà en base sont mises à jour.
- `mark-claimed --before AAAA-MM-JJ` marque comme déjà réclamés, statut
  `unknown`, les scores inférieurs à 100 commencés avant cette date, heure de
  Paris. Ils ne sont plus candidats. Le budget de brouillons du jour n'est pas
  entamé.
- `trips` affiche les trajets locaux, les plus anciens d'abord.
- `candidates` affiche les scores connus inférieurs à 100 sans réclamation.
- `status` affiche les compteurs. Le budget d'envoi compte les dates d'envoi ;
  aucun envoi n'existe.

## Brouillons Gmail

Créez un client OAuth « Application de bureau » dans Google Cloud, ajoutez
votre compte comme utilisateur de test, et indiquez le JSON dans
`YOUDRIVE_GMAIL_CLIENT_FILE`. Le scope demandé est `gmail.compose`. Le jeton
est enregistré dans `data/`, hors Git.

```powershell
.\.venv\Scripts\python.exe -m youdrive gmail-login
.\.venv\Scripts\python.exe -m youdrive drafts
```

`drafts` prépare au plus `YOUDRIVE_DAILY_CLAIM_LIMIT` brouillons par jour de
Paris, les candidats les plus anciens d'abord. Le compteur est la date de
création de la réclamation locale. `sent_at` reste vide. Le brouillon est créé
d'abord ; la réclamation n'est enregistrée qu'ensuite. Si Gmail refuse, le
trajet reste candidat.

Chaque brouillon est adressé à `servicetechniqueyoudrive@directassurance.fr`.
L'objet reprend `[Formulaire appli] n°` et `YOUDRIVE_CONTRACT_NUMBER`. Le corps
reprend la demande de précision, la date et l'heure du trajet. Le score, la
distance et la durée sont dans la capture affichée dans le corps. La phrase de motif reste à
compléter dans Gmail. `YOUDRIVE_MAIL_SIGNATURE` est ajoutée seulement si elle est
renseignée. Aucun appel d'envoi n'est fait.

## Configuration

| Variable | Défaut | Rôle |
|---|---|---|
| `YOUDRIVE_DB_PATH` | `data/youdrive.sqlite3` | SQLite |
| `YOUDRIVE_DAILY_CLAIM_LIMIT` | `3` | Plafond positif de préparations par jour |
| `YOUDRIVE_TIMEZONE` | `Europe/Paris` | Affichage et jour métier |
| `YOUDRIVE_LOG_LEVEL` | `INFO` | Logs JSON |
| `YOUDRIVE_CONTRACT_NUMBER` | vide | Numéro cité dans le brouillon |
| `YOUDRIVE_MAIL_SIGNATURE` | vide | Signature optionnelle, `\n` pour une nouvelle ligne |
| `YOUDRIVE_GMAIL_CLIENT_FILE` | vide | JSON du client OAuth |

Les chemins partent du dossier courant. `.env`, `data/` et `research-private/`
sont exclus de Git. `data/gmail-token.json` contient le jeton et n'est pas
chiffré. Les journaux affichent des événements fixes et des compteurs, sans
numéro de contrat, trajet ou jeton.

## Vérification

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m ruff check src tests
```

Les tests n'ouvrent ni le téléphone, ni le réseau, ni Gmail. Le premier contrôle
réel est un `sync` avec le téléphone branché, puis un `drafts` dont on vérifie
dans Gmail que le message est un brouillon et n'a pas été envoyé. Voir
[le dossier de recherche](docs/youdrive-api-research.md).
