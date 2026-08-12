import io
import json
import os
import re
import requests
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
import pdfplumber

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

def extract_date_from_text(text):
    match_iso = re.search(r'\b(20\d{2})[-/.](0[1-9]|1[0-2])[-/.](0[1-9]|[12]\d|3[01])\b', text)
    if match_iso:
        return f"{match_iso.group(1)}-{match_iso.group(2)}-{match_iso.group(3)}"
    
    match_nor = re.search(r'\b(0[1-9]|[12]\d|3[01])[-/.](0[1-9]|1[0-2])[-/.](20\d{2})\b', text)
    if match_nor:
        return f"{match_nor.group(3)}-{match_nor.group(2)}-{match_nor.group(1)}"
        
    return datetime.now().strftime("%Y-%m-%d")

def is_long_course(course_str):
    if not course_str:
        return False
    c = str(course_str).strip().upper()
    return c in ['LCM', '50M', '50', 'LCM50', 'LANGBANE']

for url in urls:
    try:
        res = requests.get(url, headers=headers, timeout=30)
        res.raise_for_status()

        # -------------------------------------------------------------
        # 1. PARSING AV PDF-FILER (LIVETIMING)
        # -------------------------------------------------------------
        if url.lower().endswith('.pdf') or 'pdf' in url.lower():
            with pdfplumber.open(io.BytesIO(res.content)) as pdf:
                # Sjekk hele PDF-teksten for global banelengde (kortbane vs langbane)
                full_text = "".join([page.extract_text() or "" for page in pdf.pages[:3]]).lower()
                
                global_course = "25m"
                if "langbane" in full_text or "50m-bane" in full_text or "50m basseng" in full_text or "bane: 50" in full_text or "lcm" in full_text:
                    global_course = "50m"

                meet_date = extract_date_from_text(full_text)
                current_event = "Ukjent øvelse"
                current_course = global_course

                for page in pdf.pages:
                    text = page.extract_text()
                    if text:
                        for line in text.split('\n'):
                            line_lower = line.lower()
                            if "øvelse" in line_lower or "event" in line_lower:
                                current_event = line.strip()
                                # Sjekk om øvelsesoverskriften spesifikt nevner banetype
                                if "langbane" in line_lower or "(50m)" in line_lower or "50m bane" in line_lower:
                                    current_course = "50m"
                                elif "kortbane" in line_lower or "(25m)" in line_lower or "25m bane" in line_lower:
                                    current_course = "25m"
                                else:
                                    current_course = global_course

                    tables = page.extract_tables()
                    for table in tables:
                        for row in table:
                            row_clean = [c.strip() if c else "" for c in row]
                            row_text = " ".join(row_clean).lower()

                            if "varodd" in row_text or "vågsbygd" in row_text or "vagsbygd" in row_text:
                                club_name = ""
                                athlete_name = ""
                                swim_time = ""
                                fina_pts = 0
                                bday_year = ""

                                if "varodd" in row_text:
                                    club_name = "Varodd Svømmeklubb"
                                elif "vågsbygd" in row_text or "vagsbygd" in row_text:
                                    club_name = "Vågsbygd SLK"

                                # Identifiser felt basert på mønster (Tid, Poeng, Fødselsår)
                                for cell in row_clean:
                                    cell_str = cell.strip()
                                    if not cell_str:
                                        continue

                                    # Fødselsår (4 siffer mellom 1990 og 2026)
                                    if cell_str.isdigit() and 1990 <= int(cell_str) <= 2026 and not bday_year:
                                        bday_year = cell_str

                                    # FINA / WA Poeng (Reelt poengtall mellom 10 og 1100, ikke fødselsår)
                                    elif cell_str.isdigit():
                                        val = int(cell_str)
                                        if 10 <= val <= 1100 and val != int(bday_year or 0):
                                            fina_pts = val

                                    # Svømmetid (f.eks. 24.50 eller 1:02.15)
                                    elif re.match(r'^(\d{1,2}:)?\d{1,2}\.\d{2}$', cell_str):
                                        swim_time = cell_str

                                # Hent utøvernavn
                                non_empty = [
                                    c for c in row_clean 
                                    if c and "varodd" not in c.lower() 
                                    and "vågsbygd" not in c.lower() 
                                    and "vagsbygd" not in c.lower() 
                                    and c != swim_time 
                                    and c != str(fina_pts) 
                                    and c != bday_year 
                                    and not re.match(r'^\d+\.?$', c)
                                ]
                                if non_empty:
                                    athlete_name = non_empty[0]

                                fullt_navn = athlete_name.title()
                                if fullt_navn.lower() in OVERSTYR_TIL_VARODD:
                                    club_name = "Varodd Svømmeklubb"

                                sec = parse_time_to_seconds(swim_time)
                                if fullt_navn and swim_time and swim_time != "00:00.00":
                                    raw_results.append({
                                        "navn": fullt_navn,
                                        "klubb": club_name,
                                        "fodselsar": bday_year,
                                        "kjonn": "",
                                        "ovelse": current_event,
                                        "basseng": current_course,
                                        "tid": swim_time,
                                        "fina": fina_pts,
                                        "sekunder": sec,
                                        "dato": meet_date
                                    })

        # -------------------------------------------------------------
        # 2. PARSING AV LENEX (.ZIP / .XML / .LEF)
        # -------------------------------------------------------------
        else:
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

            meet_date_str = ""
            meet_course = "25m"

            for meet in root.iter():
                if meet.tag.upper() == 'MEET':
                    meet_date_str = meet.attrib.get('citydate') or meet.attrib.get('date') or ''
                    if is_long_course(meet.attrib.get('course')):
                        meet_course = "50m"
                    break

            ovelser = {}
            for elem in root.iter():
                if elem.tag.upper() == 'EVENT':
                    event_id = elem.attrib.get('eventid') or ''
                    
                    # Sjekk event-nivå, ellers fall tilbake på stevne-nivå
                    event_course_raw = elem.attrib.get('course')
                    if event_course_raw:
                        course_str = "50m" if is_long_course(event_course_raw) else "25m"
                    else:
                        course_str = meet_course

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
                                    
                                    # Les poeng fra 'points' eller 'fina' attributt
                                    raw_pts = result.attrib.get('points') or result.attrib.get('fina') or 0
                                    fina = int(raw_pts) if str(raw_pts).isdigit() else 0

                                    event_id = result.attrib.get('eventid') or ''
                                    res_date = result.attrib.get('date') or meet_date_str

                                    if tid and tid != "00:00.00" and fullt_navn:
                                        info = ovelser.get(event_id, {"navn": "Ukjent øvelse", "basseng": meet_course})
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

