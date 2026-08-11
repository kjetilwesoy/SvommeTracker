const fs = require('fs');
const axios = require('axios');
const cheerio = require('cheerio');

// KONFIGURASJON FOR REGION SØR 2025/2026 (ENKEL Å OPPDATERE)
const JUNIOR_REQUIREMENTS = {
  'G2008': 615, 'J2008': 630,
  'G2009': 615, 'J2009': 565,
  'J2010': 565,
  'G2011': 540
};

const DEVELOPMENT_SUM_REQUIREMENTS = {
  'J2013': 780,
  'G2012': 800, 'J2012': 880,
  'G2011': 900,
  'G2010': 1000
};

async function runScraper() {
  console.log("Starter scraping fra Medley.no...");

  // Eksempel på uthenging av struktur (Skraperen oppretter data mappen automatisk)
  const outputData = {
    lastUpdated: new Date().toISOString().replace('T', ' ').substring(0, 16),
    swimmers: [
      { name: "Eksempel Svømmer 1", birthYear: 2010, gender: "G", club: "Varodd SK", topWA: 510, qualifiedRegion: true, group: "Junior" },
      { name: "Eksempel Svømmer 2", birthYear: 2012, gender: "J", club: "Vågsbygd SLK", topWA: 420, qualifiedRegion: false, group: "Utvikling" }
    ]
  };

  if (!fs.existsSync('./data')) {
    fs.mkdirSync('./data');
  }

  fs.writeFileSync('./data/swimmers.json', JSON.stringify(outputData, null, 2));
  console.log("data/swimmers.json er oppdatert!");
}

runScraper();
