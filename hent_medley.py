import re
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from urllib.parse import urljoin


MEDLEY_BASE = "https://livetiming.medley.no"

STEVNEOVERSIKT = (
    f"{MEDLEY_BASE}/default.aspx"
)

STEVNER_FIL = "stevner.txt"


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36"
    )
}


# ============================================================
# HENT SIDE
# ============================================================

def hent(url):

    response = requests.get(
        url,
        headers=HEADERS,
        timeout=60
    )

    response.raise_for_status()

    response.encoding = (
        response.apparent_encoding
        or "utf-8"
    )

    return response.text


# ============================================================
# DATO
# ============================================================

def normaliser_dato(value):

    if not value:
        return ""

    match = re.search(
        r"(\d{1,2})[./-](\d{1,2})[./-](20\d{2})",
        str(value)
    )

    if not match:
        return ""

    try:

        dato = datetime(
            int(match.group(3)),
            int(match.group(2)),
            int(match.group(1))
        )

        return dato.strftime(
            "%Y-%m-%d"
        )

    except ValueError:

        return ""


# ============================================================
# STEVNE-ID
# ============================================================

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
# FINN RESULTATKILDER
# ============================================================

def finn_resultatkilder(
    soup
):

    resultater = []

    for link in soup.find_all(
        "a",
        href=True
    ):

        text = link.get_text(
            " ",
            strip=True
        )

        href = link.get(
            "href",
            ""
        )

        combined = (
            f"{text} {href}"
        ).lower()

        absolute = urljoin(
            MEDLEY_BASE,
            href
        )

        # Medley kan bruke forskjellige
        # navn på eksport/resultat.

        if (

            ".lef" in combined

            or ".lenex" in combined

            or ".xml" in combined

            or "eksport.aspx" in combined

            or "klubbeksport" in combined

            or (
                "lenex" in combined
                and (
                    "result" in combined
                    or "export" in combined
                )
            )
        ):

            if absolute not in resultater:

                resultater.append(
                    absolute
                )

    return resultater


# ============================================================
# FINN STEVNER SISTE 12 MÅNEDER
# ============================================================

def finn_stevner():

    print("=" * 70)

    print(
        "MEDLEY – FINNER STEVNER "
        "SISTE 12 MÅNEDER"
    )

    print("=" * 70)

    html = hent(
        STEVNEOVERSIKT
    )

    soup = BeautifulSoup(
        html,
        "html.parser"
    )

    today = datetime.now().date()

    cutoff = (
        today
        - timedelta(
            days=365
        )
    )

    stevner = {}

    # --------------------------------------------------------
    # FINN STEVNEDETALJER
    # --------------------------------------------------------

    for link in soup.find_all(
        "a",
        href=True
    ):

        href = link.get(
            "href",
            ""
        )

        if (
            "stevnenr="
            not in href.lower()
        ):

            continue

        stevne_id = finn_stevne_id(
            href
        )

        if not stevne_id:
            continue

        absolute = urljoin(
            MEDLEY_BASE,
            href
        )

        if (
            "stevnedetaljer.aspx"
            not in absolute.lower()
        ):

            continue

        stevner[
            stevne_id
        ] = absolute

    print(
        f"Fant {len(stevner)} "
        "stevner i Medley-oversikten."
    )

    aktuelle = []

    # --------------------------------------------------------
    # LES HVERT STEVNE
    # --------------------------------------------------------

    for stevne_id, detail_url in stevner.items():

        try:

            detail_html = hent(
                detail_url
            )

            soup = BeautifulSoup(
                detail_html,
                "html.parser"
            )

            text = soup.get_text(
                " ",
                strip=True
            )

            match = re.search(
                r"Fra dato:\s*(\d{1,2}\.\d{1,2}\.20\d{2})",
                text,
                re.IGNORECASE
            )

            if not match:
                continue

            start_date = normaliser_dato(
                match.group(1)
            )

            if not start_date:
                continue

            date_obj = datetime.strptime(
                start_date,
                "%Y-%m-%d"
            ).date()

            # Fremtidige stevner skal ikke med.

            if date_obj > today:
                continue

            # Eldre enn 12 måneder skal ikke med.

            if date_obj < cutoff:
                continue

            h1 = soup.find(
                "h1"
            )

            if h1:

                name = h1.get_text(
                    " ",
                    strip=True
                )

            elif soup.title:

                name = soup.title.get_text(
                    " ",
                    strip=True
                )

            else:

                name = (
                    f"Stevne {stevne_id}"
                )

            basseng = "25m"

            if re.search(
                r"Bassenglengde:\s*50m",
                text,
                re.IGNORECASE
            ):

                basseng = "50m"

            sources = finn_resultatkilder(
                soup
            )

            if not sources:

                print(
                    f"  ADVARSEL: Ingen "
                    f"resultatkilde: "
                    f"{name} "
                    f"({stevne_id})"
                )

                continue

            for source in sources:

                aktuelle.append({

                    "id":
                        stevne_id,

                    "navn":
                        name,

                    "dato":
                        start_date,

                    "basseng":
                        basseng,

                    "url":
                        source
                })

            print(
                f"  OK {start_date} | "
                f"{name} | "
                f"{basseng} | "
                f"{len(sources)} kilde(r)"
            )

        except Exception as exc:

            print(
                f"  FEIL ved stevne "
                f"{stevne_id}: "
                f"{exc}"
            )

    return aktuelle


# ============================================================
# SKRIV STEVNER.TXT
# ============================================================

def skriv_stevner(
    stevner
):

    urls = []

    for stevne in stevner:

        url = stevne[
            "url"
        ]

        if url not in urls:

            urls.append(
                url
            )

    # --------------------------------------------------------
    # SIKKERHET
    #
    # Hvis Medley ikke gir noen kilder,
    # skal vi IKKE tømme stevner.txt.
    # --------------------------------------------------------

    if not urls:

        raise SystemExit(
            "Ingen resultatkilder ble funnet. "
            "stevner.txt blir IKKE overskrevet."
        )

    with open(
        STEVNER_FIL,
        "w",
        encoding="utf-8"
    ) as file:

        file.write(
            "# Automatisk generert "
            "av hent_medley.py\n"
        )

        file.write(
            "# Medley resultatkilder "
            "siste 12 måneder\n"
        )

        file.write(
            "#\n"
        )

        for url in urls:

            file.write(
                url
                + "\n"
            )

    print()

    print(
        f"Skrev {len(urls)} "
        f"resultatkilder til "
        f"{STEVNER_FIL}"
    )


# ============================================================
# MAIN
# ============================================================

def main():

    stevner = finn_stevner()

    skriv_stevner(
        stevner
    )

    print()

    print(
        f"Aktuelle stevnekilder: "
        f"{len(stevner)}"
    )


if __name__ == "__main__":

    main()
