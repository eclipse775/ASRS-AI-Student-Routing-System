# What the AI does

The project supports two explicit routing providers. **Gemini mode uses a pretrained Gemini 2.5 Flash model through the Gemini API.** Local mode uses the project's supervised multinomial Naive Bayes classifier. Both return a department suggestion, confidence estimate, explanation and model provenance to the same request service. Neither generates a support answer or resolves a request automatically.

## Gemini routing

1. Authenticate the student, verify CSRF and validate the request before making an API call.
2. Send only the request message to `https://generativelanguage.googleapis.com/v1beta/models/<model>:generateContent`. Student account names, email addresses, passwords and database records are not attached. A student's own message may still contain personal information.
3. Use server instructions defining IT, finance, academic and health destinations plus `review` for unclear/conflicting cases. Student text is supplied separately as user data.
4. Request a JSON response schema (`responseMimeType` + `responseSchema`) with three required fields: `department`, `confidence`, `reason`. Validate the returned JSON, department enum, finite score and explanation again on the server.
5. If a valid department meets the administrative threshold, assign it and persist the model's explanation/version. Otherwise save an escalation with a review deadline and notification.
6. Timeout, network failure, refusal, incomplete output, bad schema, missing key, access failure or quota limit produce human review with a visible provider error category. There is one outbound call and no automatic retries.

The score is an uncalibrated model estimate. A valid JSON shape does not prove semantic correctness or protect against every prompt attack. Staff review and representative evaluation remain necessary. The prompt supports English/Russian/Kazakh meanings, but live multilingual performance has not been evaluated or accepted as complete US7.

The key is read only by the Python server from the environment or the git-ignored `.env`. The setup script hides key entry. Keys are never returned to the browser or stored in classification records, and provider raw error bodies are not logged or exposed. HTTP redirects are blocked to prevent forwarding Authorization to another origin. The API request uses `store: false`; this option alone does not establish institution-approved privacy or a zero-retention guarantee.

Network work occurs before the SQLite write transaction. The service rechecks the session and request version afterwards, so a slow API call does not hold the database write lock or overwrite a staff decision.

## Local model

The local classifier learns word/unigram and adjacent-word-pair likelihoods from 96 authored English examples (24 per department), using additive smoothing. Prediction combines token evidence with learned class priors and temperature 1.5. It stores matched terms, a score distribution and a training-data fingerprint. Fewer than two informative terms or Cyrillic text cap confidence at 0.49 and require review.

The 40-example holdout contains 10 separate authored English examples per department, with no exact training overlap. The recorded 40/40 result applies only to this local model and synthetic dataset. It is not an Gemini accuracy score or a real-campus claim.

## Human decisions and training

Support corrections retain original suggestion, selected label, score, message snapshot, reviewer and timestamp. US10 can use authorized labels later. The Gemini model is pretrained externally; this project has not fine-tuned it on the 96 examples or automatically retrained from staff corrections.

## Explain it at the defence

“We send the request text to an Gemini language model through our server. It returns a department, a confidence estimate and a short explanation in a fixed JSON format. Our backend validates that output and uses a configurable threshold. Unclear requests and API failures are saved for human review. The key stays on the server. We also have a local classifier for an offline demonstration.”

Use this description for Gemini mode. If the portal displays Local ML, describe the local trained classifier instead. The integration tests use simulated HTTP responses; a live provider response remains pending until a real key is configured and `scripts/check_ai.py` succeeds.

Official implementation references: [Gemini API quickstart](https://ai.google.dev/gemini-api/docs/quickstart), [Structured output](https://ai.google.dev/gemini-api/docs/structured-output).
