import re
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from urllib.parse import urljoin


MEDLEY_BASE = "https://livetiming.medley.no"

STEVNEOVERSIKT = (
    "https://livetiming.medley.no/default.aspx"
)

STEVNER_FIL = "stevner.txt"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/124.0 Safari/537.36"
    )
}


def hent(url):

    response = requests.get(
        url,
        headers=HEADERS,
        timeout=60
    )

    response.raise_for_status()

    response.encoding = "utf-8"

    return response.text


def normaliser_dato(value):

    if not value:
        return ""

    value = value.strip()

    match = re.search(
        r"(\d{1,2})[./-](\d{1,2})[./-](20\d{2})",
        value
    )

    if not match:
        return ""

    try:

        dato = datetime(
            int(match.group(3)),
            int(match.group(2)),
            int(match.group(1))
        )

        return dato.strftime("%Y-%m-%d")

    except Exception:
        return ""


def finn_stevne_id(url):

    match = re.search(
        r"stevnenr=(\d+)",
        url,
        re.IGNORECASE
    )

    return (
        match.group(1)
        if match
        else ""
    )


def finn_stevner():

    print()
    print("=" * 60)
    print("MEDLEY – finner stevner")
    print("=" * 60)

    html = hent(STEVNEOVERSIKT)

    soup = BeautifulSoup(
        html,
        "html.parser"
    )

    today = datetime.now().date()

    cutoff = today - timedelta(
        days=365
    )

    funnet = {}

    # Finn alle lenker som inneholder stevnenr
    for link in soup.find_all("a"):

        href = link.get("href", "")

        if "stevnenr=" not in href.lower():
            continue

        stevne_id = finn_stevne_id(href)

        if not stevne_id:
            continue

        absolute = urljoin(
            MEDLEY_BASE,
            href
        )

        # Vi vil ha selve detaljsiden
        if (
            "stevnedetaljer.aspx"
            not in absolute.lower()
        ):
            continue

        funnet[stevne_id] = absolute

    print(
        f"Fant {len(funnet)} stevner/lenker "
        "i Medley-oversikten."
    )

    aktuelle = []

    for stevne_id, detail_url in funnet.items():

        try:

            detail_html = hent(
                detail_url
            )

            detail_soup = BeautifulSoup(
                detail_html,
                "html.parser"
            )

            text = detail_soup.get_text(
                " ",
                strip=True
            )

            # Dato
            match = re.search(
                r"Fra dato:\s*(\d{2}\.\d{2}\.\d{4})",
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

            # Ikke fremtidige stevner
            if date_obj > today:
                continue

            # Ikke eldre enn 12 måneder
            if date_obj < cutoff:
                continue

            # Stevnenavn
            name = ""

            h1 = detail_soup.find("h1")

            if h1:
                name = h1.get_text(
                    " ",
                    strip=True
                )

            if not name and detail_soup.title:
                name = detail_soup.title.get_text(
                    " ",
                    strip=True
                )

            # Basseng
            course = "25m"

            if re.search(
                r"Bassenglengde:\s*50m",
                text,
                re.IGNORECASE
            ):
                course = "50m"

            # Finn best mulig resultatkilde
            result_urls = finn_resultatkilder(
                detail_soup
            )

            if not result_urls:
                print(
                    f"  ADVARSEL: Ingen resultatkilde "
                    f"funnet for {name} ({stevne_id})"
                )

                continue

            for result_url in result_urls:

                aktuelle.append({
                    "id": stevne_id,
                    "navn": name,
                    "dato": start_date,
                    "basseng": course,
                    "url": result_url,
                })

            print(
                f"  OK {start_date} | "
                f"{name} | "
                f"{course} | "
                f"{len(result_urls)} kilde(r)"
            )

        except Exception as exc:

            print(
                f"  FEIL ved stevne "
                f"{stevne_id}: {exc}"
            )

    return aktuelle


def finn_resultatkilder(soup):

    resultater = []

    for link in soup.find_all("a"):

        text = link.get_text(
            " ",
            strip=True
        )

        href = link.get(
            "href",
            ""
        )

        if not href:
            continue

        combined = (
            f"{text} {href}"
        ).lower()

        absolute = urljoin(
            MEDLEY_BASE,
            href
        )

        # Førstevalg: LENEX-resultater
        if (
            "lenex" in combined
            and "result" in combined
        ):
            resultater.append(
                absolute
            )
            continue

        # Klubbeksport kan også inneholde resultatdata
        if "klubbeksport" in combined:

            resultater.append(
                absolute
            )

    # Fjern duplikater
    unike = []

    for url in resultater:

        if url not in unike:
            unike.append(url)

    return unike


def skriv_stevner(stevner):

    # Vi skriver kun resultatkildene.
    # parse_lenex.py bruker disse.
    urls = []

    for stevne in stevner:

        url = stevne["url"]

        if url not in urls:
            urls.append(url)

    with open(
        STEVNER_FIL,
        "w",
        encoding="utf-8"
    ) as file:

        file.write(
            "# Automatisk generert av hent_medley.py\n"
        )

        file.write(
            "# Resultatkilder fra Medley siste 12 måneder\n"
        )

        for url in urls:
            file.write(
                url + "\n"
            )

    print()
    print(
        f"Skrev {len(urls)} resultatkilder "
        f"til {STEVNER_FIL}"
    )


def main():

    stevner = finn_stevner()

    skriv_stevner(
        stevner
    )

    print()
    print("=" * 60)
    print(
        f"Aktuelle stevner: {len(stevner)}"
    )
    print("=" * 60)


if __name__ == "__main__":
    main()
