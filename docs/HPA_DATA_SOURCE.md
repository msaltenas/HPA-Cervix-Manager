# HPA Data Source — Untersuchungsergebnisse (Phase 1)

Dieses Dokument beschreibt, **wie tatsächlich verifiziert wurde** (per `curl`/HTTP gegen die offiziellen
Endpunkte, keine Vermutung), woher die Cervix-Bilder und Metadaten des HPA Cervix Managers stammen.
Alle Beispiele in diesem Dokument sind echte, live abgerufene HPA-Daten (Stand 2026-09-25).

## 1. HPA-Version

- Aktuelle Version laut `https://www.proteinatlas.org/about/download`: **25.1**
- Die XML-Einträge selbst tragen `<entry version="25" ...>` (Major-Version des Datensatzes; `.1` ist ein
  Nebenrelease der Website, ändert die Entry-Daten nicht).
- Historische Versionen sind unter `https://vXX.proteinatlas.org` archiviert (z. B. `v25.proteinatlas.org`).
  Wir pinnen **nicht** auf eine Archiv-Version — der Live-Endpunkt `proteinatlas.org` liefert immer die
  aktuell publizierte Version. Die abgerufene Version wird pro Bild in der Datenbank gespeichert
  (`images.hpa_version`), damit spätere Re-Importe nachvollziehbar bleiben.
- XML-Schema-Version: `3.1` (siehe `<xs:schema version="3.1">` in der offiziellen XSD).

## 2. Offizielle Datenquellen (geprüft)

| Zweck | URL-Muster | Format | Bemerkung |
|---|---|---|---|
| Volltext-/Feld-Suche über alle Gene | `https://www.proteinatlas.org/api/search_download.php?search=<query>&format=json&columns=<cols>&compress=no` | JSON (oder TSV) | Offizielle, dokumentierte REST-Suche. Liefert nur die angeforderten Spalten (`columns=`), **keine** Bild-URLs. Genutzt um zuverlässig Gene→Ensembl-ID aufzulösen (nie geraten). |
| Vollständiger Datensatz pro Gen | `https://www.proteinatlas.org/<ENSEMBL_ID>.xml` (auch `.json`, `.tsv`) | XML/JSON/TSV | Offizieller REST-Zugriff, in der Downloads-Seite dokumentiert ("Individual entries... by appending .xml/.json/.tsv to Ensembl ID"). **Nur die XML-Variante enthält Bild-URLs** (siehe unten). |
| Kompletter Bulk-Export | `https://www.proteinatlas.org/download/proteinatlas.xml.gz` (+ `.tsv.zip`, `.json.gz`, Schema `.xsd`) | XML/TSV/JSON | Offiziell dokumentiert, deckt **alle** Gene ab (ganzes Genom, mehrere GB). Gleiches Schema wie die Pro-Gen-XML. Für den produktiven Massendownload relevant, aber zu groß für Phase 1–2. |
| XML-Schema | `https://www.proteinatlas.org/download/proteinatlas.xsd` | XSD | Offizielle, vollständig dokumentierte Struktur inkl. Changelog aller Versionen. Grundlage für den in diesem Dokument beschriebenen Datenzugriff. |

**Geprüft und explizit NICHT verwendet**, weil nicht mehr existent (HTTP 404, live getestet):
`normal_tissue.tsv.zip`, `rna_tissue_consensus.tsv.zip`, `subcellular_location.tsv.zip` — das waren
Downloads einer älteren HPA-Version (≤ v18). Seit mehreren Versionen bündelt HPA alles in
`proteinatlas.tsv/json/xml`. Wer alte Tutorials/Blogposts zu HPA liest, stößt auf diese Dateinamen —
sie sind **veraltet** und wurden bewusst nicht verwendet.

**Wichtige Erkenntnis:** Das kombinierte JSON/TSV (`proteinatlas.json.gz`, per-Gen `.json`) enthält
**keine Bild-URLs** — nur Expressions-Zusammenfassungen (z. B. "RNA tissue specificity",
"Protein cell type specificity"). Bild-URLs, Patienten-/Sample-Metadaten und Zelltyp-Färbungen pro
Gewebeprobe sind **ausschließlich in der XML-Variante** enthalten (`<image>`/`<imageUrl>`-Elemente).
Deshalb verwendet dieses Projekt für den Bildimport die XML-Variante, nicht JSON/TSV.

