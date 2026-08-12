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
    # Forsøker å finne dato i format YYYY-MM-DD eller DD.MM.YYYY i teksten
    match_iso = re.search(r'\b(20\d{2})[-/.](0[1-9]|1[0-2])[-/.](0[1-9]|[12]\d|3[01])\b', text)
    if match_iso:
        return f"{match_iso.group(1)}-{match_iso.group(2)}-{match_iso.group(3)}"
    
    match_nor = re.search(r'\b(0[1-9]|[12]\d|3[01])[-/.](0[1-9]|1[0-2])[-/.](20\d{2})\b', text)
    if match_nor:
        return f"{match_nor.group(3)}-{match_nor.group(2)}-{match_nor.group(1)}"
        
    return datetime.now().strftime("%Y-%m-%d")

for url in urls:
    try:
        res = requests.get(url, headers=headers, timeout=30)
        res.raise_for_status()

        # -------------------------------------------------------------
        # 1. PARSING AV PDF-FILER
        # -------------------------------------------------------------
        if url.lower().endswith('.pdf') or 'pdf' in url.lower():
            with pdfplumber.open(io.BytesIO(res.content)) as pdf:
                current_event = "Ukjent øvelse"
                current_course = "25m"
                meet_date = datetime.now().strftime("%Y-%m-%d")

                # Hent dato fra første side dersom det finnes
                if len(pdf.pages) > 0:
                    first_page_text = pdf.pages[0].extract_text() or ""
                    meet_date = extract_date_from_text(first_page_text)

                for page in pdf.pages:
                    text = page.extract_text()
                    if text:
                        for line in text.split('\n'):
                            if "øvelse" in line.lower() or "event" in line.lower():
                                current_event = line.strip()
                                if "50m" in line.lower() or "langbane" in line.lower() or "lcm" in line.lower():
                                    current_course = "50m"
                                else:
                                    current_course = "25m"

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

                                for cell in row_clean:
                                    if len(cell) == 4 and cell.isdigit() and 1990 <= int(cell) <= 2026:
                                        bday_year = cell
                                    elif ":" in cell or ("." in cell and any(char.isdigit() for char in cell) and len(cell) <= 8):
                                        if cell.isdigit() and int(cell) > 10:
                                            fina_pts = int(cell)
                                        else:
                                            swim_time = cell

                                non_empty = [c for c in row_clean if c and "varodd" not in c.lower() and "vågsbygd" not in c.lower() and "vagsbygd" not in c.lower() and c != swim_time and c != str(fina_pts) and c != bday_year]
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

# -------------------------------------------------------------
# 3. KRONOLOGISK SORTERING OG BEREGNING AV BARE DE NYESTE RESULTATENE
# -------------------------------------------------------------

# Grupper alle tider per utøver + øvelse + basseng
utover_map = {}
for r in raw_results:
    key = (r["navn"], r["ovelse"], r["basseng"])
    if key not in utover_map:
        utover_map[key] = []
    utover_map[key].append(r)

endelige_resultater = []
to_years_ago = (datetime.now() - timedelta(days=730)).strftime("%Y-%m-%d")

for key, tider in utover_map.items():
    # Sorter alle tider for denne øvelsen etter DATO (nyeste først)
    tider.sort(key=lambda x: str(x["dato"]), reverse=True)

    # Den nyeste registrerte tiden/stevnet blir hovedresultatet
    nyeste = tider[0].copy()

    # Beregn forbedringsprosent dersom det finnes eldre tider
    gyldige_tider = [t for t in tider if t["sekunder"] is not None]
    if len(gyldige_tider) > 1:
        # Sorter fra eldste til nyeste for forbedringsberegning
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

# Sorter den endelige listen slik at de nyeste stevneresultatene ligger øverst
endelige_resultater.sort(key=lambda x: (str(x["dato"]), int(x["fina"] or 0)), reverse=True)

# Lagre til JSON
os.makedirs(json_dir, exist_ok=True)
with open(json_path, "w", encoding="utf-8") as f:
    json.dump(endelige_resultater, f, ensure_ascii=False, indent=2)

print(f"Suksess! Lagret {len(endelige_resultater)} resultater sortert etter nyeste dato til {json_path}")
        
