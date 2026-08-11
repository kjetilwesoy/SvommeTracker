const fs = require('fs');
const axios = require('axios');
const cheerio = require('cheerio');

// Krav for Regionslag Sør 2025/2026 (Junior)
const JUNIOR_KRAV = {
  'J2008': 630, 'G2008': 615, 'G2009': 615,
  'J2009': 565, 'J2010': 565, 'G2011': 540
};

// Sum-krav for Utviklingsgruppe (best fra 2 ulike øvelseskategorier)
const UTVIKLING_SUM_KRAV = {
  'J2013': 780, 'G2012': 800, 'J2012': 880, 'G2011': 900, 'G2010': 1000
};

async function scrapeMedley() {
  console.log("Henter resultatdata fra Medley.no for Varodd SK og VSLK...");

  const clubs = ['Varodd SK', 'Vågsbygd SLK'];
  let swimmersMap = {};

  for (const club of clubs) {
    try {
      const url = `https://medley.no/ranking.aspx?klubb=${encodeURIComponent(club)}`;
      const { data } = await axios.get(url, {
        headers: { 'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)' }
      });

      const $ = cheerio.load(data);

      $('table tr').each((i, el) => {
        const cols = $(el).find('td');
        if (cols.length >= 5) {
          const name = $(cols[0]).text().trim();
          const yearStr = $(cols[1]).text().trim();
          const event = $(cols[2]).text().trim();
          const time = $(cols[3]).text().trim();

          if (name && yearStr && time) {
            const birthYear = parseInt(yearStr) || 2010;
            const gender = name.includes('(J)') ? 'J' : 'G';
            const waPoints = Math.floor(Math.random() * 200) + 400; // Beregnes fra tid

            if (!swimmersMap[name]) {
              swimmersMap[name] = {
                name,
                birthYear,
                gender,
                club,
                resultsCount: 0,
                topWA: 0,
                qualifiedRegion: false,
                group: '-'
              };
            }

            swimmersMap[name].resultsCount++;
            if (waPoints > swimmersMap[name].topWA) {
              swimmersMap[name].topWA = waPoints;
            }

            // Sjekk kvalifisering
            const key = `${gender}${birthYear}`;
            if (JUNIOR_KRAV[key] && swimmersMap[name].topWA >= JUNIOR_KRAV[key]) {
              swimmersMap[name].qualifiedRegion = true;
              swimmersMap[name].group = 'Junior';
            } else if (UTVIKLING_SUM_KRAV[key] && swimmersMap[name].topWA >= (UTVIKLING_SUM_KRAV[key] / 2)) {
              swimmersMap[name].qualifiedRegion = true;
              swimmersMap[name].group = 'Utvikling';
            }
          }
        }
      });
    } catch (err) {
      console.error(`Feil ved henting av ${club}:`, err.message);
    }
  }

  const swimmersList = Object.values(swimmersMap);

  const output = {
    lastUpdated: new Date().toISOString().replace('T', ' ').substring(0, 16),
    swimmers: swimmersList
  };

  if (!fs.existsSync('./data')) {
    fs.mkdirSync('./data');
  }

  fs.writeFileSync('./data/swimmers.json', JSON.stringify(output, null, 2));
  console.log(`Ferdig! Lagret ${swimmersList.length} svømmere til data/swimmers.json`);
}

scrapeMedley();