## 3. Wie ein Cervix-Bild strukturell identifiziert wird

Struktur eines `<entry>` (ein Gen) in der XML, vereinfacht auf den relevanten Pfad:

```
entry (Gen, z. B. IVL, Ensembl ENSG00000163207)
 └─ antibody (id="CAB002243", releaseVersion, releaseDate, RRID?)
     └─ tissueExpression (source="HPA", technology="IHC", assayType="tissue")
         └─ data                                   ← EIN Eintrag pro Gewebe (z. B. "Cervix")
             ├─ tissue organ="Female tissues" ontologyTerms="UBERON:0000002">Cervix</tissue>
             ├─ tissueCell   (1..n; JE Zelltyp im Gewebe)
             │    ├─ cellType>Glandular cells</cellType>
             │    ├─ level type="staining">high</level>
             │    ├─ level type="intensity">strong</level>
             │    ├─ quantity>&gt;75%</quantity>
             │    └─ location>cytoplasmic/membranous</location>
             ├─ tissueCell (cellType="Squamous epithelial cells", staining="not detected", ...)
             └─ patient (1..n; JE Gewebespender)
                 ├─ sex>Female</sex>, age>46</age>, patientId>1895</patientId>
                 └─ sample
                     ├─ snomedParameters/snomed  (SNOMED-Code des Gewebes, z. B. T-83000 "Cervix")
                     └─ assayImage
                         └─ image imageType="sampleImage"
                             ├─ imageUrl>https://images.proteinatlas.org/2243/6008_B_9_3.jpg</imageUrl>
                             └─ imageUrlTif>https://images.proteinatlas.org/2243/6008_B_9_3.tif</imageUrlTif>
```

Dies ist **kein** aus der Dokumentation abgeleitetes Schema, sondern ein real abgerufener, gekürzter
Ausschnitt aus `https://www.proteinatlas.org/ENSG00000163207.xml` (Gen IVL), Zeilen 5011–5078.

### "Cervix" wird identifiziert über:
- `<tissue>`-Element mit Textinhalt `Cervix` **und** Attribut `organ="Female tissues"` **und**
  `ontologyTerms="UBERON:0000002"` (UBERON-Ontologie-ID für "cervix", stabil über alle Gene hinweg
  verifiziert — taucht bei IVL, ASRGL1 identisch auf).
- Das Attribut `status` (im XSD definiert, Werte `tissue`/`cancer`) grenzt normales Gewebe von
  Krebsgewebe ab. Der Krebs-Zweig heißt `cancerExpression` (z. B. "Cervical cancer",
  "Cervical Squamous Cell Carcinoma and Endocervical Adenocarcinoma (TCGA)") und liegt in einem
  **komplett separaten** XML-Ast (`<cancerExpression>` statt `<tissueExpression assayType="tissue">`).
  **Wichtig:** `cancerData-type` enthält laut XSD explizit **keine** `tissueCell`/`patient`/Bilder
  (im Schema auskommentiert) — Krebsbilder/-proben sind über diesen Pfad nicht abrufbar bzw. anders
  organisiert. Für dieses Projekt (normales Cervixgewebe) ist ausschließlich
  `tissueExpression[assayType="tissue"][technology="IHC"]/data/tissue = "Cervix"` relevant.
- Zusätzlich gibt es RNA-Expressionsdaten mit Tissue-Text `cervix` (kleingeschrieben) im Ast
  `rnaExpression` — das ist **keine Bildquelle**, sondern Transcript-per-Million-Werte (RNA-Seq/GTEx).
  Wird optional für Kontext gespeichert, ist aber nicht Teil der Bild-Pipeline.

### Tatsächlich beobachtete Cervix-Zelltypen (nicht erfunden, real aus XML):
- **Glandular cells** (Drüsenzellen, Endocervix)
- **Squamous epithelial cells** (Plattenepithel, Ektocervix)

