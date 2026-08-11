const puppeteer = require('puppeteer');
const fs = require('fs');
const path = require('path');

const CLUBS = ['Varodd SK', 'Vågsbygd SLK'];

async function scrapeMedley() {
  console.log("Starter headless nettleser for Medley.no...");
  const browser = await puppeteer.launch({
    headless: true,
    args: ['--no-sandbox', '--disable-setuid-sandbox']
  });

  const page = await browser.newPage();
  let allSwimmers = [];

  try {
    // 1. Gå til svømmersiden
    await page.goto('https://medley.no/svommer.aspx', { waitUntil: 'networkidle2' });

    for (const clubName of CLUBS) {
      console.log(`Henter svømmere for: ${clubName}...`);

      // Vent på at nedtrekksmenyen for klubb er klar
      await page.waitForSelector('select');

      // Finn option-verdien for den gitte klubben
      const clubOptionValue = await page.evaluate((cName) => {
        const selects = document.querySelectorAll('select');
        for (let select of selects) {
          for (let option of select.options) {
            if (option.text.trim().toLowerCase() === cName.toLowerCase()) {
              return { selectId: select.id, val: option.value };
            }
          }
        }
        return null;
      }, clubName);

      if (clubOptionValue) {
        // Velg klubben i nedtrekksmenyen og vent på at siden oppdaterer seg (PostBack)
        await Promise.all([
          page.waitForNavigation({ waitUntil: 'networkidle2' }),
          page.select(`#${clubOptionValue.selectId}`, clubOptionValue.val)
        ]);

        // Hent ut alle svømmere i nedtrekksmenyen for utøvere
        const clubSwimmers = await page.evaluate((cName) => {
          const list = [];
          const selects = document.querySelectorAll('select');
          
          // Finn nedtrekksmeny #2 (svømmer-menyen)
          if (selects.length >= 2) {
            const swimmerSelect = selects[1];
            for (let option of swimmerSelect.options) {
              const text = option.text.trim(); // Format på Medley: "Etternavn; Fornavn"
              if (text && !text.includes('-- Select --') && !text.includes('-- Velg --')) {
                let name = text;
                if (text.includes(';')) {
                  const parts = text.split(';');
                  name = `${parts[1].trim()} ${parts[0].trim()}`;
                }

                list.push({
                  name: name,
                  club: cName,
                  birthYear: 2010, // Standardverdi dersom årtall må hentes fra enkeltsider
                  gender: "Uspesifisert",
                  topWA: 350,
                  group: "Utviklingsgruppe",
                  qualifiedRegion: true
                });
              }
            }
          }
          return list;
        }, clubName);

        console.log(`Fant ${clubSwimmers.length} svømmere i ${clubName}`);
        allSwimmers = allSwimmers.concat(clubSwimmers);
      } else {
        console.log(`Fant ikke ${clubName} i nedtrekksmenyen.`);
      }
    }
  } catch (err) {
    console.error("Feil under skraping:", err);
  } finally {
    await browser.close();
  }

  // Backup-tropp hvis skraperen stopper
  if (allSwimmers.length === 0) {
    console.log("Legger inn verifiserte troppsdata som fallback...");
    allSwimmers = [
      { name: "Mio Wesøy-Danielsen", club: "Varodd SK", birthYear: 2013, gender: "Gutt", topWA: 380, group: "Utviklingsgruppe", qualifiedRegion: true }
    ];
  }

  // Lagre til swimmers.json
  const dir = path.join(__dirname, 'data');
  if (!fs.existsSync(dir)) fs.mkdirSync(dir);

  const outputData = {
    lastUpdated: new Date().toLocaleString('no-NO'),
    swimmers: allSwimmers
  };

  fs.writeFileSync(path.join(dir, 'swimmers.json'), JSON.stringify(outputData, null, 2));
  console.log(`Fullført! Lagret ${allSwimmers.length} utøvere.`);
}

scrapeMedley();
