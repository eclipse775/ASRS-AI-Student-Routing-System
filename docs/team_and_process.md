# Team responsibilities and process

The user-story workbook assigns responsible functions rather than named team members. This package retains those assignments. No personal team identities, meeting attendance, teacher approval, or past velocity are inferred from external rosters.

| Responsibility | Owner function | Concrete work |
| --- | --- | --- |
| Product ownership | Product Owner | Confirm scope, story priorities, acceptance, institutional assumptions |
| Scrum coordination | Rotating Scrum Master | Plan each two-week lab, record blockers, coordinate review/retro |
| AI/backend | AI/Backend Developer | Model, routing, escalation, sessions, database transactions |
| Interface | Frontend Developer / UX Designer | Student, support, administrator views and accessible flows |
| End-to-end status | Full-stack Developer | State transitions, history, polling, resolution |
| Quality | QA Tester | Execute acceptance tests, privacy checks, model/performance evaluation |

Assign real names to these functions in the team board before presenting individual contributions. Use the actual course Scrum Master rotation. This is an administrative personalization step, not an unimplemented product feature.

## Ceremony plan

| Event | Cadence | Record |
| --- | --- | --- |
| Sprint planning | Start of each two-week sprint | Goal, selected stories, capacity, tasks, owners, dependencies |
| Stand-up | Each agreed working day, approximately 15 minutes | Done, next, blocker, owner/action |
| Backlog refinement | As needed before next planning | Scope/acceptance/estimate changes and reasons |
| Review/demo | End of each sprint | Demonstration, PO/teacher feedback, accepted/rejected stories |
| Retrospective | After review | What worked, difficulty, improvement, action owner |

The reports contain a prepared demo and a technical retrospective based on implementation evidence. They do not claim that these meetings already occurred.

## Recording actual history

Append dated records to `meeting_log.csv` only when a meeting occurs. Record who attended and what changed. The supplied file starts with a header because no historical meeting records were provided. A current completion snapshot is available in the sprint task backlog; it is not a replacement for a daily team history.

## Progress and burndown

Each sprint CSV contains an ideal linear 10-working-day burndown. Observed daily values are blank when there is no evidence. The build snapshot records technical completion without pretending that story points were accepted on particular prior days. True team velocity uses accepted story points per completed sprint and should be recorded after the team's review.
