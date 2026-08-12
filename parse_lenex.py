import io
import json
import os
import re
import requests
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from bs4 import BeautifulSoup


STEVNER_FIL = "stevner.txt"
JSON_DIR = "data"
JSON_PATH = os.path.join(JSON_DIR, "resultater.json")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 "
        "Chrome/124.0 Safari/537.36"
    )
}


# ---------------------------------------------------------
# HJELPEFUNKSJONER
# ---------------------------------------------------------

def parse_time_to_seconds(time_str):
    """
    Gjør svømmetid om til sekunder.

    Eksempler:
    00:28.87      -> 28.87
    01:04.32      -> 64.32
    01:02:03.45  -> 3723.45
    """

    if not time_str:
        return None

    value = str(time_str).strip().replace(",", ".")

    # Fjern tekst som DSQ/DNS osv.
    if value.upper() in {
        "NT",
        "DNS",
        "DNF",
        "DSQ",
        "DISK",
        "DQ",
    }:
        return None

    value = re.sub(r"[^\d:.]", "", value)

    if not value:
        return None

    try:
        parts = value.split(":")

        if len(parts) == 3:
            hours = float(parts[0])
            minutes = float(parts[1])
            seconds = float(parts[2])

            return (
                hours * 3600
                + minutes * 60
                + seconds
            )

        if len(parts) == 2:
            minutes = float(parts[0])
            seconds = float(parts[1])

            return (
                minutes * 60
                + seconds
            )

        return float(parts[0])

    except Exception:
        return None


def normaliser_dato(value):
    """
    Gjør ulike datoformater om til YYYY-MM-DD.
    """

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
    """
    Normaliserer klubbnavn.
    """

    klubb = (
        klubb_raw or ""
    ).lower().strip()

    navn_lower = (
        navn or ""
    ).lower().strip()

    if "varodd" in klubb:
        return "Varodd Svømmeklubb"

    if (
        "vågsbygd" in klubb
        or "vagsbygd" in klubb
    ):
        return "Vågsbygd SLK"

    return None


def finn_stevne_id(url):
    match = re.search(
        r"stevnenr=(\d+)",
        url,
        re.IGNORECASE
    )

    if match:
        return match.group(1)

    return ""


def finn_stevnedato_fra_url(url):
    """
    Fallback dersom dato ikke ligger i XML.
    """

    match = re.search(
        r"/(\d{8})",
        url
    )

    if match:
        raw = match.group(1)

        try:
            return datetime.strptime(
                raw,
                "%Y%m%d"
            ).strftime("%Y-%m-%d")
        except Exception:
            pass

    return ""


# ---------------------------------------------------------
# MEDLEY STEVNEINFO
# ---------------------------------------------------------

def les_stevneinfo(url):

    try:

        response = requests.get(
            url,
            headers=HEADERS,
            timeout=30
        )

        response.raise_for_status()

        soup = BeautifulSoup(
            response.text,
            "html.parser"
        )

        text = soup.get_text(
            " ",
            strip=True
        )

        navn = ""

        h1 = soup.find("h1")

        if h1:
            navn = h1.get_text(
                " ",
                strip=True
            )

        if not navn and soup.title:
            navn = soup.title.get_text(
                " ",
                strip=True
            )

        dato = ""

        # Medley bruker ofte:
        # Fra dato: 05.06.2026

        match = re.search(
            r"Fra dato:\s*(\d{2}\.\d{2}\.\d{4})",
            text,
            re.IGNORECASE
        )

        if match:
            dato = normaliser_dato(
                match.group(1)
            )

        if not dato:
            dato = finn_stevnedato_fra_url(
                url
            )

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
            "stevne_id": finn_stevne_id(url)
        }

    except Exception as exc:

        print(
            f"Kunne ikke lese stevneinfo: {url}"
        )

        print(
            f"Feil: {exc}"
        )

        return {
            "navn": "",
            "dato": finn_stevnedato_fra_url(url),
            "basseng": "25m",
            "stevne_id": finn_stevne_id(url)
        }


# ---------------------------------------------------------
# LENEX
# ---------------------------------------------------------

