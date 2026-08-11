import io
import json
import os
import requests
import zipfile
import xml.etree.ElementTree as ET

# 1. Fil som inneholder alle LENEX (.lef) URL-er
STEVNER_FIL = "stevner.txt"
json_dir = "data"
json_path = os.path.join(json_dir, "resultater.json")

urls = []
if os.path.exists(STEVNER_FIL):
    with open(STEVNER_FIL, "r", encoding="utf-8") as f:
        urls = [line.strip() for line in f if line.strip() and not line.startswith("#")]

print(f"Fant {len(urls)} stevne-lenke(r) i {STEVNER_FIL}.")

alle_resultater = []

# Map for å oversette standard LENEX-kjønn
KJONN_MAP = {
    'M': 'Gutt',
    'F': 'Jente',
    '1': 'Gutt',
    '2': 'Jente'
}

# 2. Gå gjennom alle LENEX-filer
for url in urls:
    print(f"Henter og leser: {url}")
    try:
        res = requests.get(url, timeout=30)
        res.raise_for_status()

        # Pakk ut XML direkte fra minnet
        with zipfile.ZipFile(io.BytesIO(res.content)) as z:
            xml_filename = [f for f in z.namelist() if f.endswith('.xml')][0]
            xml_content = z.read(xml_filename)

        root = ET.fromstring(xml_content)

        # Kartlegg Øvelser (eventid -> "100m Fri")
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

        # Les Klubb -> Utøver -> Resultater
        for club in root.findall('.//CLUB'):
            club_name = club.attrib.get('name', 'Ukjent klubb')
            
            for athlete in club.findall('.//ATHLETE'):
                fornavn = athlete.attrib.get('firstname', '').strip()
                etternavn = athlete.attrib.get('lastname', '').strip()
                fullt_navn = f"{fornavn} {etternavn}".strip()
                
                bday = athlete.attrib.get('birthdate', '')
                fodselsar = bday[:4] if bday else ''
                
                raw_kjonn = athlete.attrib.get('gender', '')
                kjonn = KJONN_MAP.get(raw_kjonn, raw_kjonn)

                for result in athlete.findall('.//RESULT'):
                    tid = result.attrib.get('swimtime', '')
                    fina = result.attrib.get('points', '')
                    event_id = result.attrib.get('eventid', '')

                    alle_resultater.append({
                        "navn": fullt_navn,
                        "klubb": club_name,
                        "fodselsar": fodselsar,
                        "kjonn": kjonn,
                        "ovelse": ovelser.get(event_id, "Ukjent Øvelse"),
                        "tid": tid,
                        "fina": fina
                    })

    except Exception as e:
        print(f"Feil ved lesing av {url}: {e}")

# 3. Opprett data/-mappen dersom den ikke finnes
os.makedirs(json_dir, exist_ok=True)

# 4. Lagre til data/resultater.json
with open(json_path, "w", encoding="utf-8") as f:
    json.dump(alle_resultater, f, ensure_ascii=False, indent=2)

print(f"Suksess! Genererte {json_path} med totalt {len(alle_resultater)} rader.")
