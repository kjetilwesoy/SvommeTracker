function parseTimeToSeconds(input) {
  if (!input) return 0;
  if (typeof input === 'number') return input;
  const str = String(input).trim();
  if (str.includes(':')) {
    const parts = str.split(':');
    return parseFloat(parts[0]) * 60 + parseFloat(parts[1]);
  }
  return parseFloat(str) || 0;
}

function formatSecondsToTime(sec) {
  if (!sec || isNaN(sec)) return '00:00.00';
  const mins = Math.floor(sec / 60);
  const remainderSecs = (sec % 60).toFixed(2);
  const formattedSecs = remainderSecs < 10 ? `0${remainderSecs}` : remainderSecs;
  return mins > 0 ? `${mins}:${formattedSecs}` : `${remainderSecs}`;
}

async function analyzeRaceSplits({ athleteName, poolLength, stroke, distance, breakout15m, rawSplits }) {
  const issues = [];

  // Hent økter fra data/workoutDatabase.json
  let workoutDatabase = [];
  try {
    const res = await fetch('./data/workoutDatabase.json');
    workoutDatabase = await res.json();
  } catch (e) {
    console.error("Kunne ikke laste workoutDatabase.json", e);
  }
  
  const parsedSplits = rawSplits
    .map(s => ({
      distance: Number(s.distance),
      timeSec: parseTimeToSeconds(s.time)
    }))
    .filter(s => s.timeSec > 0)
    .sort((a, b) => a.distance - b.distance);

  if (parsedSplits.length === 0) return null;

  const splitsWithLaps = parsedSplits.map((split, index) => {
    const prevTime = index === 0 ? 0 : parsedSplits[index - 1].timeSec;
    const prevDist = index === 0 ? 0 : parsedSplits[index - 1].distance;
    const lapTime = split.timeSec - prevTime;
    const lapDistance = split.distance - prevDist;

    return {
      ...split,
      lapTime,
      lapDistance,
      pacePer100: (lapTime / lapDistance) * 100
    };
  });

  const totalTimeSec = parsedSplits[parsedSplits.length - 1].timeSec;
  const avgSpeedMs = distance / totalTimeSec;

  // 1. Sjekk 15m start
  if (breakout15m) {
    const b15Sec = parseTimeToSeconds(breakout15m);
    if (b15Sec > 0) {
      const b15Speed = 15 / b15Sec;
      if (b15Speed < avgSpeedMs * 1.12) {
        issues.push({
          type: 'SLOW_BREAKOUT',
          title: 'Svak 15m Utgang/Start',
          lossEstimateSec: (b15Sec - (15 / (avgSpeedMs * 1.25))).toFixed(2),
          description: `15m-tiden var ${b15Sec}s. Du mister fremdrift ut fra pallen/streamlinjen.`
        });
      }
    }
  }

  // 2. Sjekk laktat/drop på siste runde
  if (splitsWithLaps.length >= 2) {
    const firstLap = splitsWithLaps[0];
    const lastLap = splitsWithLaps[splitsWithLaps.length - 1];
    const dropoffPercent = ((lastLap.lapTime - firstLap.lapTime) / firstLap.lapTime) * 100;

    if (dropoffPercent > 8) {
      issues.push({
        type: 'LACTATE_DROP',
        title: 'Markant Tempofall på Siste Lengde',
        lossEstimateSec: (lastLap.lapTime - (firstLap.lapTime * 1.04)).toFixed(2),
        description: `Siste runde gikk ${dropoffPercent.toFixed(1)}% tregere enn første runde.`
      });
    }
  }

  const recommendedWorkouts = issues
    .map(issue => workoutDatabase.find(w => w.category === issue.type))
    .filter(Boolean);

  return {
    athleteName,
    poolLength,
    stroke,
    distance,
    totalTimeFormatted: formatSecondsToTime(totalTimeSec),
    splits: splitsWithLaps,
    issues,
    recommendedWorkouts
  };
}
