# Recherche technique YouDrive

État au 5 octobre 2026. La collecte retenue est la lecture de l'API Android
déjà présente dans l'APK extraite, sans téléphone et sans USB. Le journal du
5 octobre décrit le contrat. Aucune modification distante ni email.

## État des preuves

| Élément | État | Preuve / limite |
|---|---|---|
| Package `fr.axa.youdrive` | Confirmé publiquement | Fiche Google Play officielle |
| Éditeur Direct Assurance, développeur AVANSSUR | Confirmé publiquement | Fiche Google Play |
| Scores, trajets, événements et carte | Décrits publiquement | Pages officielles ci-dessous ; aucune réponse API observée |
| APK et version installée | Observés localement | Extraction ADB USB : 3.2.6, code 157, base + quatre APK fractionnés ; Android 17 |
| Signature et empreintes | Vérifiées localement | `apksigner verify` réussi ; SHA-256 enregistrés hors Git ; pas de comparaison à une signature externe |
| Domaines techniques | Observés statiquement | Configuration `.env.production` et chaînes DEX/native, voir ci-dessous |
| Routes Android de trajets | Lues dans le snapshot Dart | `GET` déduit, chemin unique avec `with_pois` et `with_invalid` ; aucun paramètre de page |
| Méthode HTTP, pagination et schéma JSON Android | Contrat statique | Un appel, champs `RUserTrip` consécutifs ; unité de `distance` non indiquée ; pas d'identifiant de trajet |
| Authentification | PKCE statique | `connect/authorize` et `connect/token` ; essai réel encore à lancer par le titulaire |
| Pinning | Déclaré pour CMT | `network_security_config.xml` contient un `pin-set` pour `cmtelematics.com` et ses sous-domaines ; application effective non testée |
| Attestation, compatibilité proxy de l'API principale | Inconnues | Aucun essai de capture HTTPS |
| Capture réseau en conditions réelles | Effectuée sans déchiffrement | PCAPdroid filtré sur YouDrive, liste et détail ouverts via ADB ; domaines ci-dessous |
| Lecture des écrans par ADB | Observée | Hiérarchies d'accessibilité de la liste et du détail disponibles ; import non implémenté |
| Espace client web PC | Consulté normalement dans Chrome | Tableau de bord et page des anciens trajets accessibles avec la session existante |
| Historique web | Partiel | 10 anciens trajets dans la page ; 3 récents dans le tableau de bord ; aucune pagination confirmée |
| Tracé GPS web | Indisponible selon le titulaire | Ne pas confondre adresses de départ/arrivée et tracé du trajet |
| Client Python web / connexion dédiée | Refusé par antirobots | Prototype Playwright arrêté ; aucun contournement ni réponse API réelle validée |
| Relais Chrome habituel | Installé et validé réellement | Lecture DOM passive, réception locale de 3 + 10 trajets ; 13 lignes SQLite, lots répétés sans doublon |

Le témoignage utilisateur indique des scores erronés fréquemment corrigés
par le support. Il motive le projet mais ne démontre ni un protocole API
ni une anomalie sur un trajet particulier.

## Direction retenue : API Android, sans USB

Depuis le 5 octobre 2026, la collecte n'est plus le relais Chrome. Le web
reste plafonné à 3 trajets récents et 10 anciens ; ce plafond est abandonné
comme source. Le client PC rejoue la lecture déjà compilée dans l'application,
avec une connexion navigateur seulement si le jeton local est refusé.

Le titulaire a explicitement choisi un script **sans téléphone**, même en
Wi-Fi. La lecture Android par ADB est une preuve d'investigation passée,
pas une dépendance du script final.

L'espace client a été consulté par connexion ordinaire dans Chrome, depuis
le lien du site officiel. Pages observées :
`/espace-personnel/mypolicy/tableau-de-bord-Youdrive` et suffixe `/trajets`.
La page des anciens trajets contient 10 cartes. Les données personnelles et
le DOM restent dans `research-private/`, hors Git.

Les fichiers JavaScript publics **réellement chargés par ces pages** ont été
analysés sans session/cookies. Ils définissent :

```text
GET https://espace-personnel.direct-assurance.fr/api/private-domain-redesign/youdrive/policy/<encryptedPolicyGeneralId>/trips?numberOfTrips=13
```

Le resolver utilise 13 : le tableau de bord prend `slice(0,3)`, la page
anciens trajets `slice(3)`. **La présence du paramètre ne prouve pas que le
serveur autorise un historique plus large.** Le connecteur conserve exactement
cette limite et n'essaie aucun autre paramètre ou endpoint supposé.

