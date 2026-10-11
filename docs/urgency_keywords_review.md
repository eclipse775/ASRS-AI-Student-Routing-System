# Urgency keywords: native-speaker review checklist

The urgency detector (`app/urgency.py`) reads `app/urgency_rules.json`. The Kazakh and Russian terms were written without a native-speaker check, so please review them before the demo. A wrong keyword either misses an emergency (unsafe) or floods staff with false alerts (disruptive). Edit the JSON directly; no code change is needed.

How to read the table: a **strong** signal flags a request on its own. Two **weak** signals (weights add up to 1.0) are needed to flag it.

## Kazakh (needs review)

| Pattern in the rules file | Intended meaning | Strength | Reviewer: correct? / better wording |
| --- | --- | --- | --- |
| `кеуд\w* ауыр\w*` | chest pain ("my chest hurts") | strong | |
| `тыныс алу\w* қиын`, `тыныстай алмай\w*` | hard to breathe / cannot breathe | strong | |
| `есінен тан\w*` | fainted / lost consciousness | strong | |
| `қатты қан кет\w*` | severe bleeding | strong | |
| `жедел жәрдем` | ambulance | strong | |
| `өлгім келеді`, `өз-өзіме қол жұмса\w*` | "I want to die", harming myself | strong | |
| `өрт` | fire | strong | |
| `апат\w*` | disaster / accident, used as "emergency" | strong | Possibly too broad: check for ordinary uses |
| `шұғыл` | urgent | weak | |
| `көмектесіңдер`, `көмектесіңіз` | "please help" | weak | |

Not covered in Kazakh yet (the English and Russian rules have them): violence or threats, poisoning or overdose, seizure, allergic reaction, "dangerous", "scared". Please suggest wording.

## Russian (also worth a quick check)

Strong: боль в груди, не могу дышать / трудно дышать / задыхаюсь, без сознания / потерял сознание, сильное кровотечение, передозировка / отравление, скорая помощь, суицид / хочу умереть, пожар / горит, напал / нападение / оружие, экстренный / чрезвычайный.
Weak: срочно / немедленно, помогите, опасно / страшно / ранен.

## Known limits

- Matching is by word pattern, not meaning. Misspellings, transliterated text and slang can be missed.
- A negation such as "this is not an emergency" cancels only the stated-urgency words (emergency, urgent, help). Medical and safety terms still flag the request.
- Do not remove strong terms to reduce alerts without a staff decision. A false alert costs minutes; a missed emergency can cost much more.
