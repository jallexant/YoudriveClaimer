# Scripts

Outils d'inspection locale de l'installation Android. Aucun accès au compte
ni envoi d'email.

Depuis la racine du projet, avec le téléphone USB autorisé :

```powershell
.\.venv\Scripts\python.exe scripts\extract_installed_apk.py --adb "$env:LOCALAPPDATA\Android\Sdk\platform-tools\adb.exe"
.\.venv\Scripts\python.exe scripts\inspect_apk.py research-private\apk\base.apk
```

L'extraction refuse d'écraser un APK existant. Pour une autre version, fournir
un dossier neuf avec `--output research-private/apk-autre-version`.
L'inspection analyse la base et les `libapp.so` des APK voisins, et masque
les valeurs non URL de l'environnement production. Son inventaire reste
privé ; les chaînes trouvées ne constituent pas des endpoints validés.
