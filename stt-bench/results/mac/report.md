# Report benchmark STT/ASR

Set di registrazioni: `mac` · Motori: gemma_verbatim, whisper_turbo

## Riepilogo (su 32 frasi comuni a tutti i motori)

| Motore | WER it | WER en | CER | RTF mediano |
|---|---|---|---|---|
| gemma_verbatim | 13.0% | 24.7% | 10.2% | 0.07 |
| whisper_turbo | 6.3% | 19.2% | 5.0% | 0.07 |

_WER/CER più bassi sono meglio. RTF = tempo di calcolo / durata audio (<1 = più veloce del parlato). Le frasi `en_pron` sono escluse: hanno una sezione dedicata._

## WER per categoria

| Categoria | gemma_verbatim | whisper_turbo |
|---|---|---|
| it_basic | 0.0% | 0.0% |
| it_numbers | 10.3% | 0.0% |
| it_phonetics | 5.8% | 5.8% |
| it_tech | 17.9% | 15.4% |
| it_names | 12.0% | 8.0% |
| it_spoken | 17.1% | 11.4% |
| it_long | 9.8% | 9.8% |
| it_over30 | 22.4% | 1.2% |
| it_pseudo | 11.1% | 11.1% |
| en_basic | 6.8% | 9.1% |
| en_numbers | 15.8% | 12.5% |
| en_th | 37.5% | 18.8% |
| en_endings | 33.3% | 33.3% |
| en_tech | 62.5% | 37.5% |
| en_names | 21.4% | 14.3% |
| en_long | 21.7% | 21.7% |
| en_pseudo | 40.0% | 30.0% |

## Dettaglio errori

**it04** · it_numbers · 7.6 s  
Riferimento: Il treno per Milano parte alle diciassette e quarantacinque dal binario dodici.
- `gemma_verbatim` (18.2%): il treno il treno per milano parte alle 17:45 dal binario 12
- `whisper_turbo` (0.0%): Il treno per Milano parte alle 17.45 dal binario 12.

**it05** · it_numbers · 5.8 s  
Riferimento: Il totale è di milleduecentotrentaquattro euro e cinquanta centesimi.
- `gemma_verbatim` (11.1%): Il totale è di €1234 e 50 centesimi.
- `whisper_turbo` (0.0%): Il totale è di 1.234,50 euro.

**it08** · it_phonetics · 6.2 s  
Riferimento: Questo scoglio è bagnato, perciò fai attenzione a dove metti i piedi.
- `gemma_verbatim` (8.3%): Questo scoglio è bagnato, perciò fai attenzione dove metti i piedi.
- `whisper_turbo` (8.3%): Questo scoglio è bagnato, perciò fare attenzione a dove metti i piedi.

**it09** · it_phonetics · 5.9 s  
Riferimento: Mia sorella ha comprato due caffè, uno è per me e l'altro per la nonna.
- `gemma_verbatim` (12.5%): Mia sorella ha comprato due caffè, uno è per me, l'altro è per la nonna.
- `whisper_turbo` (12.5%): Mia sorella ha comprato due caffè, uno è per me, l'altro è per la nonna.

**it11** · it_tech · 5.7 s  
Riferimento: Ho installato Ollama sul MacBook e ora provo Gemma con FastAPI e React.
- `gemma_verbatim` (15.4%): Ho installato Llama sul MacBook e ora provo Gemma con FastAPI in React.
- `whisper_turbo` (23.1%): Ho installato Lama sul Macbook e ora provo Gemma con FastHapy in React.

**it12** · it_tech · 4.8 s  
Riferimento: Il backend in Python usa un WebSocket per inviare l'audio al modello.
- `gemma_verbatim` (23.1%): Il backend in Python usa web socket per inviare l'audio al modem.
- `whisper_turbo` (7.7%): Il backend in Python usa WebSocket per inviare l'audio al modello.

**it13** · it_tech · 6.5 s  
Riferimento: Apri il terminale e lancia il comando pip install, poi riavvia il server.
- `gemma_verbatim` (15.4%): Apri il terminale e lancia il comando piplistol, poi riavvia il server.
- `whisper_turbo` (15.4%): Apri il terminale e lancia il comando ppstall, poi riavvia il server.

