import io
import json
import os
import requests
import zipfile
import xml.etree.ElementTree as ET

STEVNER_FIL = "stevner.txt"
json_dir = "data"
json_path = os.path.join(json_dir, "resultater.json")

# Kun svømmere fra denne klubben blir med i resultater.json
MAL_KLUBB = "Varodd Svømmeklubb"

# Svømmere som automatisk endres til Varodd Svømmeklubb uansett hva som står i LENEX-filen
OVERSTYR_TIL_VARODD = [
    "mio wesøy-danielsen",
    "luca wesøy-danielsen"
]

urls = []
if os.path.exists(STEVNER_FIL):
    with open(STEVNER_FIL, "r", encoding="utf-8") as f:
        urls = [line.strip() for line in f if line.strip() and not line.startswith("#")]

print(f"Fant {len(urls)} stevne-lenke(r) i {STEVNER_FIL}.")

beste_resultater = {}

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'
}

for url in urls:
    print(f"\nProcessing: {url}")
    try:
        res = requests.get(url, headers=headers, timeout=30)
        res.raise_for_status()

        xml_raw = None
        try:
            with zipfile.ZipFile(io.BytesIO(res.content)) as z:
                xml_files = [f for f in z.namelist() if f.lower().endswith('.xml') or f.lower().endswith('.lef')]
                xml_raw = z.read(xml_files[0]) if xml_files else z.read(z.namelist()[0])
        except zipfile.BadZipFile:
            xml_raw = res.content

        if not xml_raw:
            continue

        try:
            xml_str = xml_raw.decode('utf-8')
        except UnicodeDecodeError:
            xml_str = xml_raw.decode('iso-8859-1', errors='ignore')

        root = ET.fromstring(xml_str)

        # Finn bassenglengde (SCM = 25m, LCM = 50m)
        default_course = "25m"
        for elem in root.iter():
            tag = elem.tag.upper()
            if tag in ['MEET', 'SESSION', 'CONSTRUCTION']:
                course = elem.attrib.get('course') or elem.attrib.get('COURSE') or ''
                if course.upper() == 'LCM':
                    default_course = "50m"
                    break
                elif course.upper() == 'SCM':
                    default_course = "25m"
                    break

        # Kartlegg Øvelser
        ovelser = {}
        for elem in root.iter():
            if elem.tag.upper() == 'EVENT':
                event_id = elem.attrib.get('eventid') or elem.attrib.get('EVENTID') or ''
                number = elem.attrib.get('number') or elem.attrib.get('NUMBER') or ''
                
                event_course = elem.attrib.get('course') or elem.attrib.get('COURSE') or default_course
                course_str = "50m" if str(event_course).upper() == 'LCM' else "25m"

                dist, stroke = '', ''
                for child in elem.iter():
                    if child.tag.upper() == 'SWIMSTYLE':
                        dist = child.attrib.get('distance') or child.attrib.get('DISTANCE') or ''
                        stroke = child.attrib.get('stroke') or child.attrib.get('STROKE') or ''
                        break
                
                ovelse_navn = f"{dist}m {stroke}".strip() if dist and stroke else f"Øvelse {number}"
                ovelser[event_id] = {
                    "navn": ovelse_navn,
                    "basseng": course_str
                }

        # Les Utøvere og Resultater
        for club in root.iter():
            if club.tag.upper() == 'CLUB':
                original_club_name = club.attrib.get('name') or club.attrib.get('NAME') or 'Ukjent klubb'
                
                for athlete in club.iter():
                    if athlete.tag.upper() == 'ATHLETE':
                        fornavn = (athlete.attrib.get('firstname') or athlete.attrib.get('FIRSTNAME') or '').strip()
                        etternavn = (athlete.attrib.get('lastname') or athlete.attrib.get('LASTNAME') or '').strip()
                        fullt_navn = f"{fornavn} {etternavn}".strip()
                        
                        # Overstyr klubb til Varodd Svømmeklubb for Mio og Luca
                        aktuelt_klubbnavn = original_club_name
                        if fullt_navn.lower() in OVERSTYR_TIL_VARODD:
                            aktuelt_klubbnavn = MAL_KLUBB

                        # HOPP OVER hvis utøveren ikke tilhører Varodd Svømmeklubb
                        if aktuelt_klubbnavn != MAL_KLUBB:
                            continue

                        bday = athlete.attrib.get('birthdate') or athlete.attrib.get('BIRTHDATE') or ''
                        fodselsar = bday[:4] if bday else ''
                        kjonn = athlete.attrib.get('gender') or athlete.attrib.get('GENDER') or ''

                        for result in athlete.iter():
                            if result.tag.upper() == 'RESULT':
                                tid = result.attrib.get('swimtime') or result.attrib.get('SWIMTIME') or ''
                                fina_raw = result.attrib.get('points') or result.attrib.get('POINTS') or '0'
                                event_id = result.attrib.get('eventid') or result.attrib.get('EVENTID') or ''

                                try:
                                    fina = int(fina_raw)
                                except ValueError:
                                    fina = 0

                                if tid and tid != "00:00.00" and fullt_navn:
                                    ovelse_info = ovelser.get(event_id, {"navn": "Ukjent øvelse", "basseng": default_course})
                                    ovelse_navn = ovelse_info["navn"]
                                    basseng = ovelse_info["basseng"]

                                    key = (fullt_navn, ovelse_navn, basseng)

                                    nytt_resultat = {
                                        "navn": fullt_navn,
                                        "klubb": aktuelt_klubbnavn,
                                        "fodselsar": fodselsar,
                                        "kjonn": kjonn,
                                        "ovelse": ovelse_navn,
                                        "basseng": basseng,
                                        "tid": tid,
                                        "fina": fina
                                    }

                                    if key not in beste_resultater or fina > beste_resultater[key]["fina"]:
                                        beste_resultater[key] = nytt_resultat

    except Exception as e:
        print(f"Feil ved lesing av {url}: {e}")

resultat_liste = list(beste_resultater.values())

os.makedirs(json_dir, exist_ok=True)
with open(json_path, "w", encoding="utf-8") as f:
    json.dump(resultat_liste, f, ensure_ascii=False, indent=2)

print(f"Lagret {len(resultat_liste)} unike beste-tider for {MAL_KLUBB} i {json_path}.")
