# Première capture des connexions YouDrive

Objectif : observer les serveurs réellement contactés à l'ouverture des
trajets, sans modifier l'application ni ses protections TLS.

**Première capture déjà réalisée le 2 octobre 2026 par contrôle ADB du
téléphone**, avec accord du titulaire. PCAPdroid est installé, configuré
pour YouDrive et la capture est arrêtée. Le fichier est conservé dans
`research-private/captures/`. Les étapes ci-dessous servent à reproduire
l'observation ; le titulaire n'a pas eu à effectuer manuellement cette capture.

## Ce que cette capture peut démontrer

PCAPdroid permet une capture locale sans root, via le service VPN Android.
Le VPN sert à traiter le trafic sur le téléphone, sans serveur VPN externe.
Sources : [projet officiel](https://github.com/emanuele-f/PCAPdroid) et
[guide de démarrage](https://emanuele-f.github.io/PCAPdroid/quick_start).

Les connexions et les noms de domaines visibles pourront être comparés aux
chaînes trouvées dans l'APK. Un nom d'hôte peut manquer si DNS/TLS ne le rend
pas visible. Une capture chiffrée ne donne ni les routes HTTP, ni les en-têtes
d'authentification, ni les réponses JSON. Aucun client API ne sera validé sur
la seule base de cette capture.

## Manipulations sur le téléphone

1. Installer [PCAPdroid depuis Google Play](https://play.google.com/store/apps/details?id=com.emanuelef.remote_capture),
   via le lien proposé par le projet officiel.
2. Ouvrir PCAPdroid et sélectionner uniquement YouDrive
   (`fr.axa.youdrive`) dans le filtre d'applications. Choisir l'enregistrement
   dans un fichier PCAP local si l'option est proposée.
3. Laisser le déchiffrement TLS désactivé. Aucun certificat, module de
   déchiffrement, root ou patch de l'application n'est nécessaire.
4. Démarrer la capture et accepter la demande Android de connexion VPN
   locale. Si un VPN est déjà actif, arrêter cette procédure et déterminer
   comment gérer ce conflit avant de changer la configuration existante.
5. Ouvrir YouDrive, afficher la liste des trajets, puis ouvrir le détail d'un
   trajet. Utiliser un rafraîchissement normal si l'application le propose.
   Ne pas se déconnecter, réinitialiser l'application ou effacer son cache.
6. Revenir dans PCAPdroid et arrêter la capture après environ une minute.
   Noter les opérations effectuées et leur ordre, sans noter d'identité ou
   de coordonnées personnelles dans un fichier suivi par Git.
7. Enregistrer/exporter le fichier PCAP dans Téléchargements sur le téléphone
   et garder le téléphone connecté en USB. Le fichier pourra alors être
   récupéré par ADB dans `research-private/captures/` sur le PC.

Une liste de connexions vide peut simplement signifier que YouDrive a
affiché des données mises en cache ; ce n'est pas la preuve d'une absence
d'API. Une capture doit rester locale et hors Git.

## Analyse ensuite

Comparer les domaines contactés pendant la liste et le détail aux domaines
de la configuration APK. Identifier le service métier probable et les flux
télématiques/annexes. Documenter les observations et les limites.

Pour obtenir un vrai schéma de réponse, rechercher ensuite une voie autorisée :
interface web officielle présentant ces trajets, export officiel, ou capture
HTTPS ordinaire effectivement acceptée par l'application. Ne pas contourner
un refus de certificat ou le pinning. Si aucune voie n'est disponible,
documenter la limite et envisager un import local de données obtenues par le
canal officiel d'accès/portabilité.
