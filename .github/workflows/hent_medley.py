import json
import os
import requests
from bs4 import BeautifulSoup

# Liste over stevne-URL-er du ønsker å hente data fra
STEVNE_URLER = [
    "https://livetiming.medley.no/rapport.aspx?stevnenr=1234&rs=R"  # Bytt ut/legg til URL-er
]

JSON_FILSTI = "data/resultater.json"

def last_eksisterende_data():
    if os.path.exists(JSON_FILSTI):
        try:
            with open(JSON_FILSTI, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return []
    return []

def skrap_stevne(url):
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        resp = requests.get(url, headers=headers)
        resp.encoding = 'utf-8'
        if resp.status_code != 200:
            return []
    except Exception as e:
        print(f"Feil ved henting av {url}: {e}")
        return []

    soup = BeautifulSoup(resp.text, 'html.parser')
    nye_resultater = []
    nuvaerende_ovelse = "Ukjent øvelse"
    nuvaerende_basseng = "25m"

    for tr in soup.find_all('tr'):
        tekst = tr.get_text().strip()
        
        if "Øvelse" in tekst:
            nuvaerende_ovelse = tekst.split('\n')[0].strip()
            nuvaerende_basseng = "50m" if "50m" in tekst.lower() and "bane" in tekst.lower() else "25m"
            continue

        tds = tr.find_all('td')
        if len(tds) >= 5:
            kol = [td.get_text().strip() for td in tds]
            if kol[0].isdigit():
                navn = kol[1]
                klubb = kol[3] if len(kol) > 3 else ""
                tid = kol[-2] if len(kol) >= 6 else kol[-1]
                
                fina_poeng = 0
                for item in kol:
                    if item.isdigit() and 50 <= int(item) <= 1200:
                        fina_poeng = int(item)

                nye_resultater.append({
                    "dato": "2026-08-12",
                    "navn": navn,
                    "klubb": klubb,
                    "ovelse": nuvaerende_ovelse,
                    "basseng": nuvaerende_basseng,
                    "tid": tid,
                    "fina": fina_poeng
                })
    return nye_resultater

def main():
    eksisterende = last_eksisterende_data()
    
    # Bruk en 'set' for å unngå duplikater basert på unik nøkkel
    eksisterende_nokler = {
        (r.get('navn'), r.get('ovelse'), r.get('tid'), r.get('dato')) 
        for r in eksisterende
    }

    totalt_nye = 0
    for url in STEVNE_URLER:
        hentet = skrap_stevne(url)
        for res in hentet:
            nokkel = (res['navn'], res['ovelse'], res['tid'], res['dato'])
            if nokkel not in eksisterende_nokler:
                eksisterende.append(res)
                eksisterende_nokler.add(nokkel)
                totalt_nye += 1

    if totalt_nye > 0:
        os.makedirs(os.path.dirname(JSON_FILSTI), exist_ok=True)
        with open(JSON_FILSTI, 'w', encoding='utf-8') as f:
            json.dump(eksisterende, f, ensure_ascii=False, indent=2)
        print(f"Lagt til {totalt_nye} nye resultater i {JSON_FILSTI}")
    else:
        print("Ingen nye resultater å legge til.")

if __name__ == "__main__":
    main()
          
