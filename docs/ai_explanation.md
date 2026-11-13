# What the AI does

The portal supports a local Naive Bayes classifier and an optional Gemini API route. Both suggest a department and confidence estimate. Neither answers the request or resolves it. Unclear or failed classifications go to the support queue.

## Gemini routing and translation

1. The server authenticates the student and validates the request before making an API call.
2. It sends only the request message to Gemini. Names, email addresses, passwords, database records, and attachments are not included. A student's message can still contain personal information.
3. The response schema asks for department, confidence, a short routing reason, language, urgency, and a separate English translation for staff.
4. The backend validates output fields, department and language codes, score, and translation length before storing the result.
5. If the request is unclear or Gemini is unavailable, the system saves it for human review. There is one outbound classification request and no retries.

Gemini supports English, Russian, and Kazakh meaning and can return a staff translation when configured. The original student text is stored separately and never replaced by the translation. The offline local model does not translate arbitrary text; staff see a clear notice when translation is unavailable.

The confidence score is an uncalibrated model estimate. A valid JSON response does not establish semantic correctness, real-campus accuracy, or institutional approval to send request text to an external provider. Use synthetic text for demonstrations and review the provider's current privacy terms before real use.

The key is loaded on the server from the process environment or local `.env`. It is not sent to the browser or stored in classification records. Provider error bodies are not logged or exposed. Redirects are blocked to prevent forwarding the API key to another origin. See `API_START_RU.md` for setup.

## Offline classifier

The local classifier learns English word and adjacent-word-pair likelihoods from the supplied training data. A small term map adds common Russian and Kazakh support vocabulary to those English features. If the request has too little recognized topic evidence, it is escalated to staff rather than guessed.

The offline term map covers common topics such as accounts, Wi-Fi, tuition, scholarships, schedules, exams, health services, and physical safety. It is not a full multilingual model. Accuracy parity between languages has not been established; representative validation examples are needed before claiming it.

## Urgency and staff correction

Urgency signals are scanned server-side before and independently of AI routing. This still works if Gemini is unavailable. A detected urgent request bypasses the uncertain-route queue, receives an immediate support-dashboard alert, and can be escalated to configured email contacts if nobody acknowledges it. Students and staff can also report a missed emergency.

Staff routing corrections and reopen decisions are saved as labels for scheduled local-model retraining. A candidate model is checked against held-out data and replaces the live version only if it does not score worse. Model versions can be restored. Gemini remains a pretrained external model and is not retrained on the project's student data.

## Explain it at the defence

“The system routes requests with a local classifier or an optional Gemini model. Our server checks the result and sends uncertain requests to a human. Russian and Kazakh topic terms are supported offline, while Gemini can provide a separate English translation for staff. Urgent requests bypass the normal review queue and alert support. Staff corrections can improve the local model after validation.”

Current code has not been acceptance-tested for the new US8-US16 increment. See `testing.md` for the scope of the earlier baseline evidence.
