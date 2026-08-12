import io
import json
import os
import re
import requests
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
import pdfplumber


STEVNER_FIL = "stevner.txt"
JSON_DIR = "data"
JSON_PATH = os.path.join(JSON_DIR, "resultater.json")

KLUBBER = {
    "varodd": "Varodd Svømmeklubb",
    "vågsbygd": "Vågsbygd SLK",
    "vagsbygd": "Vågsbygd SLK",
}

OVERSTYR_TIL_VARODD = [
    "mio wesøy-danielsen",
    "luca wesøy-danielsen",
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/124.0 Safari/537.36"
    )
}


def parse_time_to_seconds(time_str):
    if not time_str:
        return None

    value = str(time_str).strip().replace(",", ".")

    # Fjern eventuelle markeringer
    value = re.sub(r"[^\d:.]", "", value)

    try:
        parts = value.split(":")

        if len(parts) == 3:
            return (
                float(parts[0]) * 3600
                + float(parts[1]) * 60
                + float(parts[2])
            )

        if len(parts) == 2:
            return float(parts[0]) * 60 + float(parts[1])

        return float(parts[0])

    except Exception:
        return None


def normaliser_dato(value):
    if not value:
        return ""

    value = str(value).strip()

    # 2026-08-12
    match = re.search(
        r"(20\d{2})[-/.](\d{1,2})[-/.](\d{1,2})",
        value
    )

    if match:
        try:
            return datetime(
                int(match.group(1)),
                int(match.group(2)),
                int(match.group(3))
            ).strftime("%Y-%m-%d")
        except Exception:
            pass

    # 12.08.2026
    match = re.search(
        r"(\d{1,2})[-/.](\d{1,2})[-/.](20\d{2})",
        value
    )

    if match:
        try:
            return datetime(
                int(match.group(3)),
                int(match.group(2)),
                int(match.group(1))
            ).strftime("%Y-%m-%d")
        except Exception:
            pass

    return ""


def is_long_course(course):
    if not course:
        return False

    value = str(course).strip().upper()

    return value in {
        "LCM",
        "50M",
        "50",
        "LCM50",
        "LANGBANE",
        "LONG COURSE",
    }


def finn_klubb(klubb_raw, navn=""):
    klubb = (klubb_raw or "").lower().strip()
    navn_lower = (navn or "").lower().strip()

    if navn_lower in OVERSTYR_TIL_VARODD:
        return "Varodd Svømmeklubb"

    if "varodd" in klubb:
        return "Varodd Svømmeklubb"

    if "vågsbygd" in klubb or "vagsbygd" in klubb:
        return "Vågsbygd SLK"

    return None


def finn_stevne_id(url):
    match = re.search(r"stevnenr=(\d+)", url, re.IGNORECASE)

    if match:
        return match.group(1)

    return ""


def les_stevneinfo(url):
    """
    Forsøker å hente stevnenavn, dato og basseng fra Medley-stevnesiden.
    """
    try:
        response = requests.get(
            url,
            headers=HEADERS,
            timeout=30
        )
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")
        text = soup.get_text(" ", strip=True)

        navn = ""

        # H1
        h1 = soup.find("h1")
        if h1:
            navn = h1.get_text(" ", strip=True)

        # Fallback: title
        if not navn and soup.title:
            navn = soup.title.get_text(" ", strip=True)

        dato = ""

        match = re.search(
            r"Fra dato:\s*(\d{2}\.\d{2}\.\d{4})",
            text,
            re.IGNORECASE
        )

        if match:
            dato = normaliser_dato(match.group(1))

        basseng = "25m"

        if re.search(
            r"Bassenglengde:\s*50m",
            text,
            re.IGNORECASE
        ):
            basseng = "50m"

        return {
            "navn": navn,
            "dato": dato,
            "basseng": basseng,
        }

    except Exception as exc:
        print(f"Kunne ikke lese stevneinfo: {url}")
        print(f"Feil: {exc}")

        return {
            "navn": "",
            "dato": "",
            "basseng": "25m",
        }