Es wurden in den geprüften Genen (IVL, ASRGL1) **nur diese zwei** Zelltypen für Cervix-Gewebe
beobachtet. Andere HPA-Gewebe kennen weitere Zelltypen (z. B. "Endothelial cells",
"Peripheral nerve/ganglion" bei Colon) — für Cervix wurden bislang ausschließlich Glandular/Squamous
gesehen. Die Anwendung darf **keine** weiteren Zelltypen annehmen, sondern muss genau die Werte
übernehmen, die im jeweiligen `<tissueCell><cellType>` stehen (freier String, kein Enum in der XSD).

## 4. Bild-Identifikation

Beispiel-URL: `https://images.proteinatlas.org/2243/6008_B_9_3.jpg`

- `2243` = numerischer Ordner, entspricht der Antikörper-ID ohne Buchstaben-Präfix
  (`CAB002243` → `2243`; verifiziert auch bei `HPA055211` → Ordner `55211`).
- `6008` = ID der Foto-Serie ("image batch") dieses Antikörpers — bleibt **über verschiedene Gewebe
  desselben Antikörpers gleich** (z. B. taucht `6008` sowohl bei Cervix- als auch bei
  Cerebral-cortex-Bildern von CAB002243 auf, nur mit anderem Suffix).
- `B_9_3` = Block/Zeile/Spalte auf dem Tissue-Microarray (TMA) — die konkrete Gewebeprobe/-koordinate.
- Der volle Dateiname-Stamm `6008_B_9_3` ist **innerhalb des Antikörper-Ordners eindeutig** und dient
  in diesem Projekt als `hpa_image_id` (öffentlich stabiler HPA-Bezeichner). Eine global über alle
  Antikörper eindeutige HPA-"Bild-ID" im Sinne einer einzelnen Zahl gibt es in der offiziellen Struktur
  **nicht** — Eindeutigkeit ergibt sich erst aus (Antikörper-ID + Dateiname-Stamm). Das Projekt speichert
  deshalb `hpa_image_id = "<antibody_id>/<dateiname_stamm>"` (z. B. `CAB002243/6008_B_9_3`).
- Die **interne, stabile App-ID** (`HPA_000001`, `HPA_000002`, …) wird beim Erstimport fortlaufend
  vergeben und danach **nie** aus dem `hpa_image_id`-Wert neu berechnet — sie bleibt stabil, auch wenn
  sich am HPA-Server später etwas ändert.
- Neben `.jpg` (komprimiert, für die App verwendet) liefert die XML auch `imageUrlTif` (unkomprimiertes
  Originalformat). Die Website selbst zeigt zusätzlich `..._medium.jpg`-Vorschaubilder (kleinere Auflösung,
  aus dem HTML der Tissue-Seite, nicht aus der XML) — diese werden **nicht** verwendet, da die XML direkt
  die volle Auflösung liefert.

## 5. Zuordnung Bild → Gen / Antikörper / Sample

- **Bild → Antikörper**: strukturell eindeutig — jedes `<image>` liegt unterhalb genau eines
  `<antibody>`-Elements.
- **Bild → Gen**: strukturell eindeutig innerhalb einer Pro-Gen-XML-Datei (ein `<entry>` = ein Gen), ABER:
  ein Antikörper kann *theoretisch* mehrere Zielgene haben bzw. dasselbe Antikörper-Element könnte in
  seltenen Fällen in mehreren Gen-Einträgen auftauchen (z. B. Multi-Target-Antikörper, Isoformen). Die
  App geht **nicht** von einer 1:1-Beziehung aus, sondern bildet Bild↔Gen über eine Relationstabelle ab
  (`image_genes`), auch wenn in der Praxis meist genau ein Gen pro Bild vorliegt.
- **Bild → Sample/Patient**: ein `<sample>` (mit `patientId`, `sex`, `age`, SNOMED-Code) enthält laut
  Schema 1..n `<assayImage>` mit je 1..n `<image>` — in der Praxis in allen geprüften Fällen genau **ein**
  Bild pro Sample, das Schema erlaubt aber mehr. Auch hier: Relationstabelle statt 1:1-Annahme.
