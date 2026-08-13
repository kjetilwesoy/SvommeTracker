import io
import json
import os
import re
import zipfile
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from bs4 import BeautifulSoup


STEVNER_FIL = "stevner.txt"
JSON_PATH = "data/resultater.json"
BASE = "https://livetiming.medley.no"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36"
    )
}


# ============================================================
# HJELPEFUNKSJONER
# ============================================================

def tag(element):
    """
    Fjerner XML namespace og returnerer elementnavnet.
    """
    return element.tag.rsplit("}", 1)[-1].upper()


def attr(element, *names):
    """
    Henter første eksisterende attributt fra XML-elementet.
    """
    if element is None:
        return ""

    for name in names:
        value = element.attrib.get(name)

        if value not in (None, ""):
            return str(value).strip()

    return ""


def parse_time(value):
    """
    Gjør svømmetid om til sekunder.

    Eksempler:
    00:28.87 -> 28.87
    01:04.32 -> 64.32
    01:02:03.45 -> 3723.45
    """

    if not value:
        return None

    value = str(value).strip().replace(",", ".")

    if value.upper() in {
        "NT",
        "DNS",
        "DNF",
        "DSQ",
        "DQ",
        "DISK",
        ""
    }:
        return None

    value = re.sub(
        r"[^0-9:.]",
        "",
        value
    )

    try:
        parts = value.split(":")

        if len(parts) == 3:
            return (
                float(parts[0]) * 3600
                + float(parts[1]) * 60
                + float(parts[2])
            )

        if len(parts) == 2:
            return (
                float(parts[0]) * 60
                + float(parts[1])
            )

        return float(parts[0])

    except Exception:
        return None


def normaliser_dato(value):
    """
    Gjør dato om til YYYY-MM-DD.
    """

    if not value:
        return ""

    value = str(value).strip()

    patterns = [
        (
            r"(20\d{2})[-/.](\d{1,2})[-/.](\d{1,2})",
            "ymd"
        ),
        (
            r"(\d{1,2})[-/.](\d{1,2})[-/.](20\d{2})",
            "dmy"
        )
    ]

    for pattern, order in patterns:

        match = re.search(
            pattern,
            value
        )

        if not match:
            continue

        try:

            if order == "ymd":

                dato = datetime(
                    int(match.group(1)),
                    int(match.group(2)),
                    int(match.group(3))
                )

            else:

                dato = datetime(
                    int(match.group(3)),
                    int(match.group(2)),
                    int(match.group(1))
                )

            return dato.strftime(
                "%Y-%m-%d"
            )

        except ValueError:
            pass

    return ""


def finn_klubb(value):
    """
    Normaliserer klubbnavn.

    Alt som inneholder Varodd
    blir Varodd Svømmeklubb.

    Alt som inneholder Vågsbygd/Vagsbygd
    blir Vågsbygd SLK.
    """

    value = (
        value or ""
    ).lower()

    if "varodd" in value:
        return "Varodd Svømmeklubb"

    if (
        "vågsbygd" in value
        or "vagsbygd" in value
    ):
        return "Vågsbygd SLK"

    return ""


def finn_stevne_id(url):
    match = re.search(
        r"stevnenr=(\d+)",
        url or "",
        re.IGNORECASE
    )

    if match:
        return match.group(1)

    return ""


# ============================================================
# MEDLEY STEVNEINFO
# ============================================================

