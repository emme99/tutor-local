# Report benchmark LLM per il tutor

Modelli confrontati: gemma4_26b_a4b

| Modello | JSON valido | Errori corretti bene | Errori rilevati | Controlli senza falsi allarmi | Spiegazioni in italiano | Risposta adatta al TTS | Parole nella risposta (mediana) | Latenza mediana | tok/s mediani | Troncati | Con thinking |
|---|---|---|---|---|---|---|---|---|---|---|---|
| gemma4_26b_a4b | 100% (20/20) | 100% (10/10) | 100% (10/10) | 86% (6/7) | 100% (10/10) | 100% (20/20) | 17 | 2.4 s | 85 | 0 | 0 |

_Latenza = tempo totale per risposta (temperatura 0, nessuna storia). Per un tutor vocale conta restare entro pochi secondi. Le risposte lunghe (colonna «Parole») allungano il TTS e tendono a ripetere ciò che sta già nelle correzioni._

## Dove sbagliano

### gemma4_26b_a4b
- **a01** «I installed Dolama on my back book and now I'm testing German with fast therapy and React.» → is_correct=False, corretta: «I installed Llama on my MacBook and now I'm testing German with FastAPI and React.»; correzioni: 

## Da leggere a mano

_Casi senza punteggio automatico: guarda se il tutor resta nel ruolo, aiuta davvero e non inventa errori._

### m01 · «Ciao, non so come si dice in inglese: vorrei prenotare una camera per due notti.»
_l'allievo parla italiano: il tutor dovrebbe dare la frase in inglese e invitare a ripeterla, senza trattarla come un errore_

**gemma4_26b_a4b**
- risposta: In English, you can say: I would like to book a room for two nights. Can you try saying that?
- corretta: Ciao, non so come si dice in inglese: vorrei prenotare una camera per due notti. (is_correct=True)
- follow-up: Try to repeat the sentence: I would like to book a room for two nights.

### m03 · «Can you help me write a Python script?»
_fuori compito: ci si aspetta una risposta gentile che resta nel ruolo di tutor_

**gemma4_26b_a4b**
- risposta: I am here to practice English, but I would be happy to talk about Python or programming with you in English instead.
- corretta: Can you help me write a Python script? (is_correct=False)
- follow-up: 

### m04 · «I don't know what to say.»
_allievo bloccato: il tutor dovrebbe aiutarlo a ripartire con una domanda semplice, non fare una lezione_

**gemma4_26b_a4b**
- risposta: That is perfectly fine! We can start with something simple. How was your day today?
- corretta: I don't know what to say. (is_correct=True)
- follow-up: Tell me one thing you did today.

## Esempi completi da leggere (qualità dell'italiano e della conversazione)

**gemma4_26b_a4b · h01** · «Yesterday I have went to the shop and I buyed two breads.»
```json
{
 "is_correct": false,
 "corrected_sentence": "Yesterday I went to the shop and I bought two loaves of bread.",
 "corrections": [
  {
   "original": "have went",
   "corrected": "went",
   "explanation_it": "Per il passato semplice si usa solo la forma passata del verbo (went), non l'ausiliare have con il participio in questo contesto.",
   "type": "grammar"
  },
  {
   "original": "buyed",
   "corrected": "bought",
   "explanation_it": "Il verbo 'to buy' è irregolare. Il participio passato e il passato semplice sono 'bought'.",
   "type": "grammar"
  },
  {
   "original": "two breads",
   "corrected": "two loaves of bread",
   "explanation_it": "In inglese 'bread' è un nome non numerabile. Per indicare due unità si dice 'two loaves of bread'.",
   "type": "grammar"
  }
 ],
 "reply": "That sounds like a productive trip! What did you make with the bread?",
 "new_vocab": [
  {
   "term": "a loaf of bread",
   "translation_it": "una pagnotta di pane",
   "example": "I bought a loaf of bread for the sandwiches."
  },
  {
   "term": "grocery shopping",
   "translation_it": "fare la spesa",
   "example": "I need to go grocery shopping this afternoon."
  }
 ],
 "follow_up": "Can you tell me what else you bought at the shop?"
}
```

**gemma4_26b_a4b · h03** · «She is working here from three years and she don't like it.»
```json
{
 "is_correct": false,
 "corrected_sentence": "She has been working here for three years and she doesn't like it.",
 "corrections": [
  {
   "original": "is working here from three years",
   "corrected": "has been working here for three years",
   "explanation_it": "Per azioni che iniziano nel passato e continuano nel presente si usa il Present Perfect Continuous. Inoltre, con i periodi di tempo si usa 'for' e non 'from'.",
   "type": "grammar"
  },
  {
   "original": "she don't like it",
   "corrected": "she doesn't like it",
   "explanation_it": "Con la terza persona singolare (she) si usa l'ausiliare 'does not' o 'doesn't'.",
   "type": "grammar"
  }
 ],
 "reply": "I am sorry to hear that she is not happy with her job. Why do you think she doesn't like it?",
 "new_vocab": [
  {
   "term": "to quit a job",
   "translation_it": "licenziarsi / lasciare il lavoro",
   "example": "She wants to quit her job next month."
  },
  {
   "term": "stressful",
   "translation_it": "stressante",
   "example": "Her new position is very stressful."
  }
 ],
 "follow_up": "Do you like your job or is it stressful too?"
}
```

