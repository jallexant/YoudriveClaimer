# YouDrive Claimer

Fondations d'une application **locale sur Windows**, en Python 3.12+ et SQLite,
pour suivre les trajets YouDrive et, ultérieurement, les réclamations.

Le projet se concentre actuellement sur les étapes 1 et 2 : stockage, CLI et
recherche du protocole Android. **Aucun trajet réel n'est encore récupéré.**
Aucun client HTTP, accès Gmail, génération ou envoi d'email n'est implémenté.

## Installation Windows / PowerShell

Depuis le dossier du projet, avec Python 3.12 ou ultérieur installé :

```powershell
py -3.14 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e '.[dev]'
Copy-Item .env.example .env
.\.venv\Scripts\python.exe -m youdrive init
```

La commande `py -3.14` correspond au Python disponible sur ce PC lors de
l'initialisation ; adaptez-la à votre version (minimum 3.12).
L'activation du venv n'est pas nécessaire avec ces commandes.

## CLI actuelle

```powershell
.\.venv\Scripts\python.exe -m youdrive trips
.\.venv\Scripts\python.exe -m youdrive candidates
.\.venv\Scripts\python.exe -m youdrive status
.\.venv\Scripts\python.exe -m youdrive sync
```

- `init` crée les tables, sans supprimer les données existantes.
- `trips` affiche les trajets locaux, du plus ancien au plus récent.
- `candidates` affiche les trajets avec score connu inférieur à 100, sans
  réclamation existante, ainsi que le budget d'envoi restant aujourd'hui.
  La liste contient tous les candidats ; elle ne prépare ni n'envoie rien.
- `status` affiche les compteurs locaux et les statuts des réclamations.
- `sync` explique que le protocole n'est pas vérifié et retourne le code 2,
  sans appel réseau ni modification de la base.

Les commandes locales initialisent automatiquement une base absente. Une
base vide est donc normale tant que l'import réel n'est pas disponible.
`claims prepare` sera ajouté après validation de la récupération des trajets.

## Configuration et confidentialité

`.env.example` contient uniquement les réglages connus. Copiez-le en `.env`.
Les variables d'environnement du processus ont priorité sur ce fichier.

| Variable | Valeur par défaut | Rôle |
|---|---|---|
| `YOUDRIVE_DB_PATH` | `data/youdrive.sqlite3` | Fichier SQLite local |
| `YOUDRIVE_DAILY_CLAIM_LIMIT` | `3` | Quota configurable, entier positif |
| `YOUDRIVE_TIMEZONE` | `Europe/Paris` | Jour métier et affichage |
| `YOUDRIVE_LOG_LEVEL` | `INFO` | Niveau des logs JSON sur stderr |

Les chemins et `.env` sont résolus depuis le dossier courant : lancez les
commandes depuis le projet, ou utilisez un chemin absolu pour la base.

`.env`, bases locales, APK et captures réseau sont exclus de Git. Placez les
autres éléments d'investigation dans `research-private/`, également exclu.
La base, les captures et un futur `.env` contenant des secrets doivent rester
privés sur le PC. `.env` et SQLite ne sont pas chiffrés par cette application.
Les logs ne contiennent que des noms d'événements fixes, sans payload,
token, mot de passe ou numéro de contrat. L'affichage des trajets est une
sortie locale volontaire, pas un journal d'exécution.

## Modèle et règles

- `Trip` : identifiant local, identifiant YouDrive unique, début/fin, score
  éventuellement inconnu, distance en km, durée en secondes, événements JSON,
  GPS JSON facultatif, dates d'import et de dernière synchronisation.
- `Claim` : trajet unique, création, envoi éventuel, statut (`draft`, `pending`,
  `corrected`, `rejected`, `unknown`), texte et réponse éventuels.
- L'état de traitement est calculé depuis les trajets et réclamations : aucun
  compteur séparé susceptible de diverger. Toute réclamation existante, même
  brouillon ou refusée, exclut le trajet des candidats.
- Une contrainte SQLite garantit une seule réclamation par trajet. Une
  éventuelle relance manuelle nécessitera un workflow explicite ultérieur.
- Le quota compte les dates **d'envoi**, tous statuts confondus, dans le jour
  local configuré. Les brouillons non envoyés ne consomment pas ce quota.
  Le futur workflow devra contrôler et réserver le quota transactionnellement
  avant tout envoi ; il n'existe actuellement aucun chemin d'envoi.
- Les dates doivent inclure un fuseau. Elles sont stockées en UTC et affichées
  dans le fuseau configuré, y compris lors des changements d'heure.

Les champs JSON sont une structure de stockage provisoire, pas un contrat
de réponse YouDrive. Les unités et champs réels devront être confirmés.
`create_all` crée uniquement les tables manquantes ; aucune migration de
schéma existant n'est encore fournie.

## Vérification

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m ruff check .
```

Les tests utilisent des données fictives dans des bases temporaires : ils
ne prouvent ni l'accès à YouDrive ni la correction d'un trajet réel.

## Suite

Voir [le dossier de recherche](docs/youdrive-api-research.md) pour les faits,
inconnues, sources officielles et éléments nécessaires à l'analyse de l'APK.
La prochaine réalisation sera un client minimal en lecture seule, uniquement
après observation et validation d'un endpoint de trajet réel.