def parse_lenex(content, source_url, metadata=None):
    """
    Leser LENEX/XML eller ZIP med LENEX/XML.
    Returnerer ALLE resultater for Varodd og Vågsbygd.
    """

    metadata = metadata or {}

    xml_raw = None

    try:
        try:
            with zipfile.ZipFile(io.BytesIO(content)) as archive:

                candidates = [
                    name
                    for name in archive.namelist()
                    if name.lower().endswith(
                        (".xml", ".lef", ".lenex")
                    )
                ]

                if candidates:
                    xml_raw = archive.read(candidates[0])
                elif archive.namelist():
                    xml_raw = archive.read(archive.namelist()[0])

        except zipfile.BadZipFile:
            xml_raw = content

        if not xml_raw:
            return []

        try:
            xml_text = xml_raw.decode("utf-8")
        except UnicodeDecodeError:
            xml_text = xml_raw.decode(
                "iso-8859-1",
                errors="ignore"
            )

        root = ET.fromstring(xml_text)

    except Exception as exc:
        print(f"LENEX-feil i {source_url}: {exc}")
        return []

    # ---------------------------------------------------------
    # Stevneinformasjon
    # ---------------------------------------------------------

    meet_date = metadata.get("dato", "")
    meet_course = metadata.get("basseng", "25m")
    meet_name = metadata.get("navn", "")

    for elem in root.iter():
        if elem.tag.upper().endswith("MEET"):

            meet_date = (
                elem.attrib.get("citydate")
                or elem.attrib.get("date")
                or meet_date
            )

            meet_date = normaliser_dato(meet_date)

            if is_long_course(
                elem.attrib.get("course")
            ):
                meet_course = "50m"

            meet_name = (
                elem.attrib.get("name")
                or meet_name
            )

            break

    # ---------------------------------------------------------
    # Finn øvelser
    # ---------------------------------------------------------

    events = {}

    for elem in root.iter():

        if not elem.tag.upper().endswith("EVENT"):
            continue

        event_id = (
            elem.attrib.get("eventid")
            or elem.attrib.get("id")
            or ""
        )

        course = elem.attrib.get("course")

        basseng = (
            "50m"
            if is_long_course(course)
            else meet_course
        )

        distance = ""
        stroke = ""

        for child in elem.iter():

            if child.tag.upper().endswith("SWIMSTYLE"):

                distance = (
                    child.attrib.get("distance")
                    or ""
                )

                stroke = (
                    child.attrib.get("stroke")
                    or ""
                )

                break

        if distance and stroke:
            event_name = f"{distance}m {stroke}"
        else:
            event_name = "Ukjent øvelse"

        events[event_id] = {
            "navn": event_name,
            "basseng": basseng,
        }

    # ---------------------------------------------------------
    # Finn utøvere og resultater
    # ---------------------------------------------------------

    results = []

    for club in root.iter():

        if not club.tag.upper().endswith("CLUB"):
            continue

        original_club = (
            club.attrib.get("name")
            or club.attrib.get("shortname")
            or ""
        )

        for athlete in club.iter():

            if not athlete.tag.upper().endswith("ATHLETE"):
                continue

            firstname = (
                athlete.attrib.get("firstname")
                or ""
            ).strip()

            lastname = (
                athlete.attrib.get("lastname")
                or ""
            ).strip()

            full_name = (
                f"{firstname} {lastname}"
            ).strip()

            klubbnavn = finn_klubb(
                original_club,
                full_name
            )

            if not klubbnavn:
                continue

            birthdate = (
                athlete.attrib.get("birthdate")
                or ""
            )

            fodselsar = (
                birthdate[:4]
                if birthdate
                else ""
            )

            kjonn = (
                athlete.attrib.get("gender")
                or ""
            )

            for result in athlete.iter():

                if not result.tag.upper().endswith("RESULT"):
                    continue

                tid = (
                    result.attrib.get("swimtime")
                    or result.attrib.get("time")
                    or ""
                ).strip()

                if not tid:
                    continue

                if tid in {
                    "00:00.00",
                    "0:00.00",
                    "NT",
                    "DNS",
                    "DNF",
                    "DSQ",
                }:
                    continue

                event_id = (
                    result.attrib.get("eventid")
                    or ""
                )

                event_info = events.get(
                    event_id,
                    {
                        "navn": "Ukjent øvelse",
                        "basseng": meet_course,
                    }
                )

                points_raw = (
                    result.attrib.get("points")
                    or result.attrib.get("fina")
                    or "0"
                )

                try:
                    fina = int(float(points_raw))
                except Exception:
                    fina = 0

                result_date = (
                    result.attrib.get("date")
                    or meet_date
                )

                result_date = normaliser_dato(
                    result_date
                )

                seconds = parse_time_to_seconds(tid)

                results.append({
                    "stevne": meet_name,
                    "stevne_id": finn_stevne_id(source_url),
                    "dato": result_date,
                    "navn": full_name,
                    "klubb": klubbnavn,
                    "ovelse": event_info["navn"],
                    "basseng": event_info["basseng"],
                    "tid": tid,
                    "fina": fina,
                    "sekunder": seconds,
                    "fodselsar": fodselsar,
                    "kjonn": kjonn,
                })

    return results


