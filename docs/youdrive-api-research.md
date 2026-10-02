# Recherche technique YouDrive

État au 2 octobre 2026. Phase 1 : identifier une voie légitime de récupération
des trajets du titulaire du compte. Aucune modification distante ni email.

## État des preuves

| Élément | État | Preuve / limite |
|---|---|---|
| Package `fr.axa.youdrive` | Confirmé publiquement | Fiche Google Play officielle |
| Éditeur Direct Assurance, développeur AVANSSUR | Confirmé publiquement | Fiche Google Play |
| Scores, trajets, événements et carte | Décrits publiquement | Pages officielles ci-dessous ; aucune réponse API observée |
| APK et version installée | Observés localement | Extraction ADB USB : 3.2.6, code 157, base + quatre APK fractionnés ; Android 17 |
| Signature et empreintes | Vérifiées localement | `apksigner verify` réussi ; SHA-256 enregistrés hors Git ; pas de comparaison à une signature externe |
| Domaines techniques | Observés statiquement | Configuration `.env.production` et chaînes DEX/native, voir ci-dessous |
| Routes de trajets | Candidates statiques | `/users/trips?_format=json`, `/trip/`, `/trips/` ; aucun appel réel confirmé |
| Méthode HTTP, pagination, unités et schéma JSON | Inconnus | Aucun trafic métier observé |
| Authentification | Indices statiques | SSO, marqueurs PKCE et tokens ; flux et utilisation réelle non vérifiés |
| Pinning, attestation, compatibilité proxy | Inconnus | Ne rien conclure sans observation |
| Client Python compatible | Non réalisé | La CLI `sync` bloque explicitement |

Le témoignage utilisateur indique des scores erronés fréquemment corrigés
par le support. Il motive le projet mais ne démontre ni un protocole API
ni une anomalie sur un trajet particulier.

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
- Pour la prochaine étape, identifier une méthode d'observation ordinaire
  compatible avec ce téléphone et l'application. Si elle requiert une
  interaction (ouvrir YouDrive, accepter une configuration de capture),
  préciser cette interaction avant de poursuivre.

L'inspection statique initiale est terminée. Aucune capture HTTPS ni
configuration de certificat/proxy/VPN n'a été effectuée. Aucun contournement
ne sera tenté si l'observation ordinaire est refusée.

## Journal des découvertes

| Date | Action | Résultat |
|---|---|---|
| 2026-10-02 | Consultation des sources publiques officielles | Package et fonctionnalités confirmés, protocole inconnu |
| 2026-10-02 | Création du socle local | SQLite, CLI locale, règles de sélection/quota ; aucun accès YouDrive |
| 2026-10-02 | Extraction USB de l'installation | Version 3.2.6/code 157, cinq APK, empreintes et signature conservées localement |
| 2026-10-02 | Manifeste, assets, DEX et binaire Flutter | Domaines de production, routes candidates et indices PKCE/CMT ; aucun trafic validé |

Pour toute découverte ultérieure, ajouter date, origine (APK ou capture),
preuve expurgée, degré de certitude et prochaine vérification. Les données
privées restent hors de ce document et hors de Git.
