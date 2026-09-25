# Setup auf dem zweiten Mac (Bilder herunterladen)

Diese Anleitung ist für den Mac gedacht, auf dem die eigentlichen ~55.000
Cervix-Bilder heruntergeladen und zu JPEG konvertiert werden sollen (Phase
11b). Die Metadaten (welche Bilder es gibt, zu welchem Gen/Antikörper/Sample
sie gehören) wurden bereits einmal vollständig synchronisiert — dieser Mac
muss das nicht noch einmal tun, er braucht nur die vorhandene Datenbank.

Hintergrund/Architektur: `docs/MASS_DOWNLOAD.md`. Diese Datei hier ist nur
die praktische Schritt-für-Schritt-Anleitung.

## 1. Voraussetzungen prüfen

```bash
python3 --version
```

Falls keine Version ≥ 3.11 vorhanden ist (macOS liefert oft nur 3.9 mit
aus), per Homebrew nachinstallieren:

```bash
brew install python@3.12
```

## 2. Repository herunterladen

**Variante A — ohne Git, per Browser-Download (empfohlen, kein GitHub-Login im Terminal nötig):**

Im Browser (dort eingeloggt) zu `https://github.com/Infoeasy12/HPA-Cervix-Manager`
gehen, grünen **"Code"**-Button → **"Download ZIP"** klicken. Dann im Terminal:

```bash
cd ~/Downloads
ls
```

Schau nach, wie der entpackte Ordner heißt (meist automatisch entpackt,
z. B. `HPA-Cervix-Manager-main`), dann:

```bash
mv ~/Downloads/HPA-Cervix-Manager-main ~/HPA-Cervix-Manager
cd ~/HPA-Cervix-Manager
```

**Variante B — per Git** (falls du lieber `git pull` für spätere Updates
willst; braucht einen GitHub Personal Access Token, siehe unten):

```bash
git clone https://github.com/Infoeasy12/HPA-Cervix-Manager.git
cd HPA-Cervix-Manager
```

Falls dabei "Authentication failed" kommt: Im Browser zu
`https://github.com/settings/tokens/new`, Scope **`repo`** ankreuzen,
Token generieren und kopieren. Beim `git clone`-Login dann als Username
`Infoeasy12` und als Passwort den kopierten Token (nicht das GitHub-Passwort)
eingeben.

## 3. Virtuelle Umgebung + Abhängigkeiten installieren

```bash
/opt/homebrew/bin/python3.12 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -e ".[dev]"
```

## 4. Datenordner festlegen

Wähle einen Ordner, der genug Platz hat (grobe Schätzung: **~80 GB** für
alle ~55.000 JPEGs, siehe `docs/MASS_DOWNLOAD.md`). Das kann z. B. ein
iCloud-Drive-Ordner sein, muss es aber nicht.

```bash
mkdir -p /Users/DEINNAME/HPA_Cervix
```

## 5. Die Metadaten-Datenbank hierher bringen

Diese Datei **muss** von dem Mac kommen, auf dem `sync_cervix_metadata.py`
bereits gelaufen ist (sonst weiß dieser Mac nicht, welche Bilder es gibt):

```
<Datenordner>/metadata/hpa_cervix.sqlite
```

Kopiere sie z. B. per AirDrop, USB-Stick, iCloud Drive oder `scp` in:

```
/Users/DEINNAME/HPA_Cervix/metadata/hpa_cervix.sqlite
```

Alternativ: Falls dieser Mac stattdessen selbst die Metadaten synchronisieren
soll (z. B. weil kein Datei-Transfer möglich ist), kann er
`sync_cervix_metadata.py` auch einfach selbst einmal laufen lassen (dauert
lokal getestet ~3,5 Minuten inkl. Download der 730-MB-Bulk-Datei):

```bash
python scripts/sync_cervix_metadata.py --data-dir /Users/DEINNAME/HPA_Cervix
```

## 6. Bilder herunterladen und konvertieren

```bash
python scripts/download_pending_images.py --data-dir /Users/DEINNAME/HPA_Cervix --workers 2
```

- Lädt jedes Bild herunter, konvertiert es mit Pillow zu einem echten JPEG
  (Qualität 95) und trägt das Ergebnis in die SQLite-Datenbank ein.
- **Unterbrechbar und wiederholbar**: `Strg+C` jederzeit möglich, einfach den
  gleichen Befehl erneut ausführen — bereits fertige Bilder werden
  übersprungen, fehlgeschlagene automatisch erneut versucht.
- `--workers` bewusst niedrig lassen (Default: 2), um den HPA-Server nicht
  unnötig zu belasten.
- Für einen kurzen Test vorher (z. B. nur 20 Bilder):
  ```bash
  python scripts/download_pending_images.py --data-dir /Users/DEINNAME/HPA_Cervix --limit 20 --workers 2
  ```

## 7. Fortschritt prüfen

Am Ende jedes Laufs wird eine Zusammenfassung geloggt (`Succeeded`,
`Failed`, Status-Verteilung). Für eine Zwischenprüfung jederzeit:

```bash
python3 -c "
import sqlite3
conn = sqlite3.connect('/Users/DEINNAME/HPA_Cervix/metadata/hpa_cervix.sqlite')
for row in conn.execute('SELECT download_status, COUNT(*) FROM images GROUP BY download_status'):
    print(row)
"
```

## Kurzfassung (wenn alles schon mal lief und nur fortgesetzt werden soll)

```bash
cd ~/HPA-Cervix-Manager
source .venv/bin/activate
python scripts/download_pending_images.py --data-dir /Users/DEINNAME/HPA_Cervix --workers 2
```

(Nur bei Variante B zusätzlich vorher `git pull`, um neuen Code zu holen —
bei der ZIP-Variante A stattdessen bei Bedarf erneut "Download ZIP" machen
und den alten Ordner ersetzen.)