Enveloppe consommée par le web : `{status,data}`, succès `status=0`, non
autorisé `status=3`. Champs lus par les composants : `id`, `startDate`,
`endDate`, `distance` (affichée en km), `durationInMinutes`, `score`,
`startAddress`, `endAddress`, `tripWithoutPhone`. Les deux dates sont
converties en `Date` JavaScript. Ce sont des **faits statiques** ; les types
et fuseaux de la réponse réelle restent à vérifier. Aucun tracé GPS ni
événement détaillé n'a été trouvé dans le parcours consommé.

L'authentification web utilise une navigation normale vers
`api/oidc/login?returnUrlAfterLogin=...` et un contrôle
`GET api/authenticate/eligibility-check`. La durée des cookies et le
renouvellement autonome ne sont pas établis. Un prototype fondé sur la
[session partagée de Playwright](https://playwright.dev/python/docs/api/class-apirequestcontext)
et une connexion normale dans Chrome dédié a été préparé. Le titulaire a
constaté un refus antirobots : ce processus a été interrompu, sans récupération
de session ni import API. Ce prototype n'est pas exposé par la CLI actuelle.

À la demande du titulaire, la page déjà connectée dans Chrome habituel a
ensuite été lue par son DOM visible : date française avec année, horaires,
score, distance en km et durée HH:mm. Dix trajets ont été capturés puis
importés localement. Une actualisation ultérieure a aussi provoqué un CAPTCHA
sur ce navigateur ; les interactions automatisées ont été arrêtées et
le titulaire a rétabli l'accès lui-même par le parcours normal.

Le titulaire a explicitement autorisé et installé un relais Chrome local.
L'ouverture de `chrome://extensions` par l'agent a été refusée par le contrôle
de sécurité du navigateur (protocoles HTTP/HTTPS seulement) ; le chargement
de l'extension non empaquetée a donc été réalisé manuellement, sans détour.
Le relais lit uniquement les cartes rendues sur les pages YouDrive. Il ne
lit aucun cookie/mot de passe, n'ouvre ni actualise les pages et n'appelle
aucune API distante. Il transmet les champs visibles à `127.0.0.1:8766`,
avec clé aléatoire locale ; le serveur est limité à loopback, refuse les
origines web, valide taille et schéma avant toute transaction. Les envois
refusent redirections et cookies. Les adresses ne sont pas transmises :
elles participent seulement à l'empreinte calculée dans Chrome.

**Validation réelle du 2 octobre :** trois trajets récents reçus, puis dix
anciens reçus ; SQLite contient 13 trajets. La répétition des lots a actualisé
les mêmes lignes sans doublon. Toutes ces opérations sont locales, sans
téléphone, email ni modification distante. Cette collecte partielle n'est plus
la commande `sync` : depuis le 5 octobre 2026, `sync` interroge l'API Android.
Les 13 lignes `web-visible:` restent en base.

Les cartes ne donnent pas l'identifiant serveur. L'identité provisoire
`web-visible:<sha256>` utilise date, horaires, distance et adresses, sans score.
Une modification de ces champs peut créer une autre ligne : la prévention
de doublons inter-sources doit être qualifiée avant un futur envoi automatique.
Les heures Europe/Paris ambiguës/inexistantes sont rejetées plutôt qu'inférées.
Les lignes sorties de la fenêtre web sont conservées, mais leur score ne
peut plus être contrôlé par ce relais. Le contrat du 5 octobre 2026 décrit
la lecture qui remplace cette collecte pour l'historique et les points d'intérêt.

Preuves statiques privées : cinq JS, manifeste SHA-256 et
`research-private/web-static/static-findings.md`. Capture visible privée :
`research-private/visible-trips.json`.

## Sources officielles consultées

1. [Google Play — YouDrive](https://play.google.com/store/apps/details?id=fr.axa.youdrive&hl=fr)
   confirme le package et l'éditeur. La fiche décrit les scores, accélérations,
   freinages, virages et allures. La mise à jour affichée du 31 juillet 2026
   mentionne des corrections d'authentification : cela ne révèle pas son
   mécanisme et ne donne pas la version installée sur le téléphone.
2. [Application mobile YouDrive](https://www.direct-assurance.fr/nos-services/appli-mobile-youdrive)
   décrit le test de conduite sur smartphone et l'affichage des trajets,
   scores et économies pour les clients connectés au boîtier.
3. [Assurance auto connectée](https://www.direct-assurance.fr/nos-assurances/assurance-auto-connectee)
   décrit l'identification avec le compte Direct Assurance et l'association
   Bluetooth du boîtier.
4. [Politique de confidentialité YouDrive](https://www.direct-assurance.fr/direct-assurance/politique-confidentialite-appli-youdrive)
   mentionne date, heure, géolocalisation, accélération, freinage, allure,
   virage, kilomètres et référence du boîtier, ainsi que carte et tableau de
   bord. Elle indique des droits d'accès et de portabilité. Ses mentions de
   durées de conservation ne permettent pas d'établir l'historique disponible
   via une éventuelle API.
5. [Conditions particulières YouDrive, document 08.24](https://directassurance.cdn.axa-contento-118412.eu/directassurance/584a1f8a-2373-4855-a226-69d5a07dece4_CPYD_08.24_VW_def_18.09.pdf)
   décrivent un boîtier Bluetooth et le GPS du smartphone. Le dispositif
   réellement utilisé par le titulaire reste à préciser ; les générations
   de boîtiers et documents peuvent différer.

Ces pages renseignent les fonctions produit, pas les appels internes.

## Premières observations de l'APK installé

L'utilisateur a connecté son téléphone avec débogage USB autorisé. Les
outils Android SDK déjà présents sur le PC ont permis une extraction
en lecture seule de `fr.axa.youdrive`. `adb -d` sélectionne explicitement
le téléphone USB et évite les sessions Wi-Fi/émulateur présentes dans ADB.
Le gestionnaire de packages Android indique l'installeur `com.android.vending`
(Google Play).
Aucune donnée du compte, préférence privée ou session applicative n'a été lue.

Preuves privées : `research-private/apk/installation.json` (versions,
tailles et SHA-256), `signature.txt` (vérification de signature),
`manifest-tree.txt` et `static-inventory.json`. Ces fichiers et les APK sont
exclus de Git. Le manifeste annonce min SDK 28 et target SDK 36.

### Domaines et environnement de production

L'APK contient des ressources Flutter et le fichier
`assets/flutter_assets/assets/env/.env.production`. Les valeurs de clés et
identifiants embarqués sont masquées dans l'inventaire et ne sont pas utilisées.

| Variable / origine | Hôte observé | Interprétation à vérifier |
|---|---|---|
| `API_URL` | `master-7rqtwti-dtlqboapsyb6y.eu-2.platformsh.site` | Base API nommée dans la configuration production |
| `DARWIN_AUTH_BASE_URL` | `esg.axa-direct.com` | Base de l'authentification Darwin |
| `LOGIN_SSO_WEB_VIEW_BASE_URL` | `login.direct-assurance.fr` | Base de connexion par WebView SSO |
| `API_DRIVE_PROSPECT` | `mobile-sink.youdrive.next.dil.services`, chemin `/mobile` | Service nommé pour le parcours prospect |
| Chaînes DEX | `mobile.cmtelematics.com`, `mobile-de-prod.cmtelematics.com`, `mobile-log.cmtelematics.com` | Adresses contenues dans les bibliothèques ; usage réel non observé |

La présence dans `.env.production` ne suffit pas à prouver que l'installation
exécute actuellement cette configuration, ni que chaque domaine est contacté.

### Routes candidates et authentification

Le binaire Flutter `libapp.so` contient notamment :

- `/users/trips?_format=json` ; `/trip/` ; `/trips/` ;
- `/users/agg_scores?_format=json` ; `/score?_format=json` ;
- `/login?_format=json` ; `/register/login?_format=json` ;
- `/authorize` ; `/auth/requestAuthCode/` ; `/cmt-auth`.

Il contient aussi les noms de fichiers `user_trips_response.dart`,
`trip_response.dart`, `trip_score_response.dart`,
`authentication_interceptor.dart`, `login_webview_settings.dart` et `pkce.dart`.
Les marqueurs `code_challenge`, `code_challenge_method`, `code_verifier`,
`S256`, `authorization_code`, `access_token`, `refresh_token`, `Authorization`
et `Bearer` sont présents.

**Hypothèse :** un parcours SSO avec code d'autorisation et PKCE participe à
la connexion ; une session/token est ensuite utilisé pour une API de trajets.
La présence des chaînes n'établit pas leurs liens, les méthodes HTTP, le
client autorisé, la redirection, les scopes ou le renouvellement. Certaines
routes peuvent concerner les prospects, un ancien parcours ou la navigation
interne ; ne pas concaténer un domaine et une route pour tester à l'aveugle.

Les namespaces DEX `com/cmtelematics/mobilesdk`, `com/cmtelematics/sdk`,
`com/cmtelematics/drivewellplugin` et `com/gotruemotion/mobilesdk` confirment
la présence de composants portant ces noms. Leurs responsabilités exactes
et l'origine des données affichées restent à vérifier.

La prochaine preuve manquante est un appel de lecture effectué normalement
par l'application, avec sa méthode, son schéma de réponse et son
authentification légitime. Aucun endpoint n'a été appelé pendant cette analyse.

### Configuration TLS et prochaine observation

Inspection supplémentaire du 2 octobre : le manifeste référence
`res/xml/network_security_config.xml`. Le fichier contient une configuration
de domaine avec `includeSubdomains=true` et des empreintes de clés publiques
épinglées pour `cmtelematics.com`, ainsi qu'une configuration de
`www.cmtelematics.com`. Aucun ajout de confiance aux certificats utilisateur
n'apparaît dans ce fichier. La preuve décodée est conservée dans
`research-private/apk/network-security-tree.txt`.

Selon la [documentation Android](https://developer.android.com/privacy-and-security/security-config),
les applications modernes ne font pas confiance par défaut aux certificats
ajoutés par l'utilisateur. Le pinning impose en plus une correspondance avec
les clés épinglées. Ce constat ne permet pas de déduire le comportement de
chaque bibliothèque Flutter ou de chaque domaine YouDrive. Aucun proxy ou
certificat n'a été installé et aucun contrôle TLS n'a été modifié.

Première observation retenue : capture locale **sans déchiffrement**, filtrée
sur YouDrive, avec PCAPdroid. Elle peut montrer les connexions, adresses et
certains noms d'hôtes, mais ne révèle pas les chemins HTTPS, tokens ou JSON.
Ce sera une corroboration des domaines, pas une preuve d'endpoint exploitable.
PCAPdroid n'était pas installé lors de la première vérification USB du 2 octobre.
Voir [la procédure de capture](capture-youdrive.md).

### Capture réalisée par contrôle USB

À la demande du titulaire, les manipulations ont ensuite été réalisées par
ADB : installation de PCAPdroid 2.0.2 depuis Google Play, filtre limité à
`fr.axa.youdrive`, mode fichier PCAP, démarrage via les autorisations Android
ordinaires, ouverture de la liste des trajets puis du détail d'un trajet.
Aucun certificat ni module de déchiffrement n'a été installé. Le blocage des
DNS privés proposé par défaut dans PCAPdroid a été désactivé et aucun blocage
QUIC n'a été activé. Aucun VPN actif n'était présent avant le démarrage.

La capture arrêtée contient 846 paquets et environ 1 Mo. Un résumé local par
lecture DNS/TLS ClientHello a relevé 26 ClientHello décodables et notamment :

- `master-7rqtwti-dtlqboapsyb6y.eu-2.platformsh.site` ;
- `esg.axa-direct.com` ;
- `login.direct-assurance.fr` ;
- `mobile-de-prod.cmtelematics.com`.

Ces quatre domaines de l'APK sont donc aussi **observés sur le réseau**
pendant la session de consultation. Les autres domaines de services annexes
restent dans le résumé privé. On ne peut pas attribuer chaque connexion à
la liste ou au détail à partir de ce seul résumé, ni démontrer la route
`/users/trips?_format=json`, la méthode, les en-têtes ou le JSON.
L'analyse n'a pas déchiffré TLS et n'effectue pas de réassemblage TCP ;
l'inventaire des noms n'est donc pas garanti exhaustif.

Preuves locales hors Git :
`research-private/captures/youdrive-connections-20261002.pcap`, son
`.summary.json` avec SHA-256 et période UTC, et les hiérarchies d'écran
`window-youdrive-trips.xml` / `window-youdrive-detail.xml`.
Le petit outil d'investigation et sa dépendance `dpkt` restent eux aussi
dans `research-private/`, séparés de l'application.

L'arrêt a été vérifié : PCAPdroid affiche « Prêt » et « Démarrer », et
aucun réseau VPN actif n'est présent après la capture. PCAPdroid reste
installé pour les observations ultérieures ; aucune capture continue
n'est laissée active.

### Alternative concrète : lecture de l'interface

Les éléments d'accessibilité YouDrive sont lisibles via `uiautomator dump`
sans root ni modification de l'APK. Les lignes de la liste sont cliquables
et exposent du texte de trajet ; le détail expose la carte et les catégories
vitesse, accélération, freinage et virage. Cela confirme la possibilité
d'explorer une extraction par navigation normale si l'API ne peut pas être
reproduite sans contournement.

Cette piste n'est pas encore un import fiable : il reste à vérifier les
champs effectivement exposés, la pagination/défilement, l'année et le
fuseau, la stabilité d'identification d'un trajet, ainsi que la résistance
aux mises à jour de l'application. Aucun trajet n'a été importé dans SQLite.

## Démarche d'analyse autorisée

### 1. APK original

Utiliser l'APK provenant de l'installation officielle du titulaire, avec
version et origine. Certaines installations sont composées d'une base et
de plusieurs APK fractionnés : conserver l'ensemble si disponible.
Stocker les fichiers dans `research-private/`, calculer localement leur
SHA-256 et relever package, version et signature avant analyse.

Inspecter statiquement : manifeste, permissions, configuration de sécurité
réseau, ressources, chaînes de domaines et routes, bibliothèques HTTP et
authentification. Des outils tels que Android SDK/apkanalyzer et JADX peuvent
être envisagés ; aucun n'est installé ou utilisé dans cette première étape.
Une chaîne découverte reste une piste jusqu'à corroboration avec un appel
réel ; ne pas la transformer directement en endpoint supposé.

### 2. Authentification et trafic normal

Avec le propre compte du titulaire, observer seulement connexion, affichage
de la liste et ouverture d'un trajet. Consigner méthode, domaine, route,
paramètres non sensibles, pagination, structure des réponses et statuts HTTP.
Conserver séparément et localement les données sensibles. Les notes suivies
par Git ne doivent contenir aucun secret, identifiant réel, trajet personnel
ou coordonnée GPS.

Examiner une capture réseau seulement si elle est accessible par une
configuration ordinaire et autorisée. Si Android ou l'application refuse
l'observation HTTPS (certificat, pinning, attestation ou autre contrôle),
documenter le refus et arrêter cette piste. Aucun patch de l'APK, désactivation
de validation TLS, extraction de secret d'un autre compte, contournement
ou exploitation de vulnérabilité n'est prévu.

### 3. Critère pour le client minimal

Avant de coder un client `requests`/`httpx`, il faut une preuve d'appel de
lecture réel : endpoint, méthode, authentification légitime, paramètres,
réponse expurgée et correspondance avec la liste affichée sur le téléphone.
Vérifier identifiant stable, fuseau, score, distance/durée, événements,
pagination et renouvellement de session. Ne jamais inventer ces éléments.
Un premier essai devra seulement récupérer et afficher les trajets, sans
action distante ni préparation d'emails.

## Stratégies alternatives à vérifier

Si l'API directe est protégée ou dépend d'un composant non reproductible
sans contournement, expliquer précisément la limite observée. Examiner
ensuite un éventuel tableau de bord officiel, export proposé au titulaire,
ou demande officielle d'accès/portabilité. Aucun export automatique n'est
confirmé aujourd'hui. Un import local de fichier expurgé pourra constituer
une étape intermédiaire, après validation du format et des unités.

## Éléments nécessaires pour continuer

- APK et version Android : **déjà récupérés** grâce au téléphone USB.
  Ne pas fournir mot de passe, token ou numéro de contrat dans le chat.
- Type de boîtier utilisé : Bluetooth ou ancienne DriveBox, si connu.
- Téléphone USB avec débogage : **déjà disponible et utilisé**.
- Première observation réseau et navigation : **effectuées par ADB**.
- Le contrat statique du 5 octobre 2026 remplace cette attente. Le contrôle
  qui reste est le premier `login` puis `sync` lancé par le titulaire.

L'inspection statique et une capture locale de trafic chiffré sont réalisées.
Un VPN local temporaire PCAPdroid a été utilisé puis arrêté ; aucun proxy,
certificat ou déchiffrement HTTPS n'a été configuré. Aucun contournement
ne sera tenté si une observation supplémentaire est refusée.

## Contrat de lecture prouvé le 5 octobre 2026

Décodage statique du snapshot Dart de `libapp.so` (Dart 3.12.1, application
3.2.6). Aucun patch d'APK, proxy TLS ou Frida. Le compte-rendu détaillé reste
dans `research-private/`. Aucun secret ni trajet n'est recopié ici.

- Liste : chemin `/users/trips?_format=json&with_pois=true&encrypted_policy_id=`
  suivi de `&with_invalid=true`. Aucun `page` ni `numberOfTrips` à côté.
  `hasNextPage` existe dans le binaire mais pas sur cet appel. La méthode GET
  est déduite de l'URL sans corps ; le littéral `POST` est, lui, collé à
  `proxy/darwin/motorpartner?_format=json`.
- Schéma consécutif : `trips`, puis `distance`, `end_location`, `score`,
  `status`, `status_detail`, `start_location`, `start_time`, `stop_time`,
  `scores_dil` (`acceleration`, `braking`, `expert`, `smoothness`) et `poi_dil`.
  Pas de champ `id`. L'identité locale est `android:` plus `start_time`.
  `distance` est stockée telle quelle.
- Contrat : clé `EncryptedPolicyGeneralId`, cherchée dans la réponse du POST
  motorpartner. Elle n'est pas journalisée.
- Auth : l'émetteur qui répond est `https://login.direct-assurance.fr`
  (`LOGIN_SSO_WEB_VIEW_BASE_URL`, document OpenID public). `esg.axa-direct.com`
  ferme la connexion sans donnée, ce qui produit `ERR_EMPTY_RESPONSE`.
  Chemins `connect/authorize` et `connect/token`, PKCE S256, redirect
  `fr.axa.youdrive://auth`, portées `openid offline_access IdentityServerApi
  user_context`. Corps du jeton : `grant_type`, `authorization_code`,
  `refresh_token`, `redirect_uri`, `code_verifier`. En-têtes `Authorization: Bearer` et
  `X-Axa-TargetServer: prod`. La clé d'application retenue pour les appels
  contrat est le littéral client `youdrive_france`, distinct du littéral
  prospect collé à l'intercepteur. `idclient=00000` n'est pas envoyé.
- Le pinning TLS vise `cmtelematics.com`, pas l'hôte de cette lecture.
  Aucune attestation Play Integrity n'apparaît dans ce flux.
- Le premier `login` puis `sync` réel reste à faire par le titulaire. Le
  nombre de trajets du mois doit correspondre à l'application.

## Journal des découvertes

| Date | Action | Résultat |
|---|---|---|
| 2026-10-02 | Consultation des sources publiques officielles | Package et fonctionnalités confirmés, protocole inconnu |
| 2026-10-02 | Création du socle local | SQLite, CLI locale, règles de sélection/quota ; aucun accès YouDrive |
| 2026-10-02 | Extraction USB de l'installation | Version 3.2.6/code 157, cinq APK, empreintes et signature conservées localement |
| 2026-10-02 | Manifeste, assets, DEX et binaire Flutter | Domaines de production, routes candidates et indices PKCE/CMT ; aucun trafic validé |
| 2026-10-02 | Configuration TLS | Pinning déclaré pour les domaines CMT ; préparation d'une capture des connexions sans déchiffrement |
| 2026-10-02 | Capture et navigation ADB | Quatre domaines métier corroborés, capture arrêtée et rapatriée ; écrans d'accessibilité lisibles |
| 2026-10-02 | Espace personnel web et JS publics | GET statique limité à 13 ; 3 récents et 10 anciens, aucun historique complet/GPS validé |
| 2026-10-02 | Connexion Chrome dédiée au prototype | Refus antirobots signalé par le titulaire ; essai interrompu sans contournement |
| 2026-10-02 | Relais passif dans Chrome habituel | Autorisé et chargé manuellement ; réception réelle 3 + 10 et lots répétés sans doublon |
| 2026-10-05 | Snapshot Dart de l'APK déjà extraite | Contrat de lecture et PKCE figés ; collecte basculée hors du relais web ; essai réel non lancé |
| 2026-10-05 | Ouverture de `connect/authorize` | `esg.axa-direct.com` ne renvoie rien ; l'émetteur `login.direct-assurance.fr` redirige vers la page de connexion |
| 2026-10-05 | Retour du navigateur après connexion | Le handler accepte aussi `fr.axa.youdrive://auth/?code=…` et ne montre plus de console |
| 2026-10-05 | Premier `sync` après connexion | POST formulaire refusé (415) ; en JSON, le serveur exige le droit `yd_proxy_darwin_post_motorpartner` (403). `GET /users/trips` répond 404 |

Pour toute découverte ultérieure, ajouter date, origine (APK ou capture),
preuve expurgée, degré de certitude et prochaine vérification. Les données
privées restent hors de ce document et hors de Git.