**it15** · it_names · 7.0 s  
Riferimento: Ho letto un articolo di Anthropic e uno di Google DeepMind sui nuovi modelli.
- `gemma_verbatim` (21.4%): Ho letto un articolo di Anthropik e uno di Google Deep Mind sui nuovi modelli.
- `whisper_turbo` (14.3%): Ho letto un articolo di Antropic e uno di Google DeepMind su nuovi modelli.

**it16** · it_spoken · 6.0 s  
Riferimento: Eh, allora, boh, non so, forse domani ci vediamo, dipende da come va il lavoro.
- `gemma_verbatim` (6.7%): Eh, allora boh, non so. Forse ci vediamo, dipende da come va il lavoro.
- `whisper_turbo` (13.3%): E allora boh, non so, forse ci vediamo, dipende da come va il lavoro.

**it17** · it_spoken · 4.5 s  
Riferimento: Davvero hai già finito? Non ci posso credere!
- `gemma_verbatim` (12.5%): Davvero è già finito, non ci posso credere.
- `whisper_turbo` (12.5%): Davvero è già finito? Non ci posso credere!

**it18** · it_spoken · 6.1 s  
Riferimento: Non ho ancora pranzato né cenato, e ormai è tardi per entrambi.
- `gemma_verbatim` (33.3%): Non ancora apprezzato, necenato e ormai è tardi per entrambi.
- `whisper_turbo` (8.3%): Non ho ancora prezzato né cenato e ormai è tardi per entrambi.

**it19** · it_long · 24.4 s  
Riferimento: Ieri sera ho provato per la prima volta a usare un modello linguistico direttamente sul telefono, senza connessione a internet. Mi ha colpito la velocità delle risposte e soprattutto la possibilità di tradurre la voce in tempo reale. Ora vorrei capire se posso costruire qualcosa di simile sul computer, con un'interfaccia web e un tutor che mi corregga quando sbaglio.
- `gemma_verbatim` (9.8%): Ieri sera, per la prima volta ho provato a usare un modello linguistico direttamente sul telefono, senza connessione a Internet. Mi ha colpito la velocità delle risposte e soprattutto la possibilità di tradurre la voce in tempo reale. Ora vorrei capire se è possibile costruire qualcosa di simile sul computer, con un'interfaccia web e un tutor che mi corregga quando sbaglio.
- `whisper_turbo` (9.8%): Ieri sera per la prima volta ho provato a usare un modello linguistico direttamente sul telefono, senza connessione a internet. Mi ha colpito la velocità delle risposte e soprattutto la possibilità di tradurre la voce in tempo reale. Ora vorrei capire se è possibile costruire qualcosa di simile sul computer con un'interfaccia web e un tutor che mi corregga quando sbaglio.

**it20** · it_over30 · 37.9 s  
Riferimento: Il progetto dovrebbe funzionare completamente in locale, senza inviare nessun dato a servizi esterni. Vorrei registrare la mia voce, ottenere la trascrizione e ricevere una risposta parlata con le correzioni grammaticali. Mi piacerebbe anche tenere traccia degli errori più frequenti e del vocabolario nuovo, per ripassarlo nei giorni successivi. Infine voglio confrontare diversi motori di riconoscimento vocale e scegliere quello che capisce meglio il mio accento, le parole tecniche e i nomi stranieri, anche quando parlo velocemente o con un po' di rumore in sottofondo.
- `gemma_verbatim` (22.4%): Il progetto dovrebbe funzionare completamente in locale, senza inviare nessun dato a servizi esterni. Vorrei registrare la mia voce, ottenere la trascrizione e ricevere una risposta parlata con le correzioni grammaticali. Mi piacerebbe anche tenere traccia degli errori più frequenti e del vocabolario nuovo per ripassarlo nei giorni successivi. Infine, voglio confrontare diversi motori di riconoscimento vocale e scegliere quello che capisce meglio il mio accento.
- `whisper_turbo` (1.2%): Il progetto dovrebbe funzionare completamente in locale, senza inviare nessun dato a servizi esterni. Vorrei registrare la mia voce, ottenere la trascrizione e ricevere una risposta parlata con le correzioni grammaticali. Mi piacerebbe anche tenere traccia degli errori più frequenti e del vocabolario nuovo per ripassarlo nei giorni successivi. Infine voglio confrontare diversi motori di riconoscimento vocale e scegliere quello che capisce meglio il mio accento, le parole tecniche e i nomi stranieri, anche quando parlo velocemente o con un po' di rumore di sottofondo.

