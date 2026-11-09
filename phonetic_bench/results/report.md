# Benchmark valutazione fonetica

- modello: `facebook/wav2vec2-xlsr-53-espeak-cv-ft` su `mps`
- impronta: `5ce2018ed3199562` (v1)
- eseguito: 2026-11-09T09:20:21+00:00
- audio: `/Users/emme/Projects/VisualStudio/tutor-local/stt-bench/recordings/mac`

## Gate

| gate | misurato | soglia | esito |
|---|---:|---:|---|
| score mediano frasi pulite | 69.0 | ≥ 60 | ✅ |
| score minimo frasi pulite | 47 | ≥ 40 | ✅ |
| coppie minime ordinate | 7/8 | ≥ 7 | ✅ |
| delta mediano coppie | +33.5 | ≥ 10 | ✅ |
| perturbazioni in ordine | 11/11 | ≥ 9 | ✅ |
| drop mediano perturbazione | +8.0 | ≥ 5 | ✅ |
| latenza mediana | 0.125 s | < 1.0 s | ✅ |

**Esito**: tutti i gate superati

## Frasi pulite

| id | categoria | score | fonemi | secondi |
|---|---|---:|---:|---:|
| en01 | en_basic | 74 | 29/39 | 0.12 |
| en02 | en_basic | 82 | 39/47 | 0.11 |
| en03 | en_basic | 79 | 37/47 | 0.11 |
| en04 | en_numbers | 86 | 40/46 | 0.11 |
| en05 | en_numbers | 66 | 35/53 | 0.12 |
| en06 | en_th | 58 | 27/46 | 0.13 |
| en07 | en_endings | 47 | 20/43 | 0.13 |
| en08 | en_tech | 69 | 41/59 | 0.13 |
| en09 | en_names | 54 | 28/51 | 0.12 |
| en10 | en_long | 65 | 46/70 | 0.16 |
| en11 | en_pseudo | 80 | 30/37 | 0.13 |

## Coppie minime

| id | focus / bad_say | ok | bad | delta | ordine |
|---|---|---:|---:|---:|---|
| pron01 | ship / sheep | 76 | 18 | +58 | ✅ |
| pron02 | bit / beat | 83 | 24 | +59 | ✅ |
| pron03 | full / fool | 64 | 36 | +28 | ✅ |
| pron04 | think / sink | 67 | 28 | +39 | ✅ |
| pron05 | this / dis | 85 | 15 | +70 | ✅ |
| pron06 | hat / at | 47 | 31 | +16 | ✅ |
| pron07 | live / leave | 71 | 68 | +3 | ✅ |
| pron08 | cat / cut | 67 | 67 | +0 | ❌ |

## Perturbazione (testo senza ultima parola)

| id | score base | score perturbato | drop |
|---|---:|---:|---:|
| en01 | 74 | 63 | +11 |
| en02 | 82 | 76 | +6 |
| en03 | 79 | 72 | +7 |
| en04 | 86 | 74 | +12 |
| en05 | 66 | 59 | +7 |
| en06 | 58 | 52 | +6 |
| en07 | 47 | 23 | +24 |
| en08 | 69 | 61 | +8 |
| en09 | 54 | 46 | +8 |
| en10 | 65 | 64 | +1 |
| en11 | 80 | 62 | +18 |

## Risorse

- latenza mediana/max: 0.125 s / 0.163 s
- memoria MPS allocata: 1263.9 MB
- memoria MPS driver: 2250.3 MB
- RSS processo: 747.9 MB