# -------------------------------------------------------------
# 3. KRONOLOGISK SORTERING OG BEHANDLING
# -------------------------------------------------------------
utover_map = {}
for r in raw_results:
    key = (r["navn"], r["ovelse"], r["basseng"])
    if key not in utover_map:
        utover_map[key] = []
    utover_map[key].append(r)

endelige_resultater = []
to_years_ago = (datetime.now() - timedelta(days=730)).strftime("%Y-%m-%d")

for key, tider in utover_map.items():
    # Sorterer etter dato slik at nyeste registrering blir valgt som hovedresultat
    tider.sort(key=lambda x: str(x["dato"]), reverse=True)
    nyeste = tider[0].copy()

    # Forbedringsberegning
    gyldige_tider = [t for t in tider if t["sekunder"] is not None]
    if len(gyldige_tider) > 1:
        gyldige_tider.sort(key=lambda x: str(x["dato"]))
        siste_to_ar = [t for t in gyldige_tider if str(t["dato"]) >= to_years_ago]
        bruk_tider = siste_to_ar if len(siste_to_ar) >= 2 else gyldige_tider

        eldste_sek = bruk_tider[0]["sekunder"]
        beste_sek = min(t["sekunder"] for t in bruk_tider)

        if eldste_sek and eldste_sek > 0:
            endring = ((eldste_sek - beste_sek) / eldste_sek) * 100
            nyeste["forbedring"] = round(endring, 2)
        else:
            nyeste["forbedring"] = 0.0
    else:
        nyeste["forbedring"] = 0.0

    endelige_resultater.append(nyeste)

# Sorterer den ferdige JSON-strukturen med nyeste stevner og flest FINA-poeng øverst
endelige_resultater.sort(key=lambda x: (str(x["dato"]), int(x["fina"] or 0)), reverse=True)

os.makedirs(json_dir, exist_ok=True)
with open(json_path, "w", encoding="utf-8") as f:
    json.dump(endelige_resultater, f, ensure_ascii=False, indent=2)

print(f"Fullført! Lagret {len(endelige_resultater)} resultater til {json_path}")
        
