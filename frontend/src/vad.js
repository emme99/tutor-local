// VAD a energia: ferma la registrazione dopo una pausa di silenzio.
// Nessuna dipendenza e nessun modello da scaricare (resta tutto locale). Se un giorno serve più robustezza
// (rumore di fondo forte, voci in sottofondo) si può sostituire con un VAD neurale tipo Silero.
//
// Funzionamento: i primi 400 ms calibrano il rumore di fondo; poi "voce" = livello RMS sopra
// max(0.015, 3 × rumore). Si ferma dopo `silenceMs` di silenzio DOPO aver sentito voce, oppure dopo
// `noSpeechMs` senza alcuna voce, oppure dopo `maxMs` in totale. Ritorna la funzione di pulizia.
export function startVAD(stream, { silenceMs = 2500, noSpeechMs = 10000, maxMs = 90000, onLevel, onStop }) {
  const ctx = new (window.AudioContext || window.webkitAudioContext)();
  const src = ctx.createMediaStreamSource(stream);
  const analyser = ctx.createAnalyser();
  analyser.fftSize = 1024;
  src.connect(analyser);

  const buf = new Float32Array(analyser.fftSize);
  const t0 = performance.now();
  let noiseSum = 0;
  let noiseN = 0;
  let heardVoice = false;
  let lastVoice = t0;
  let lastLevelUpdate = 0;
  let fired = false;

  const timer = setInterval(() => {
    analyser.getFloatTimeDomainData(buf);
    let sum = 0;
    for (let i = 0; i < buf.length; i++) sum += buf[i] * buf[i];
    const rms = Math.sqrt(sum / buf.length);
    const now = performance.now();

    if (now - t0 < 400) {            // calibrazione del rumore di fondo
      noiseSum += rms;
      noiseN += 1;
      return;
    }
    const floor = noiseN ? noiseSum / noiseN : 0.005;
    const threshold = Math.max(0.015, floor * 3);
    if (rms > threshold) {
      heardVoice = true;
      lastVoice = now;
    }
    if (onLevel && now - lastLevelUpdate > 100) {
      lastLevelUpdate = now;
      onLevel(Math.min(1, rms / (threshold * 4)));
    }
    const stop =
      (heardVoice && now - lastVoice > silenceMs) ||
      (!heardVoice && now - t0 > noSpeechMs) ||
      now - t0 > maxMs;
    if (stop && !fired) {
      fired = true;
      onStop();
    }
  }, 50);

  return () => {
    clearInterval(timer);
    src.disconnect();
    ctx.close().catch(() => {});
  };
}
