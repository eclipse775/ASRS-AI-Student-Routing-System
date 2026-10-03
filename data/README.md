# Synthetic routing data

`training.json` contains 96 authored English examples, 24 per department. `evaluation.json` contains 40 distinct authored examples, 10 per department. Examples are labeled `it`, `finance`, `academic`, or `health`. No exact text overlap is permitted; evaluation examples are not used by the application during training.

These data are an educational baseline. They contain no real student identities or requests. Similar-domain phrasing makes this a small demonstration benchmark, not a measure of real operational accuracy. Use authorized, varied, independently labeled data before institutional deployment.

The application trains token counts at startup. The model version hashes the training file. Staff decisions are stored in a separate database table for a later retraining pipeline and do not silently modify these files.
