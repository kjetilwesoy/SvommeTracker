import io
import json
import os
import requests
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta

STEVNER_FIL = "stevner.txt"
json_dir = "data"
json_path = os.path.join(json_dir, "resultater.json")

OVERSTYR_TIL_VARODD = [
    "mio wesøy-danielsen",
    "luca wesøy-danielsen"
]

urls = []
if os.path.exists(STEVNER_FIL):
    with open(STEVNER_FIL, "r", encoding="utf-8") as f:
        urls = [line.strip() for line in f if line.strip() and not line.startswith("#")]

raw_results = []
headers = {'User-Agent': 'Mozilla/5.0'}

def parse_time_to_seconds(time_str):
    try:
        parts = time_str.split(':')
        if len(parts) == 3:
            return float(parts[0])*3600 + float(parts[1])*60 + float(parts[2])
        elif len(parts) == 2:
            return float(parts[0])*60 + float(parts[1])
        return float(parts[0])
    except:
        return None

for url in urls:
    try:
        res = requests.get(url, headers=headers, timeout=30)
        res.raise_for_status()

        try:
            with zipfile.ZipFile(io.BytesIO(res.content)) as z:
                xml_files = [f for f in z.namelist() if f.lower().endswith(('.xml', '.lef'))]
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

        # Finn stevnedato
        meet_date_str = ""
        for meet in root.iter():
            if meet.tag.upper() == 'MEET':
                meet_date_str = meet.attrib.get('citydate') or meet.attrib.get('date') or ''
                break

        default_course = "25m"
        for elem in root.iter():
            if elem.tag.upper() in ['MEET', 'SESSION', 'CONSTRUCTION']:
                course = elem.attrib.get('course') or ''
                if course.upper() == 'LCM':
                    default_course = "50m"
                    break

        ovelser = {}
        for elem in root.iter():
            if elem.tag.upper() == 'EVENT':
                event_id = elem.attrib.get('eventid') or ''
                event_course = elem.attrib.get('course') or default_course
                course_str = "50m" if str(event_course).upper() == 'LCM' else "25m"

                dist, stroke = '', ''
                for child in elem.iter():
                    if child.tag.upper() == 'SWIMSTYLE':
                        dist = child.attrib.get('distance') or ''
                        stroke = child.attrib.get('stroke') or ''
                        break
                
                ovelse_navn = f"{dist}m {stroke}".strip() if dist and stroke else "Ukjent øvelse"
                ovelser[event_id] = {"navn": ovelse_navn, "basseng": course_str}

        for club in root.iter():
            if club.tag.upper() == 'CLUB':
                orig_club = club.attrib.get('name') or ''
                
                for athlete in club.iter():
                    if athlete.tag.upper() == 'ATHLETE':
                        fornavn = (athlete.attrib.get('firstname') or '').strip()
                        etternavn = (athlete.attrib.get('lastname') or '').strip()
                        fullt_navn = f"{fornavn} {etternavn}".strip()
                        
                        klubbnavn = orig_club
                        if fullt_navn.lower() in OVERSTYR_TIL_VARODD:
                            klubbnavn = "Varodd Svømmeklubb"
                        elif "varodd" in orig_club.lower():
                            klubbnavn = "Varodd Svømmeklubb"
                        elif "vågsbygd" in orig_club.lower() or "vagsbygd" in orig_club.lower():
                            klubbnavn = "Vågsbygd SLK"

                        if klubbnavn not in ["Varodd Svømmeklubb", "Vågsbygd SLK"]:
                            continue

                        bday = athlete.attrib.get('birthdate') or ''
                        fodselsar = bday[:4] if bday else ''
                        kjonn = athlete.attrib.get('gender') or ''

                        for result in athlete.iter():
                            if result.tag.upper() == 'RESULT':
                                tid = result.attrib.get('swimtime') or ''
                                fina = int(result.attrib.get('points') or 0)
                                event_id = result.attrib.get('eventid') or ''
                                res_date = result.attrib.get('date') or meet_date_str

                                if tid and tid != "00:00.00" and fullt_navn:
                                    info = ovelser.get(event_id, {"navn": "Ukjent øvelse", "basseng": default_course})
                                    sec = parse_time_to_seconds(tid)

                                    raw_results.append({
                                        "navn": fullt_navn,
                                        "klubb": klubbnavn,
                                        "fodselsar": fodselsar,
                                        "kjonn": kjonn,
                                        "ovelse": info["navn"],
                                        "basseng": info["basseng"],
                                        "tid": tid,
                                        "fina": fina,
                                        "sekunder": sec,
                                        "dato": res_date
                                    })
    except Exception as e:
        print(f"Feil ved lesing av {url}: {e}")

# Grupper og finn beste tider + forbedringsprosent
to_year_ago = (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d")
utover_map = {}

for r in raw_results:
    key = (r["navn"], r["ovelse"], r["basseng"])
    if key not in utover_map:
        utover_map[key] = []
    utover_map[key].append(r)

endelige_resultater = []

for key, tider in utover_map.items():
    # Sorter etter FINA/WA poeng (høyest først)
    tider.sort(key=lambda x: x["fina"], reverse=True)
    beste = tider[0].copy()

    # Beregn forbedringsprosent (siste 12 mnd)
    gyldige_tider = [t for t in tider if t["sekunder"] is not None]
    
    if len(gyldige_tider) > 1:
        # Sorter kronologisk
        gyldige_tider.sort(key=lambda x: x["dato"] if x["dato"] else "1900-01-01")
        # Filtrer tider fra siste 12 mnd hvis mulig
        siste_aar = [t for t in gyldige_tider if t["dato"] >= to_year_ago]
        bruk_tider = siste_aar if len(siste_aar) >= 2 else gyldige_tider

        eldste_sek = bruk_tider[0]["sekunder"]
        beste_sek = min(t["sekunder"] for t in bruk_tider)

        if eldste_sek and eldste_sek > 0:
            endring = ((eldste_sek - beste_sek) / eldste_sek) * 100
            beste["forbedring"] = round(endring, 2)
        else:
            beste["forbedring"] = 0.0
    else:
        beste["forbedring"] = 0.0

    endelige_resultater.append(beste)

os.makedirs(json_dir, exist_ok=True)
with open(json_path, "w", encoding="utf-8") as f:
    json.dump(endelige_resultater, f, ensure_ascii=False, indent=2)

print(f"Lagret {len(endelige_resultater)} beste resultater med forbedringsprosent.")
                