def parse_lenex(
    content,
    source_url,
    metadata=None
):

    metadata = metadata or {}

    xml_raw = None

    try:

        # Forsøk ZIP først
        try:

            with zipfile.ZipFile(
                io.BytesIO(content)
            ) as archive:

                candidates = [
                    name
                    for name in archive.namelist()
                    if name.lower().endswith(
                        (
                            ".xml",
                            ".lef",
                            ".lenex"
                        )
                    )
                ]

                if candidates:
                    xml_raw = archive.read(
                        candidates[0]
                    )

                elif archive.namelist():
                    xml_raw = archive.read(
                        archive.namelist()[0]
                    )

        except zipfile.BadZipFile:

            xml_raw = content

        if not xml_raw:
            return []

        try:

            xml_text = xml_raw.decode(
                "utf-8"
            )

        except UnicodeDecodeError:

            xml_text = xml_raw.decode(
                "iso-8859-1",
                errors="ignore"
            )

        root = ET.fromstring(
            xml_text
        )

    except Exception as exc:

        print(
            f"LENEX-feil i {source_url}: {exc}"
        )

        return []

    # -----------------------------------------------------
    # STEVNEINFO
    # -----------------------------------------------------

    meet_date = metadata.get(
        "dato",
        ""
    )

    meet_course = metadata.get(
        "basseng",
        "25m"
    )

    meet_name = metadata.get(
        "navn",
        ""
    )

    meet_id = metadata.get(
        "stevne_id",
        ""
    )

    # -----------------------------------------------------
    # Finn MEET-element
    # -----------------------------------------------------

    for elem in root.iter():

        if elem.tag.upper().endswith(
            "MEET"
        ):

            meet_name = (
                elem.attrib.get("name")
                or meet_name
            )

            raw_date = (
                elem.attrib.get("citydate")
                or elem.attrib.get("date")
                or meet_date
            )

            parsed_date = normaliser_dato(
                raw_date
            )

            if parsed_date:
                meet_date = parsed_date

            course = elem.attrib.get(
                "course"
            )

            if is_long_course(course):
                meet_course = "50m"

            break

    if not meet_date:

        meet_date = finn_stevnedato_fra_url(
            source_url
        )

    # -----------------------------------------------------
    # FINN ØVELSER
    # -----------------------------------------------------

    events = {}

    for elem in root.iter():

        if not elem.tag.upper().endswith(
            "EVENT"
        ):
            continue

        event_id = (
            elem.attrib.get("eventid")
            or elem.attrib.get("id")
            or ""
        )

        course = elem.attrib.get(
            "course"
        )

        basseng = (
            "50m"
            if is_long_course(course)
            else meet_course
        )

        distance = ""
        stroke = ""

        for child in elem.iter():

            if child.tag.upper().endswith(
                "SWIMSTYLE"
            ):

                distance = (
                    child.attrib.get(
                        "distance"
                    )
                    or ""
                )

                stroke = (
                    child.attrib.get(
                        "stroke"
                    )
                    or ""
                )

                break

        if distance and stroke:

            event_name = (
                f"{distance}m {stroke}"
            )

        else:

            event_name = (
                "Ukjent øvelse"
            )

        events[event_id] = {
            "navn": event_name,
            "basseng": basseng
        }

    # -----------------------------------------------------
    # FINN RESULTATER
    # -----------------------------------------------------

    results = []

    for club in root.iter():

        if not club.tag.upper().endswith(
            "CLUB"
        ):
            continue

        original_club = (
            club.attrib.get("name")
            or club.attrib.get("shortname")
            or ""
        )

        for athlete in club.iter():

            if not athlete.tag.upper().endswith(
                "ATHLETE"
            ):
                continue

            firstname = (
                athlete.attrib.get(
                    "firstname"
                )
                or ""
            ).strip()

            lastname = (
                athlete.attrib.get(
                    "lastname"
                )
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
                athlete.attrib.get(
                    "birthdate"
                )
                or ""
            )

            fodselsar = (
                birthdate[:4]
                if birthdate
                else ""
            )

            kjonn = (
                athlete.attrib.get(
                    "gender"
                )
                or ""
            )

            for result in athlete.iter():

                if not result.tag.upper().endswith(
                    "RESULT"
                ):
                    continue

                tid = (
                    result.attrib.get(
                        "swimtime"
                    )
                    or result.attrib.get(
                        "time"
                    )
                    or ""
                ).strip()

                if not tid:
                    continue

                seconds = parse_time_to_seconds(
                    tid
                )

                # Ikke ta med ugyldige tider
                if (
                    seconds is None
                    or seconds <= 0
                ):
                    continue

                event_id = (
                    result.attrib.get(
                        "eventid"
                    )
                    or ""
                )

                event_info = events.get(
                    event_id,
                    {
                        "navn": "Ukjent øvelse",
                        "basseng": meet_course
                    }
                )

                # -------------------------------------------------
                # FINA
                # -------------------------------------------------

                points_raw = (
                    result.attrib.get(
                        "points"
                    )
                    or result.attrib.get(
                        "fina"
                    )
                    or result.attrib.get(
                        "score"
                    )
                    or "0"
                )

                try:

                    fina = int(
                        float(points_raw)
                    )

                except Exception:

                    fina = 0

                # -------------------------------------------------
                # DATO
                # -------------------------------------------------

                result_date = (
                    result.attrib.get(
                        "date"
                    )
                    or meet_date
                )

                result_date = normaliser_dato(
                    result_date
                )

                if not result_date:
                    result_date = meet_date

                results.append({

                    "stevne": meet_name,

                    "stevne_id": (
                        meet_id
                        or finn_stevne_id(
                            source_url
                        )
                    ),

                    "dato": result_date,

                    "navn": full_name,

                    "klubb": klubbnavn,

                    "ovelse": event_info[
                        "navn"
                    ],

                    "basseng": event_info[
                        "basseng"
                    ],

                    "tid": tid,

                    "fina": fina,

                    "sekunder": seconds,

                    "fodselsar": fodselsar,

                    "kjonn": kjonn

                })

    return results