def parse_html(content, source_url, metadata=None):
    """
    Fallback dersom Medley ikke tilbyr LENEX på et stevne.
    """

    metadata = metadata or {}

    try:
        soup = BeautifulSoup(
            content.decode("utf-8", errors="ignore"),
            "html.parser"
        )
    except Exception:
        return []

    results = []

    date = metadata.get("dato", "")
    course = metadata.get("basseng", "25m")
    meet_name = metadata.get("navn", "")

    current_event = "Ukjent øvelse"

    for tr in soup.find_all("tr"):

        cells = [
            td.get_text(" ", strip=True)
            for td in tr.find_all(["td", "th"])
        ]

        if not cells:
            continue

        row_text = " ".join(cells)
        row_lower = row_text.lower()

        # Forsøk å finne øvelse
        if "øvelse" in row_lower or "event" in row_lower:

            current_event = cells[0]

            if "50m" in row_lower:
                course = "50m"

            elif "25m" in row_lower:
                course = "25m"

            continue

        klubb = None

        if "varodd" in row_lower:
            klubb = "Varodd Svømmeklubb"

        elif (
            "vågsbygd" in row_lower
            or "vagsbygd" in row_lower
        ):
            klubb = "Vågsbygd SLK"

        if not klubb:
            continue

        # Finn svømmetid
        tid = ""

        for cell in cells:

            if re.match(
                r"^(\d{1,2}:)?\d{1,2}\.\d{2}$",
                cell
            ):
                tid = cell
                break

        if not tid:
            continue

        # Finn navn
        navn = ""

        for cell in cells:

            low = cell.lower()

            if (
                cell
                and cell != tid
                and "varodd" not in low
                and "vågsbygd" not in low
                and "vagsbygd" not in low
                and not cell.isdigit()
            ):
                navn = cell
                break

        if not navn:
            continue

        fina = 0

        for cell in cells:

            if cell.isdigit():

                number = int(cell)

                if 10 <= number <= 1200:
                    fina = number

        results.append({
            "stevne": meet_name,
            "stevne_id": finn_stevne_id(source_url),
            "dato": date,
            "navn": navn,
            "klubb": klubb,
            "ovelse": current_event,
            "basseng": course,
            "tid": tid,
            "fina": fina,
            "sekunder": parse_time_to_seconds(tid),
            "fodselsar": "",
            "kjonn": "",
        })

    return results


def hent_resultat(url, metadata):
    print(f"  Henter: {url}")

    try:

        response = requests.get(
            url,
            headers=HEADERS,
            timeout=60
        )

        response.raise_for_status()

        content_type = (
            response.headers
            .get("Content-Type", "")
            .lower()
        )

        is_xml = (
            url.lower().endswith(
                (".xml", ".lef", ".zip", ".lenex")
            )
            or "xml" in content_type
            or "zip" in content_type
        )

        if is_xml:
            return parse_lenex(
                response.content,
                url,
                metadata
            )

        return parse_html(
            response.content,
            url,
            metadata
        )

    except Exception as exc:

        print(
            f"  FEIL ved henting av {url}: {exc}"
        )

        return []


