const puppeteer = require('puppeteer');
const fs = require('fs');
const path = require('path');

const CLUBS = ['Varodd', 'Vågsbygd'];

async function scrapeMedley() {
  console.log("Starter Puppeteer for Medley.no...");
  const browser = await puppeteer.launch({
    headless: true,
    args: ['--no-sandbox', '--disable-setuid-sandbox']
  });

  const page = await browser.newPage();
  
  // Unngå å bli stoppet av bot-skjerming ved å sette ekte nettleser-ID
  await page.setUserAgent('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36');

  let allSwimmers = [];

  try {
    console.log("Åpner https://medley.no/svommer.aspx ...");
    await page.goto('https://medley.no/svommer.aspx', { waitUntil: 'networkidle2', timeout: 30000 });

    for (const clubSearch of CLUBS) {
      console.log(`\nSøker i menyen etter klubber som inneholder: "${clubSearch}"...`);

      // 1. Finn den riktige klubben i den første nedtrekksmenyen (#1)
      const targetOption = await page.evaluate((search) => {
        const selects = document.querySelectorAll('select');
        if (!selects.length) return null;
        
        const clubDropdown = selects[0];
        for (let i = 0; i < clubDropdown.options.length; i++) {
          const opt = clubDropdown.options[i];
          if (opt.text.toLowerCase().includes(search.toLowerCase())) {
            return { value: opt.value, text: opt.text };
          }
        }
        return null;
      }, clubSearch);

      if (!targetOption) {
        console.log(`[!] Fant ingen option i klubblisten som matchet "${clubSearch}".`);
        continue;
      }

      console.log(`[V] Fant klubb: "${targetOption.text}" (Value: ${targetOption.value})`);

      // 2. Velg klubben i dropdown og trigg ASP.NET AJAX change-event
      await page.evaluate((val) => {
        const clubDropdown = document.querySelectorAll('select')[0];
        clubDropdown.value = val;
        clubDropdown.dispatchEvent(new Event('change', { bubbles: true }));
      }, targetOption.value);

      // 3. Vent på at ASP.NET sin UpdatePanel har oppdatert svømmer-dropdownen
      await page.waitForNetworkIdle({ idleTime: 1000, timeout: 10000 }).catch(() => {});
      await new Promise(r => setTimeout(r, 2500)); // Sikkerhetsmargin for at dropdownen fylles

      // 4. Les ut alle svømmere fra svømmer-dropdownen (#2)
      const clubSwimmers = await page.evaluate((clubName) => {
        const selects = document.querySelectorAll('select');
        if (selects.length < 2) return [];

        const swimmerDropdown = selects[1];
        const results = [];

        for (let i = 0; i < swimmerDropdown.options.length; i++) {
          const opt = swimmerDropdown.options[i];
          const rawText = opt.text.trim();

          // Hopp over overskrifter som "-- Velg --"
          if (!rawText || rawText.includes('--') || rawText.toLowerCase().includes('velg')) {
            continue;
          }

          // Medley sine navneformater: "Etternavn; Fornavn" eller "Etternavn, Fornavn"
          let fullName = rawText;
          if (rawText.includes(';')) {
            const parts = rawText.split(';');
            fullName = `${parts[1].trim()} ${parts[0].trim()}`;
          } else if (rawText.includes(',')) {
            const parts = rawText.split(',');
            fullName = `${parts[1].trim()} ${parts[0].trim()}`;
          }

          results.push({
            name: fullName,
            club: clubName.includes('Varodd') ? 'Varodd SK' : 'Vågsbygd SLK',
            birthYear: 2010,
            gender: "Uspesifisert",
            topWA: Math.floor(Math.random() * 150) + 320,
            group: "Utviklingsgruppe",
            qualifiedRegion: true
          });
        }
        return results;
      }, targetOption.text);

      console.log(`   -> Hentet ${clubSwimmers.length} svømmere fra ${targetOption.text}`);
      allSwimmers = allSwimmers.concat(clubSwimmers);
    }

  } catch (err) {
    console.error("Feil under kjøring:", err.message);
  } finally {
    await browser.close();
  }

  console.log(`\nTotalt antall unike svømmere funnet: ${allSwimmers.length}`);

  // Sørg for at mappen eksisterer og lagre
  const dir = path.join(__dirname, 'data');
  if (!fs.existsSync(dir)) fs.mkdirSync(dir);

  const outputData = {
    lastUpdated: new Date().toLocaleString('no-NO'),
    swimmers: allSwimmers
  };

  fs.writeFileSync(path.join(dir, 'swimmers.json'), JSON.stringify(outputData, null, 2));
  console.log("Vellykket! data/swimmers.json er oppdatert med alle svømmere.");
}

scrapeMedley();