def hent_stevneinfo(url):

    info = {
        "navn": "",
        "dato": "",
        "basseng": "25m",
        "stevne_id": finn_stevne_id(url)
    }

    try:

        response = requests.get(
            url,
            headers=HEADERS,
            timeout=40
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

        h1 = soup.find("h1")

        if h1:

            info["navn"] = h1.get_text(
                " ",
                strip=True
            )

        elif soup.title:

            info["navn"] = soup.title.get_text(
                " ",
                strip=True
            )

        match = re.search(
            r"Fra dato:\s*(\d{1,2}\.\d{1,2}\.20\d{2})",
            text,
            re.IGNORECASE
        )

        if match:

            info["dato"] = normaliser_dato(
                match.group(1)
            )

        if re.search(
            r"Bassenglengde:\s*50m",
            text,
            re.IGNORECASE
        ):

            info["basseng"] = "50m"

    except Exception as exc:

        print(
            f"    Kunne ikke lese stevneinfo: {exc}"
        )

    return info


# ============================================================
# XML / ZIP
# ============================================================

def hent_xml_bytes(content):

    # Medley kan levere ZIP selv om
    # Content-Type ikke sier ZIP.

    if content[:2] == b"PK":

        try:

            with zipfile.ZipFile(
                io.BytesIO(content)
            ) as archive:

                files = [
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

                if files:

                    return archive.read(
                        files[0]
                    )

        except zipfile.BadZipFile:

            pass

    return content


# ============================================================
# LENEX-PARSER
# ============================================================

def parse_lenex(
    content,
    source_url,
    metadata
):

    try:

        xml_content = hent_xml_bytes(
            content
        )

        root = ET.fromstring(
            xml_content
        )

    except Exception as exc:

        print(
            f"    XML/LENEX-feil: {exc}"
        )

        return []

    # --------------------------------------------------------
    # STEVNEINFO
    # --------------------------------------------------------

    meet = None

    for element in root.iter():

        if tag(element) == "MEET":

            meet = element
            break

    meet_name = metadata.get(
        "navn",
        ""
    )

    meet_date = metadata.get(
        "dato",
        ""
    )

    meet_course = metadata.get(
        "basseng",
        "25m"
    )

    if meet is not None:

        meet_name = (
            attr(
                meet,
                "name"
            )
            or meet_name
        )

        xml_date = normaliser_dato(
            attr(
                meet,
                "date",
                "citydate"
            )
        )

        if xml_date:
            meet_date = xml_date

        course = attr(
            meet,
            "course"
        ).upper()

        if course in {
            "LCM",
            "50M",
            "50"
        }:

            meet_course = "50m"

    # --------------------------------------------------------
    # FINN DATO FRA SESSION HVIS NØDVENDIG
    # --------------------------------------------------------

    if not meet_date:

        for element in root.iter():

            if tag(element) != "SESSION":
                continue

            session_date = normaliser_dato(
                attr(
                    element,
                    "date"
                )
            )

            if session_date:

                meet_date = session_date
                break

    # --------------------------------------------------------
    # FINN ALLE ØVELSER
    # --------------------------------------------------------

    events = {}

    for element in root.iter():

        if tag(element) != "EVENT":
            continue

        event_id = attr(
            element,
            "eventid",
            "id"
        )

        if not event_id:
            continue

        swimstyle = None

        for child in element.iter():

            if tag(child) == "SWIMSTYLE":

                swimstyle = child
                break

        distance = ""

        stroke = ""

        if swimstyle is not None:

            distance = attr(
                swimstyle,
                "distance"
            )

            stroke = attr(
                swimstyle,
                "stroke"
            )

        if distance and stroke:

            event_name = (
                f"{distance}m {stroke}"
            )

        else:

            event_name = (
                "Ukjent øvelse"
            )

        course = attr(
            element,
            "course"
        )

        if not course:

            course = meet_course

        course = course.upper()

        if course in {
            "LCM",
            "50M",
            "50"
        }:

            basseng = "50m"

        else:

            basseng = "25m"

        events[event_id] = {
            "navn": event_name,
            "basseng": basseng
        }

    print(
        f"    Fant {len(events)} øvelser i LENEX"
    )

    # --------------------------------------------------------
    # FINN RESULTATER
    #
    # LENEX:
    #
    # CLUB
    #   ATHLETE
    #     RESULTS
    #       RESULT
    #
    # RESULT peker til EVENT med eventid.
    # --------------------------------------------------------

    rows = []

    for club in root.iter():

        if tag(club) != "CLUB":
            continue

        club_name = attr(
            club,
            "name",
            "shortname",
            "code"
        )

        klubb = finn_klubb(
            club_name
        )

        if not klubb:
            continue

        for athlete in club.iter():

            if tag(athlete) != "ATHLETE":
                continue

            firstname = attr(
                athlete,
                "firstname"
            )

            lastname = attr(
                athlete,
                "lastname"
            )

            name = (
                f"{firstname} {lastname}"
            ).strip()

            if not name:
                continue

            birthdate = attr(
                athlete,
                "birthdate"
            )

            gender = attr(
                athlete,
                "gender"
            )

            for result in athlete.iter():

                if tag(result) != "RESULT":
                    continue

                swimtime = attr(
                    result,
                    "swimtime",
                    "time"
                )

                seconds = parse_time(
                    swimtime
                )

                if (
                    seconds is None
                    or seconds <= 0
                ):
                    continue

                event_id = attr(
                    result,
                    "eventid"
                )

                event = events.get(
                    event_id,
                    {
                        "navn": "Ukjent øvelse",
                        "basseng": meet_course
                    }
                )

                points = attr(
                    result,
                    "points",
                    "fina",
                    "score"
                )

                try:

                    fina = (
                        int(
                            float(points)
                        )
                        if points
                        else 0
                    )

                except ValueError:

                    fina = 0

                result_date = normaliser_dato(
                    attr(
                        result,
                        "date"
                    )
                )

                if not result_date:

                    result_date = meet_date

                rows.append({

                    "stevne": meet_name,

                    "stevne_id": (
                        metadata.get(
                            "stevne_id"
                        )
                        or finn_stevne_id(
                            source_url
                        )
                    ),

                    "dato": result_date,

                    "navn": name,

                    "klubb": klubb,

                    "ovelse": event[
                        "navn"
                    ],

                    "basseng": event[
                        "basseng"
                    ],

                    "tid": swimtime,

                    "fina": fina,

                    "sekunder": round(
                        seconds,
                        3
                    ),

                    "fodselsar": (
                        birthdate[:4]
                        if birthdate
                        else ""
                    ),

                    "kjonn": gender
                })

    print(
        f"    Fant {len(rows)} gyldige "
        "resultater for Varodd/Vågsbygd"
    )

    return rows


# ============================================================
# HENT RESULTAT
# ============================================================

def hent_resultat(url):

    print(
        f"  Henter: {url}"
    )

    metadata = hent_stevneinfo(
        url
    )

    try:

        response = requests.get(
            url,
            headers=HEADERS,
            timeout=90
        )

        response.raise_for_status()

        rows = parse_lenex(
            response.content,
            url,
            metadata
        )

        if rows:

            return rows

        # ----------------------------------------------------
        # FALLBACK
        #
        # Dersom eksport.aspx returnerer HTML
        # med en lenke til XML/LENEX.
        # ----------------------------------------------------

        soup = BeautifulSoup(
            response.content,
            "html.parser"
        )

        for link in soup.find_all(
            "a",
            href=True
        ):

            href = link[
                "href"
            ]

            lower = href.lower()

            if not any(
                x in lower
                for x in (
                    ".xml",
                    ".lef",
                    ".lenex",
                    "eksport"
                )
            ):

                continue

            if href.startswith("http"):

                target = href

            elif href.startswith("/"):

                target = (
                    BASE
                    + href
                )

            else:

                target = (
                    BASE
                    + "/"
                    + href
                )

            try:

                fallback = requests.get(
                    target,
                    headers=HEADERS,
                    timeout=90
                )

                fallback.raise_for_status()

                rows = parse_lenex(
                    fallback.content,
                    target,
                    metadata
                )

                if rows:

                    return rows

            except Exception as exc:

                print(
                    f"    Fallback feilet: {exc}"
                )

    except Exception as exc:

        print(
            f"    FEIL: {exc}"
        )

    return []


# ============================================================
# LES STEVNER.TXT
# ============================================================

def les_urls():

    if not os.path.exists(
        STEVNER_FIL
    ):

        return []

    urls = []

    with open(
        STEVNER_FIL,
        encoding="utf-8"
    ) as file:

        for line in file:

            line = line.strip()

            if not line:
                continue

            if line.startswith("#"):
                continue

            if not line.startswith("http"):
                continue

            if line not in urls:

                urls.append(
                    line
                )

    return urls


# ============================================================
# FJERN DUPLIKATER
# ============================================================

def deduplicate(rows):

    seen = set()

    result = []

    for row in rows:

        key = (

            row.get(
                "stevne_id"
            ),

            row.get(
                "dato"
            ),

            row.get(
                "navn"
            ),

            row.get(
                "klubb"
            ),

            row.get(
                "ovelse"
            ),

            row.get(
                "basseng"
            ),

            row.get(
                "tid"
            )
        )

        if key in seen:
            continue

        seen.add(key)

        result.append(
            row
        )

    return result


# ============================================================
# 12 MÅNEDER
# ============================================================

def dato_i_12_maneder(
    dato,
    cutoff,
    today
):

    try:

        date_obj = datetime.strptime(
            dato,
            "%Y-%m-%d"
        ).date()

        return (
            cutoff
            <= date_obj
            <= today
        )

    except Exception:

        return False


# ============================================================
# BESTE / DÅRLIGSTE / FØRSTE
# ============================================================

def legg_til_statistikk(
    rows
):

    today = datetime.now().date()

    cutoff = (
        today
        - timedelta(
            days=365
        )
    )

    grupper = {}

    # --------------------------------------------------------
    # GRUPPER:
    #
    # klubb
    # svømmer
    # øvelse
    # basseng
    #
    # Dermed blandes ikke:
    #
    # 25m og 50m
    # 50 fri og 100 fri
    # forskjellige svømmere
    # --------------------------------------------------------

    for row in rows:

        if not dato_i_12_maneder(
            row.get(
                "dato",
                ""
            ),
            cutoff,
            today
        ):

            continue

        key = (

            row.get(
                "klubb",
                ""
            ),

            row.get(
                "navn",
                ""
            ),

            row.get(
                "ovelse",
                ""
            ),

            row.get(
                "basseng",
                ""
            )
        )

        grupper.setdefault(
            key,
            []
        ).append(
            row
        )

    final_rows = []

    for key, gruppe in grupper.items():

        # Beste tid = lavest tid
        beste = min(
            gruppe,
            key=lambda x: x[
                "sekunder"
            ]
        )

        # Dårligste tid = høyest tid
        darligste = max(
            gruppe,
            key=lambda x: x[
                "sekunder"
            ]
        )

        # Første registrerte resultat
        forste = min(
            gruppe,
            key=lambda x:
            x.get(
                "dato",
                "9999-99-99"
            )
        )

        # ----------------------------------------------------
        # FORBEDRING
        #
        # Eksempel:
        #
        # Dårligste: 1:10.00
        # Beste:     1:05.00
        #
        # (7