def les_urls():
    if not os.path.exists(STEVNER_FIL):
        return []

    with open(
        STEVNER_FIL,
        "r",
        encoding="utf-8"
    ) as file:

        return [
            line.strip()
            for line in file
            if line.strip()
            and not line.strip().startswith("#")
        ]


def beregn_forbedring(results):
    """
    Beregner forbedring for hver kombinasjon
    svømmer + øvelse + basseng.
    """

    grupper = {}

    for result in results:

        key = (
            result["navn"],
            result["klubb"],
            result["ovelse"],
            result["basseng"],
        )

        grupper.setdefault(key, []).append(result)

    final = []

    cutoff = (
        datetime.now() - timedelta(days=365)
    ).strftime("%Y-%m-%d")

    for key, rows in grupper.items():

        rows.sort(
            key=lambda x: str(x.get("dato", "")),
            reverse=True
        )

        siste_12 = [
            row
            for row in rows
            if row.get("sekunder")
            and row["sekunder"] > 0
            and str(row.get("dato", "")) >= cutoff
        ]

        for row in rows:
            row["forbedring"] = 0.0
            row["beste_tid"] = row["tid"]
            row["daarligste_tid"] = row["tid"]

        if len(siste_12) >= 2:

            best = min(
                siste_12,
                key=lambda x: x["sekunder"]
            )

            worst = max(
                siste_12,
                key=lambda x: x["sekunder"]
            )

            if worst["sekunder"] > 0:

                improvement = (
                    (
                        worst["sekunder"]
                        - best["sekunder"]
                    )
                    / worst["sekunder"]
                ) * 100

            else:
                improvement = 0

            rows[0]["forbedring"] = round(
                improvement,
                2
            )

            rows[0]["beste_tid"] = best["tid"]
            rows[0]["daarligste_tid"] = worst["tid"]

        final.append(rows[0])

    return final


def main():

    urls = les_urls()

    print("=" * 60)
    print("SvømmeTracker – resultatimport")
    print("=" * 60)
    print(f"Antall kilder: {len(urls)}")

    if not urls:
        print(
            "INGEN KILDER FUNNET I stevner.txt"
        )

        return

    all_results = []

    for url in urls:

        print()
        print(f"Behandler stevne: {url}")

        metadata = les_stevneinfo(url)

        print(
            f"  Stevne: {metadata.get('navn', '')}"
        )

        print(
            f"  Dato: {metadata.get('dato', '')}"
        )

        print(
            f"  Basseng: {metadata.get('basseng', '')}"
        )

        results = hent_resultat(
            url,
            metadata
        )

        print(
            f"  Fant {len(results)} resultater"
        )

        all_results.extend(results)

    # Fjern duplikater
    unique = {}

    for result in all_results:

        key = (
            result.get("stevne_id"),
            result.get("navn"),
            result.get("klubb"),
            result.get("ovelse"),
            result.get("basseng"),
            result.get("tid"),
            result.get("dato"),
        )

        unique[key] = result

    all_results = list(unique.values())

    # Beregn forbedring
    final_results = beregn_forbedring(
        all_results
    )

    # Sorter nyeste først
    final_results.sort(
        key=lambda x: (
            str(x.get("dato", "")),
            int(x.get("fina", 0) or 0),
        ),
        reverse=True
    )

    os.makedirs(
        JSON_DIR,
        exist_ok=True
    )

    with open(
        JSON_PATH,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            final_results,
            file,
            ensure_ascii=False,
            indent=2
        )

    print()
    print("=" * 60)
    print(
        f"Totalt importerte råresultater: "
        f"{len(all_results)}"
    )
    print(
        f"Resultater til JSON: "
        f"{len(final_results)}"
    )
    print(
        f"Lagret: {JSON_PATH}"
    )
    print("=" * 60)


if __name__ == "__main__":
    main()