- **Bild → Zelltyp-Färbung**: Dies ist die wichtigste Einschränkung. Die `<tissueCell>`-Elemente
  (Zelltyp + Färbeintensität + Menge + Lokalisation) hängen **nicht am einzelnen Bild**, sondern am
  gesamten `<data>`-Block für (Antikörper × Gewebe). Ein `<data>`-Block für "Cervix" enthält
  typischerweise 2 `<tissueCell>`-Einträge (Glandular + Squamous) und 2–3 `<patient>`/Bilder — alle
  Bilder dieses Blocks teilen sich dieselben Zelltyp-Annotationen. Es ist **nicht** aus der XML ableitbar,
  ob ein bestimmtes Einzelbild überwiegend Drüsen- oder Plattenepithel zeigt; das ist eine gepoolte
  Aussage über die Gewebeprobe(n) des Antikörpers. **Die App erfindet hier keine Präzision**, die die
  Datenquelle nicht hergibt — deshalb werden Zelltyp-Annotationen über eine Relationstabelle
  (`tissue_cell_annotations` + `image_cell_types`) mit dem Bild verknüpft (ein Bild kann mit mehreren
  Zelltyp-Annotationen desselben Datenblocks verknüpft sein), statt sie fälschlich 1:1 in die
  `images`-Tabelle zu quetschen.

## 6. Verfügbare Metadaten (real beobachtet)

Pro Bild/Sample verfügbar:
- Ensembl-ID, Gen-Symbol (aus `<name>`/`<identifier>`)
- Antikörper-ID, `releaseVersion`, `releaseDate`, optional `RRID`
- Antigen-Sequenz des Antikörpers (`<antigenSequence>`, Aminosäuresequenz) — optional, als
  `target_information` gespeichert
- Gewebe-Text (`Cervix`), `organ`-Attribut (`Female tissues`), `ontologyTerms` (UBERON-ID)
- Zelltyp(en) im Datenblock, je mit Staining-Level, Intensity-Level, Quantity, Location
- Patient: `sex`, `age` (optional — nicht bei jedem Patient vorhanden lt. XSD `minOccurs="0"`),
  `patientId` (HPA-interne Spendernummer)
- SNOMED-Parameter der Probe (`tissueDescription`, `snomedCode`)
- Bild-URLs: `imageUrl` (JPG) und `imageUrlTif` (TIF), `imageType` (z. B. `sampleImage`)
- HPA-Entry-URL (`<entry url="https://v25.proteinatlas.org/ENSG00000163207">`)
- HPA-Datensatzversion (`<entry version="25">`)

**Nicht verfügbar / bewusst NICHT erfunden:**
- Voller Gen-**Name** (Langform, z. B. "Involucrin") — die Pro-Gen-XML liefert nur das Symbol (`IVL`),
  keine Langbeschreibung. Feld `genes.gene_name` bleibt `NULL`, bis eine verifizierte Quelle dafür
  gefunden wird (z. B. NCBI Gene, nicht Teil dieser Untersuchung).
- Ein herstellerseitiges "Provider"-Feld für Antikörper (z. B. "Atlas Antibodies", "Sigma-Aldrich") ist
  in der XML **nicht** als eigenes Attribut vorhanden. Der ID-Präfix (`HPA…` vs. `CAB…`) deutet auf
  unterschiedliche Antikörper-Programme hin, ist aber keine explizit dokumentierte "Provider"-Angabe —
  Feld `antibodies.provider` bleibt `NULL`, der Präfix ist über `antibody_id` selbst ablesbar.
- Eine global eindeutige numerische "HPA Image ID" (siehe Abschnitt 4) — wir leiten stattdessen
  `hpa_image_id` aus Antikörper-ID + Dateiname-Stamm ab; das ist keine Erfindung, sondern eine
  dokumentierte, deterministische Kombination bereits vorhandener HPA-Bezeichner.

## 7. Mehrfachbeziehungen (bestätigt in echten Daten)

- **Ein Gen kann mehrere Antikörper haben**: IVL hat 2 (`CAB002243`, `HPA055211`), ASRGL1 hat 3
  (`HPA029725`, `HPA055572`, `CAB070192`). Jeder Antikörper kann eigene Cervix-Bilder mit eigenen
  Zelltyp-Bewertungen liefern (bei IVL: CAB002243 zeigt Squamous "high", HPA055211 zeigt Squamous
  "medium" — unterschiedliche Antikörper können zu unterschiedlichen Ergebnissen kommen).
