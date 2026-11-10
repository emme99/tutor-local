/** Helper e costanti condivise dal frontend. */

export function reviewSpeechText(item) {
  // Per gli errori si ascolta la forma corretta; per i vocaboli il termine inglese, non la traduzione.
  return item?.kind === "mistake" ? item.answer : item.prompt;
}

export const MODE_LABEL = {
  conversation: "Conversazione",
  scenario: "Scenario",
  translate: "Traduzione",
};

export const MODE_HINTS = {
  conversation:
    "Premi ● Parla e dì qualcosa in inglese, per esempio «My name is…». Il tutor ti risponde e ti corregge.",
  scenario:
    "Descrivi in italiano una situazione, per esempio «Aiutami a presentarmi in albergo per avere una camera»: riceverai le frasi da dire e poi farete un gioco di ruolo.",
  translate:
    "Parla (o scrivi) nella lingua scelta a sinistra: il tutor traduce e pronuncia la traduzione.",
};
