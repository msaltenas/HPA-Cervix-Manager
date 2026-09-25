# ChatGPT-Prompt für die Ersteinrichtung auf dem zweiten Mac

Dieser Text ist zum Copy-Pasten in ChatGPT gedacht, auf dem Mac, der später
die Cervix-Bilder herunterladen soll (siehe `docs/SECOND_MAC_SETUP.md` für
den Hintergrund). ChatGPT führt dich Schritt für Schritt durchs Terminal.

Die Datei `hpa_cervix.sqlite` musst du trotzdem selbst per AirDrop o. Ä.
auf den zweiten Mac bringen — das kann ChatGPT nicht übernehmen.

---

```
Ich möchte auf meinem Mac ein Python-Projekt von GitHub einrichten und starten.
Führe mich Schritt für Schritt durchs Terminal (zsh, macOS, Apple Silicon).

Repository: https://github.com/Infoeasy12/HPA-Cervix-Manager (privat, ich bin im Browser eingeloggt und habe GitHub verbunden)

Ziel: Ich will NUR das Skript scripts/download_pending_images.py laufen lassen. Es lädt Bilder von einer öffentlichen wissenschaftlichen Datenbank (Human Protein Atlas) herunter und wandelt sie in JPEGs um. Dafür braucht es Python 3.11 oder neuer.

Bitte hilf mir mit folgenden Schritten, jeweils mit den genauen Terminal-Befehlen, und prüfe nach jedem Schritt kurz, ob er funktioniert hat, bevor wir weitermachen:

1. Prüfen, ob Python 3.11+ installiert ist (`python3 --version`). Falls nicht: Python 3.12 über Homebrew installieren (`brew install python@3.12`), ggf. vorher Homebrew installieren falls nicht vorhanden.

2. Das Repository klonen (git clone) nach ~/HPA-Cervix-Manager. Falls beim Klonen ein Authentifizierungsfehler kommt, obwohl ich im Browser bei GitHub eingeloggt bin, erkläre mir wie ich entweder:
   a) die GitHub CLI (`gh`) per Homebrew installiere und `gh auth login` per Browser durchführe, oder
   b) einen Personal Access Token unter https://github.com/settings/tokens/new erstelle (Scope: repo) und beim Login als Passwort verwende.

3. In den Projektordner wechseln, eine virtuelle Python-Umgebung (.venv) mit Python 3.12 erstellen und aktivieren.

4. Die Abhängigkeiten installieren mit: pip install -e ".[dev]"
   Falls "pip: command not found" kommt, nutze stattdessen "python -m pip ...".

5. Einen Datenordner anlegen: mkdir -p ~/HPA_Cervix/metadata
   (Ich bringe die Datei hpa_cervix.sqlite selbst per AirDrop in diesen Ordner, das übernimmst du nicht.)

6. Sobald ich bestätige, dass die Datei ~/HPA_Cervix/metadata/hpa_cervix.sqlite vorhanden ist: das Skript starten mit
   python scripts/download_pending_images.py --data-dir ~/HPA_Cervix --workers 2

Frag mich nach jedem Schritt nach der genauen Terminal-Ausgabe, bevor du den nächsten Befehl vorschlägst, damit wir Fehler sofort erkennen.
```