**it21** · it_pseudo · 8.4 s  
Riferimento: Le parole inventate sono: stranfo, bliscare, gruppeto e cravidenza.
- `gemma_verbatim` (11.1%): Le parole inventate sono stranfo, bliscare, gruppetto e cravidenza.
- `whisper_turbo` (11.1%): Le parole inventate sono stranfo, bliscare, gruppetto e cravidenza.

**en01** · en_basic · 9.5 s  
Riferimento: I would like to book a table for four people tonight at eight o'clock.
- `gemma_verbatim` (6.7%): I would like to book a table for people tonight at eight o'clock.
- `whisper_turbo` (13.3%): I would like to book a table for people tonight at 8 o'clock.

**en02** · en_basic · 6.3 s  
Riferimento: Tomorrow morning I have a meeting with the client, so I need to wake up early.
- `gemma_verbatim` (6.2%): Tomorrow morning I have meeting with the client so I need to wake up early.
- `whisper_turbo` (6.2%): Tomorrow morning I have meeting with the client, so I need to wake up early.

**en03** · en_basic · 6.1 s  
Riferimento: I didn't understand the question, could you repeat it more slowly, please?
- `gemma_verbatim` (7.7%): I didn't understand the question could you repeat more slowly please
- `whisper_turbo` (7.7%): I didn't understand the question. Could you repeat more slowly, please?

**en04** · en_numbers · 6.3 s  
Riferimento: The train to London leaves at five forty-five from platform twelve.
- `gemma_verbatim` (9.1%): The train to London leaves at 5:45 for platform 12.
- `whisper_turbo` (18.2%): The train to London leave at 5.45 for platform 12.

**en05** · en_numbers · 7.7 s  
Riferimento: The total is one thousand two hundred and thirty-four dollars and fifty cents.
- `gemma_verbatim` (25.0%): The total is $1,234 and 50 cent.
- `whisper_turbo` (0.0%): The total is $1234.50.

**en06** · en_th · 9.3 s  
Riferimento: I think that Thursday is the third day of the month, though they said something else.
- `gemma_verbatim` (37.5%): I think the Tuesday is the third day of March. Thought they said something, guess.
- `whisper_turbo` (18.8%): I think that Tuesday is the third day of month. Now they said something else.

**en07** · en_endings · 8.7 s  
Riferimento: She walked, talked, and laughed while they waited and worked all afternoon.
- `gemma_verbatim` (33.3%): She worked, talked, and laughed. We day want waited and worked all afternoon.
- `whisper_turbo` (33.3%): She walked, talked and loved. We day one waited and worked all afternoon.

**en08** · en_tech · 8.3 s  
Riferimento: I installed Ollama on my MacBook and now I'm testing Gemma with FastAPI and React.
- `gemma_verbatim` (62.5%): I install the dolama or my backup and now I instain jema with first happy and react.
- `whisper_turbo` (37.5%): I installed Dolama on my back book and now I'm testing German with fast therapy and React.

**en09** · en_names · 7.8 s  
Riferimento: Next summer we are going to Edinburgh, then to Worcester and finally to Leicester.
- `gemma_verbatim` (21.4%): Next summer we are going to Edinburgh to then Worcester and finally Leicester.
- `whisper_turbo` (14.3%): Next summer we are going to Edinburgh, then Worcester and finally Leicester.

**en10** · en_long · 13.1 s  
Riferimento: Could you tell me whether the library closes early on Fridays, and if there's a quiet room I can use to study?
- `gemma_verbatim` (21.7%): Could you tell me whether the river closes at early on Friday and if there a quiet room I can use study
- `whisper_turbo` (21.7%): Could you tell me whether the library closed early on Friday and if there a quiet room I can use Taddy?

**en11** · en_pseudo · 9.1 s  
Riferimento: The made-up words are: blorf, tramble, skindle and fompet.
- `gemma_verbatim` (40.0%): The midap word are bluffer, tramble, skindle and fompet.
- `whisper_turbo` (30.0%): The made up words are bluff, trombone, skindle and thumpet.

## Clip lunghe (limite audio di Gemma: 30 s)

