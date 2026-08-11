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

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'
}

for url in urls:
    print(f"\nProcessing: {url}")
    try:
        res = requests.get(url, headers=headers, timeout=30)
        res.raise_for_status()

        xml_raw = None

        # Try ZIP first
        try:
            with zipfile.ZipFile(io.BytesIO(res.content)) as z:
                xml_files = [f for f in z.namelist() if f.lower().endswith('.xml') or f.lower().endswith('.lef')]
                if xml_files:
                    xml_raw = z.read(xml_files[0])
                elif len(z.namelist()) > 0:
                    xml_raw = z.read(z.namelist()[0])
            print("  -> Decompressed ZIP file successfully.")
        except zipfile.BadZipFile:
            print("  -> Not a ZIP file, treating response directly as XML.")
            xml_raw = res.content

        if not xml_raw:
            print("  -> Could not extract XML content.")
            continue

        # Decode XML safely
        try:
            xml_str = xml_raw.decode('utf-8')
        except UnicodeDecodeError:
            xml_str = xml_raw.decode('iso-8859-1', errors='ignore')

        root = ET.fromstring(xml_str)

        # Map Events
        ovelser = {}
        for elem in root.iter():
            if elem.tag.upper() == 'EVENT':
                event_id = elem.attrib.get('eventid') or elem.attrib.get('EVENTID') or ''
                number = elem.attrib.get('number') or elem.attrib.get('NUMBER') or ''
                
                dist, stroke = '', ''
                for child in elem.iter():
                    if child.tag.upper() == 'SWIMSTYLE':
                        dist = child.attrib.get('distance') or child.attrib.get('DISTANCE') or ''
                        stroke = child.attrib.get('stroke') or child.attrib.get('STROKE') or ''
                        break
                
                if dist and stroke:
                    ovelser[event_id] = f"{dist}m {stroke}"
                else:
                    ovelser[event_id] = f"Øvelse {number}"

        # Parse Athletes and Results
        count = 0
        for club in root.iter():
            if club.tag.upper() == 'CLUB':
                club_name = club.attrib.get('name') or club.attrib.get('NAME') or 'Ukjent klubb'
                
                for athlete in club.iter():
                    if athlete.tag.upper() == 'ATHLETE':
                        fornavn = (athlete.attrib.get('firstname') or athlete.attrib.get('FIRSTNAME') or '').strip()
                        etternavn = (athlete.attrib.get('lastname') or athlete.attrib.get('LASTNAME') or '').strip()
                        fullt_navn = f"{fornavn} {etternavn}".strip()
                        
                        bday = athlete.attrib.get('birthdate') or athlete.attrib.get('BIRTHDATE') or ''
                        fodselsar = bday[:4] if bday else ''
                        kjonn = athlete.attrib.get('gender') or athlete.attrib.get('GENDER') or ''

                        for result in athlete.iter():
                            if result.tag.upper() == 'RESULT':
                                tid = result.attrib.get('swimtime') or result.attrib.get('SWIMTIME') or ''
                                fina = result.attrib.get('points') or result.attrib.get('POINTS') or ''
                                event_id = result.attrib.get('eventid') or result.attrib.get('EVENTID') or ''

                                if tid and tid != "00:00.00":
                                    alle_resultater.append({
                                        "navn": fullt_navn,
                                        "klubb": club_name,
                                        "fodselsar": fodselsar,
                                        "kjonn": kjonn,
                                        "ovelse": ovelser.get(event_id, "Øvelse"),
                                        "tid": tid,
                                        "fina": fina
                                    })
                                    count += 1

        print(f"  -> Successfully extracted {count} results.")

    except Exception as e:
        print(f"  -> Error processing {url}: {e}")

# Always save output
os.makedirs(json_dir, exist_ok=True)
with open(json_path, "w", encoding="utf-8") as f:
    json.dump(alle_resultater, f, ensure_ascii=False, indent=2)

print(f"\nDone! Total results saved: {len(alle_resultater)} to {json_path}")
