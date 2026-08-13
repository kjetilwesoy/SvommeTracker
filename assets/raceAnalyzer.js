async function kjorAiAnalyse() {
  const athleteName = document.getElementById('aiAthlete').value;
  const stroke = document.getElementById('aiStroke').value;
  const breakout15m = document.getElementById('ai15m').value;
  
  // Hent eksisterende felt fra din kalkulator hvis du vil gjenbruke dem:
  // (F.eks distanse og bassengtype fra toppen av siden din)
  const poolLength = '25'; // eller hent fra din dropdown
  const distance = 100;

  // Samle sammen alle splitt-feltene
  const splitInputs = document.querySelectorAll('.split-input');
  const rawSplits = [];
  splitInputs.forEach(input => {
    if (input.value.trim() !== '') {
      rawSplits.push({
        distance: input.getAttribute('data-dist'),
        time: input.value.trim()
      });
    }
  });

  // Kjøre analysen
  const result = await analyzeRaceSplits({
    athleteName,
    poolLength,
    stroke,
    distance,
    breakout15m,
    rawSplits
  });

  const resultDiv = document.getElementById('aiResultArea');
  resultDiv.style.display = 'block';

  if (!result) {
    resultDiv.innerHTML = `<div class="alert alert-warning">Vennligst fyll ut minst én splitt-tid.</div>`;
    return;
  }

  // Generer HTML-visning av resultatet
  let issuesHtml = result.issues.length === 0 
    ? `<div class="alert alert-success">✅ Perfekt disponering! Ingen markante tidstap funnet.</div>`
    : result.issues.map(i => `
        <div class="alert alert-danger mb-2">
          <strong>⚠️ ${i.title} (Beregnet tidstap: -${i.lossEstimateSec}s)</strong><br>
          <small>${i.description}</small>
        </div>
      `).join('');

  let workoutsHtml = result.recommendedWorkouts.map(w => `
    <div class="card p-3 mb-2 bg-light">
      <h6 class="fw-bold text-primary mb-1">${w.title}</h6>
      <p class="small text-muted mb-2">${w.description}</p>
      <ul class="mb-0 small">
        ${w.sets.map(s => `<li>${s}</li>`).join('')}
      </ul>
    </div>
  `).join('');

  resultDiv.innerHTML = `
    <hr>
    <h5 class="fw-bold">Rapport for ${result.athleteName} - ${result.distance}m ${result.stroke}</h5>
    <p><strong>Totaltid:</strong> ${result.totalTimeFormatted}</p>
    <h6 class="fw-bold mt-3">Diagnostiserte Tidstap:</h6>
    ${issuesHtml}
    <h6 class="fw-bold mt-3">Anbefalte Treningsøkter:</h6>
    ${workoutsHtml}
  `;
}
