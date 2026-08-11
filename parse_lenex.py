import io
import json
import os
import requests
import zipfile
import xml.etree.ElementTree as ET

STEVNER_FIL = "stevner.txt"
json_dir = "data"
json_path = os.path.join(json_dir, "resultater.json")

urls = []
if os.path.exists(STEVNER_FIL):
    with open(STEVNER_FIL, "r", encoding="utf-8") as f:
        urls = [line.strip() for line in f if line.strip() and not line.startswith("#")]

print(f"Fant {len(urls)} stevne-lenke(r) i {STEVNER_FIL}.")

alle_resultater = []

for url in urls:
    print(f"Henter og leser: {url}")
    try:
        # Legg til User-Agent så Medley ikke blokkerer kallen
        headers = {'User-Agent': 'Mozilla/5.0'}
        res = requests.get(url, headers=headers, timeout=30)
        res.raise_for_status()

        # Pakk ut XML fra minnet
        with zipfile.ZipFile(io.BytesIO(res.content)) as z:
            xml_files = [f for f in z.namelist() if f.endswith('.xml') or f.endswith('.lef')]
            if not xml_files:
                print(f"Fant ingen XML-fil i ZIP for {url}")
                continue
            xml_content = z.read(xml_files[0])

        root = ET.fromstring(xml_content)

        # Kartlegg Øvelser case-insensitive
        ovelser = {}
        for event in root.findall('.//EVENT') + root.findall('.//event'):
            event_id = event.attrib.get('eventid') or event.attrib.get('EVENTID') or ''
            number = event.attrib.get('number') or event.attrib.get('NUMBER') or ''
            
            sweep = event.find('.//SWIMSTYLE')
            if sweep is None:
                sweep = event.find('.//swimstyle')
                
            if sweep is not None:
                dist = sweep.attrib.get('distance') or sweep.attrib.get('DISTANCE') or ''
                stroke = sweep.attrib.get('stroke') or sweep.attrib.get('STROKE') or ''
                ovelser[event_id] = f"{dist}m {stroke}".strip()
            else:
                ovelser[event_id] = f"Øvelse {number}"

        # Les Klubb -> Utøver -> Resultater
        clubs = root.findall('.//CLUB') + root.findall('.//club')
        print(f"Fant {len(clubs)} klubber i filen.")

        for club in clubs:
            club_name = club.attrib.get('name') or club.attrib.get('NAME') or 'Ukjent klubb'
            
            athletes = club.findall('.//ATHLETE') + club.findall('.//athlete')
            for athlete in athletes:
                fornavn = (athlete.attrib.get('firstname') or athlete.attrib.get('FIRSTNAME') or '').strip()
                etternavn = (athlete.attrib.get('lastname') or athlete.attrib.get('LASTNAME') or '').strip()
                fullt_navn = f"{fornavn} {etternavn}".strip()
                
                bday = athlete.attrib.get('birthdate') or athlete.attrib.get('BIRTHDATE') or ''
                fodselsar = bday[:4] if bday else ''
                
                kjonn = athlete.attrib.get('gender') or athlete.attrib.get('GENDER') or ''

                results = athlete.findall('.//RESULT') + athlete.findall('.//result')
                for result in results:
                    tid = result.attrib.get('swimtime') or result.attrib.get('SWIMTIME') or ''
                    fina = result.attrib.get('points') or result.attrib.get('POINTS') or ''
                    event_id = result.attrib.get('eventid') or result.attrib.get('EVENTID') or ''

                    # Ta kun med rader som faktisk har en tid
                    if tid:
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

# Opprett data/-mappen dersom den ikke finnes
os.makedirs(json_dir, exist_ok=True)

# Lagre til data/resultater.json
with open(json_path, "w", encoding="utf-8") as f:
    json.dump(alle_resultater, f, ensure_ascii=False, indent=2)

print(f"Totalt {len(alle_resultater)} resultater lagret i {json_path}.")