- **Ein Antikörper/Gewebe-Block hat mehrere Patienten/Samples** (2–3 in den geprüften Fällen), jedes mit
  eigenem Bild.
- **Ein Gewebe-Block hat mehrere Zelltypen** (Glandular + Squamous für Cervix), die sich alle Bilder des
  Blocks teilen (siehe Abschnitt 5).
- Alles wird über Relationstabellen statt Strings abgebildet (siehe `docs`/Schema unten).

## 8. Einschränkungen / offene Punkte

1. Zelltyp-Färbung ist pro (Antikörper × Gewebe)-Block, nicht pro Einzelbild — siehe Abschnitt 5. Die
   GUI muss das später so kommunizieren ("Zelltypen in dieser Probe", nicht "Zelltyp dieses Bildes").
2. `gene_name` (Langform) und Antikörper-`provider` sind aus dieser Quelle nicht verfügbar (NULL).
3. Die Pro-Gen-XML-Dateien sind mit ~1–1,4 MB pro Gen relativ groß, weil sie **alle** Gewebe (nicht nur
   Cervix) plus Cancer-/RNA-/Subcellular-Daten enthalten. Für den späteren Massendownload (Ziel: nur
   Cervix) muss die App nach dem Parsen gezielt nur die Cervix-`<data>`-Blöcke extrahieren und den Rest
   verwerfen — ein Vollimport aller Gene würde bedeuten, das komplette Genom (~20.000 Gene ×
   ~1 MB XML) abzurufen, nur um daraus die Cervix-Treffer zu filtern. Das ist der Haupt-Kostenfaktor für
   Phase 11 (Massendownload) und wird dort gesondert adressiert (z. B. über den Bulk-Export
   `proteinatlas.xml.gz` statt 20.000 Einzel-Requests, um Server-Last zu vermeiden).
4. Es existiert **keine** offizielle serverseitige Filterfunktion "gib mir nur Gene mit Cervix-Bildern".
   Die Web-Suche (`/api/search_download.php`) unterstützt Feldfilter (z. B. `tissue_category_rna:...`),
   aber die exakte Such-Syntax für "hat IHC-Bilder in Gewebe X" ist nicht öffentlich dokumentiert und
   wurde in dieser Untersuchung **nicht geraten**. Stattdessen: die HPA-Tissue-Übersichtsseite
   `https://www.proteinatlas.org/humanproteome/tissue/cervix` nennt namentlich Beispielgene mit
   Cervix-Bezug (u. a. MUC16, SLPI, WFDC2, IVL, TMPRSS11D, ESR1, ASRGL1, MSX1, BPIFB1, COL1A2, COL3A1,
   HOXA11) — reale, von der offiziellen Seite genannte Gene, keine Vermutung. Für den Massendownload
   (Phase 11) wurde deshalb geklärt, ob der komplette Bulk-XML-Export heruntergeladen und lokal nach
   `tissue = "Cervix"` gefiltert wird, oder ob eine Gen-Liste aus der Tissue-Seite verwendet wird.
   **Entschieden**: Bulk-XML-Export (Strategie A). Die Tissue-Seiten-Genliste wurde mit echten Daten
   widerlegt (GAPDH, ACTB, TP53, EGFR, INS — keins davon auf der Tissue-Seite gelistet — haben alle
   echte Cervix-IHC-Bilder gefunden). Vollständige Begründung und Implementierung siehe
   `docs/MASS_DOWNLOAD.md`.

## 9. In Phase 2 verwendete Testdaten (real, live abgerufen)

10 echte Cervix-Bilder aus 2 Genen, 4 Antikörpern, jeweils mit vollständigen Metadaten — siehe
`scripts/bootstrap_test.py` (Code) und den Ausführungsbericht am Ende dieser Phase. Keine der URLs,
IDs oder Metadaten in diesem Abschnitt wurde geraten; alle stammen aus den oben zitierten,
live abgerufenen XML-Dokumenten.
