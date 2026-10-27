# Report benchmark LLM per il tutor

Modelli confrontati: gemma4_26b_a4b

| Modello | JSON valido | Errori corretti bene | Errori rilevati | Controlli senza falsi allarmi | Spiegazioni in italiano | Risposta adatta al TTS | Parole nella risposta (mediana) | Latenza mediana | tok/s mediani | Troncati | Con thinking |
|---|---|---|---|---|---|---|---|---|---|---|---|
| gemma4_26b_a4b | 100% (28/28) | 100% (20/20) | 100% (20/20) | 100% (8/8) | 100% (20/20) | 100% (28/28) | 14 | 2.3 s | 88 | 0 | 0 |

_Latenza = tempo totale per risposta (temperatura 0, nessuna storia). Per un tutor vocale conta restare entro pochi secondi. Le risposte lunghe (colonna «Parole») allungano il TTS e tendono a ripetere ciò che sta già nelle correzioni._

## Dove sbagliano

### gemma4_26b_a4b

## Esempi completi da leggere (qualità dell'italiano e della conversazione)

**gemma4_26b_a4b · e01** · «I am agree with you.»
```json
{
 "is_correct": false,
 "corrected_sentence": "I agree with you.",
 "corrections": [
  {
   "original": "I am agree",
   "corrected": "I agree",
   "explanation_it": "In inglese non si dice 'io sono d'accordo' usando il verbo essere, ma si usa direttamente il verbo 'to agree'.",
   "type": "grammar"
  }
 ],
 "reply": "That is a very common mistake, but don't worry! I am glad we are on the same page. What do you think about our topic today?",
 "new_vocab": [
  {
   "term": "to be on the same page",
   "translation_it": "essere sulla stessa lunghezza d'onda / essere d'accordo",
   "example": "I am glad we are on the same page about the plan."
  }
 ],
 "follow_up": "Can you try to say 'I agree' in a full sentence about your favorite food?"
}
```

**gemma4_26b_a4b · e05** · «I live here since two years.»
```json
{
 "is_correct": false,
 "corrected_sentence": "I have lived here for two years.",
 "corrections": [
  {
   "original": "I live here since two years",
   "corrected": "I have lived here for two years",
   "explanation_it": "In inglese, per un'azione che è iniziata nel passato e continua nel presente, si usa il Present Perfect. Inoltre, si usa 'for' per indicare la durata (due anni) e 'since' per indicare il momento preciso dell'inizio.",
   "type": "grammar"
  }
 ],
 "reply": "That is great! How do you like living there so far?",
 "new_vocab": [
  {
   "term": "so far",
   "translation_it": "finora",
   "example": "How is your new job going so far?"
  }
 ],
 "follow_up": "Can you tell me one thing you love about your city?"
}
```

**gemma4_26b_a4b · e16** · «I have eated pizza last night.»
```json
{
 "is_correct": false,
 "corrected_sentence": "I ate pizza last night.",
 "corrections": [
  {
   "original": "have eated",
   "corrected": "ate",
   "explanation_it": "Il passato di 'eat' è irregolare: 'ate'. Inoltre, con un riferimento temporale specifico come 'last night', si usa il Past Simple e non il Present Perfect.",
   "type": "grammar"
  }
 ],
 "reply": "That sounds delicious! What kind of pizza did you have?",
 "new_vocab": [
  {
   "term": "delicious",
   "translation_it": "delizioso",
   "example": "The pizza was delicious."
  }
 ],
 "follow_up": "Tell me, what is your favorite topping on a pizza?"
}
```

**gemma4_26b_a4b · c07** · «i went to milan last week and it was great»
```json
{
 "is_correct": true,
 "corrected_sentence": "i went to milan last week and it was great",
 "corrections": [],
 "reply": "That sounds wonderful! What was your favorite thing to do in Milan?",
 "new_vocab": [
  {
   "term": "sightseeing",
   "translation_it": "fare il turista / visitare monumenti",
   "example": "I went sightseeing in Milan all day."
  }
 ],
 "follow_up": "Did you visit the Duomo or go shopping?"
}
```