# ---------------------------------------------------------
# HENT RESULTATKILDE
# ---------------------------------------------------------

def hent_resultat(
    url,
    metadata
):

    print(
        f"  Henter resultat: {url}"
    )

    try:

        response = requests.get(
            url,
            headers=HEADERS,
            timeout=60
        )

        response.raise_for_status()

        content_type = (
            response.headers
            .get(
                "Content-Type",
                ""
            )
            .lower()
        )

        is_xml = (
            url.lower().endswith(
                (
                    ".xml",
                    ".lef",
                    ".zip",
                    ".lenex"
                )
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

        return []

    except Exception as exc:

        print(
            f"  FEIL: {exc}"
        )

        return []


# ---------------------------------------------------------
# LES STEVNER.TXT
# ---------------------------------------------------------

def les_urls():

    if not os.path.exists(
        STEVNER_FIL
    ):
        return []

    with open(
        STEVNER_FIL,
        "r",
        encoding="utf-8"
    ) as file:

        urls = []

        for line in file:

            line = line.strip()

            if not line:
                continue

            if line.startswith("#"):
                continue

            urls.append(line)

        return urls


# ---------------------------------------------------------
# 12 MÅNEDER
# ---------------------------------------------------------

def er_siste_12_maneder(
    dato,
    cutoff
):

    if not dato:
        return False

    try:

        dato_obj = datetime.strptime(
            dato,
            "%Y-%m-%d"
        ).date()

        return (
            dato_obj >= cutoff
            and dato_obj <= datetime.now().date()
        )

    except Exception:

        return False


# ---------------------------------------------------------
# BEREGN BESTE / DÅRLIGSTE
# ---------------------------------------------------------

def beregn_statistikk(
    alle_resultater
):

    """
    Viktig:

    Vi grupperer på:

    klubb
    + svømmer
    + øvelse
    + basseng

    Dermed blandes ikke 25m og 50m.
    """

    cutoff = (
        datetime.now().date()
        - timedelta(days=365)
    )

    grupper = {}

    for result in alle_resultater:

        if not result.get("sekunder"):
            continue

        if result["sekunder"] <= 0:
            continue

        if not er_siste_12_maneder(
            result.get("dato", ""),
            cutoff
        ):
            continue

        key = (
            result.get("klubb", ""),
            result.get("navn", ""),
            result.get("ovelse", ""),
            result.get("basseng", "")
        )

        grupper.setdefault(
            key,
            []
        ).append(result)

    final = []

    for key, rows in grupper.items():

        # Nyeste først
        rows.sort(
            key=lambda r: (
                r.get("dato", ""),
                r.get("sekunder", 999999)
            ),
            reverse=True
        )

        # Beste tid = laveste sekunder
        beste = min(
            rows,
            key=lambda r: r["sekunder"]
        )

        # Dårligste tid = høyeste sekunder
        darligste = max(
            rows,
            key=lambda r: r["sekunder"]
        )

        # Første registrerte resultat
        eldste = min(
            rows,
            key=lambda r: (
                r.get("dato", ""),
                r.get("sekunder", 999999)
            )
        )

        forbedring = 0

        if (
            darligste["sekunder"] > 0
            and beste["sekunder"] <
            darligste["sekunder"]
        ):

            forbedring = (
                (
                    darligste["sekunder"]
                    - beste["sekunder"]
                )
                / darligste["sekunder"]
            ) * 100

        # Kopier beste resultat som grunnobjekt
        result = dict(beste)

        result["antall_resultater"] = len(
            rows
        )

        result["beste_tid"] = (
            beste["tid"]
        )

        result["beste_sekunder"] = (
            beste["sekunder"]
        )

        result["beste_dato"] = (
            beste.get("dato", "")
        )

        result["darligste_tid"] = (
            darligste["tid"]
        )

        result["darligste_sekunder"] = (
            darligste["sekunder"]
        )

        result["darligste_dato"] = (
            darligste.get("dato", "")
        )

        result["forste_tid"] = (
            eldste["tid"]
        )

        result["forste_sekunder"] = (
            eldste["sekunder"]
        )

        result["forste_dato"] = (
            eldste.get("dato", "")
        )

        result["forbedring"] = round(
            forbedring,
            2
        )