| Frase | Durata | Motore | WER | Parole output/riferimento |
|---|---|---|---|---|
| it20 | 37.9 s | gemma_verbatim | 22.4% | 78% |
| it20 | 37.9 s | whisper_turbo | 1.2% | 100% |

_Un rapporto molto sotto il 100% su clip >30 s indica troncamento._

## Test pronuncia

### A) L'ASR riporta ciò che hai detto o lo corregge?

Sulla take *sbagliata di proposito*: **fedele** = scrive la parola pronunciata (es. «sheep»); **normalizzato** = scrive la parola attesa (es. «ship»).

| Motore | Fedele | Normalizzato | Altro |
|---|---|---|---|
| gemma_verbatim | 2 | 6 | 0 |
| whisper_turbo | 2 | 3 | 3 |

### B) Domanda diretta al modello («quali parole sono pronunciate male?»)

| Motore | Rilevato (take sbagliata) | Falsi allarmi (take corretta) | Discrimina (rilevato E nessun falso allarme) |
|---|---|---|---|
| gemma_verbatim | 7/8 | 8/8 | 0/8 |

_Conta soprattutto l'ultima colonna: un valutatore utile segnala l'errore sulla take sbagliata e risponde NONE su quella corretta._

- `gemma_verbatim` pron01 (parola «ship»): sbagliata → 'ship' · corretta → 'harbor'
- `gemma_verbatim` pron02 (parola «bit»): sbagliata → 'bit, please' · corretta → 'more'
- `gemma_verbatim` pron03 (parola «full»): sbagliata → 'full' · corretta → 'full'
- `gemma_verbatim` pron04 (parola «think»): sbagliata → 'think' · corretta → 'think,idea'
- `gemma_verbatim` pron05 (parola «this»): sbagliata → 'this' · corretta → 'brother'
- `gemma_verbatim` pron06 (parola «hat»): sbagliata → 'hat' · corretta → 'isend'
- `gemma_verbatim` pron07 (parola «live»): sbagliata → 'here' · corretta → 'here'
- `gemma_verbatim` pron08 (parola «cat»): sbagliata → 'cat' · corretta → 'cat'

## Traduzione parlato → testo (non punteggiata, da leggere)

**it01** · Buongiorno, vorrei prenotare un tavolo per quattro persone stasera alle otto.  
Riferimento: Good morning, I would like to book a table for four people tonight at eight.
- `gemma_verbatim`: Hello, I would like to book a table for four people this evening at 8:00.

**it02** · Domani mattina ho una riunione con il cliente, quindi devo svegliarmi presto.  
Riferimento: Tomorrow morning I have a meeting with the client, so I have to wake up early.
- `gemma_verbatim`: Tomorrow morning I have a meeting with the client, so I have to wake up early.

**it03** · Non ho capito bene la domanda, puoi ripeterla più lentamente?  
Riferimento: I didn't understand the question well, can you repeat it more slowly?
- `gemma_verbatim`: Don't I understand the question well? Can you repeat it more slowly?

**it11** · Ho installato Ollama sul MacBook e ora provo Gemma con FastAPI e React.  
Riferimento: I installed Ollama on the MacBook and now I'm trying Gemma with FastAPI and React.
- `gemma_verbatim`: I installed Thalamus on my book and now I am trying Gemma with FastApi in React.

**en01** · I would like to book a table for four people tonight at eight o'clock.  
Riferimento: Vorrei prenotare un tavolo per quattro persone stasera alle otto.
- `gemma_verbatim`: Vorrei prenotare un tavolo per due stasera alle otto.

**en02** · Tomorrow morning I have a meeting with the client, so I need to wake up early.  
Riferimento: Domani mattina ho una riunione con il cliente, quindi devo svegliarmi presto.
- `gemma_verbatim`: Domani mattina ho un incontro col cliente, quindi devo alzarmi presto.

**en03** · I didn't understand the question, could you repeat it more slowly, please?  
Riferimento: Non ho capito la domanda, potresti ripeterla più lentamente, per favore?
- `gemma_verbatim`: I didn't understand the question. Could you repeat more slowly, please?

**en10** · Could you tell me whether the library closes early on Fridays, and if there's a quiet room I can use to study?  
Riferimento: Potresti dirmi se la biblioteca chiude presto il venerdì e se c'è una sala silenziosa dove posso studiare?
- `gemma_verbatim`: Could you tell me whether the library closes early on Friday and if there a quiet room I can use study?

