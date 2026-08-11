import io
import json
import os
import requests
import zipfile
import xml.etree.ElementTree as ET

# 1. Les alle stevne-lenker fra stevner.txt
STEVNER_FIL = "stevner.txt"
urls = []

if os.path.exists(STEVNER_FIL):
    with open(STEVNER_FIL, "r", encoding="utf-8") as f:
        urls = [line.strip() for line in f if line.strip() and not line.startswith("#")]

print(f"Fant {len(urls)} stevne-lenke(r) å prosessere.")

alle_resultater = []

# 2. Gå gjennom hver lenke
for url in urls:
    print(f"Henter data fra: {url}")
    try:
        res = requests.get(url, timeout=30)
        res.raise_for_status()

        # Pack ut LENEX (.lef er en ZIP-fil) direkte i minnet
        with zipfile.ZipFile(io.BytesIO(res.content)) as z:
            xml_name = [f for f in z.namelist() if f.endswith('.xml')][0]
            xml_content = z.read(xml_name)

        root = ET.fromstring(xml_content)

        # Kartlegg øvelser (Event-ID til Øvelsesnavn)
        ovelser = {}
        for event in root.findall('.//EVENT'):
            event_id = event.attrib.get('eventid', '')
            number = event.attrib.get('number', '')
            sweep = event.find('.//SWIMSTYLE')
            if sweep is not None:
                dist = sweep.attrib.get('distance', '')
                stroke = sweep.attrib.get('stroke', '')
                ovelser[event_id] = f"{dist}m {stroke}"
            else:
                ovelser[event_id] = f"Øvelse {number}"

        # Les utøvere og resultater fra alle klubber
        for club in root.findall('.//CLUB'):
            club_name = club.attrib.get('name', 'Ukjent klubb')
            for athlete in club.findall('.//ATHLETE'):
                fornavn = athlete.attrib.get('firstname', '')
                etternavn = athlete.attrib.get('lastname', '')
                fullt_navn = f"{fornavn} {etternavn}".strip()
                fodselsar = athlete.attrib.get('birthdate', '')[:4]
                kjonn = athlete.attrib.get('gender', '')

                for result in athlete.findall('.//RESULT'):
                    tid = result.attrib.get('swimtime', '')
                    fina = result.attrib.get('points', '')
                    event_id = result.attrib.get('eventid', '')

                    alle_resultater.append({
                        "navn": fullt_navn,
                        "klubb": club_name,
                        "fodselsar": fodselsar,
                        "kjonn": kjonn,
                        "ovelse": ovelser.get(event_id, "Ukjent"),
                        "tid": tid,
                        "fina": fina,
                        "kilde_url": url
                    })
    except Exception as e:
        print(f"Feil ved prosessering av {url}: {e}")

# 3. Lagre alle resultater til data/resultater.json
os.makedirs("data", exist_ok=True)
json_path = os.path.join("data", "resultater.json")

with open(json_path, "w", encoding="utf-8") as f:
    json.dump(alle_resultater, f, ensure_ascii=False, indent=2)

print(f"Ferdig! Totalt {len(alle_resultater)} resultater lagret i {json_path}.")
