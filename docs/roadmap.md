# Seven-sprint course roadmap

One sprint equals one two-week lab. The supplied workbook has four story iterations; the course requires seven. This roadmap preserves the Sprint 1-2 assignment and spreads the later stories across the remaining course sprints. It does not overwrite the original workbook or claim that later stories are implemented.

| Course sprint | Focus | Stories / work | Source effort | State |
| --- | --- | --- | --- | --- |
| 1 | Basic system, authentication/database, routing and notification | US1, US2 plus foundation | 8 | Implemented increment |
| 2 | Human review and request tracking | US3, US4, US5 | 15 | Implemented increment |
| 3 | Priority handling | US6 automatic detection and real alert channel | 7 | Backlog |
| 4 | Multilingual access | US7 language detection/classification/translation | 5 | Backlog |
| 5 | Support quality and reporting | US8 feedback, US9 analytics | 9 | Backlog |
| 6 | Model improvement and integration | US10 retraining, approved datasets, drift checks | 8 | Backlog |
| 7 | Final validation and delivery | Fixes, end-to-end regression, production review, final report/presentation/demo | Enabling work, estimate after refinement | Backlog |

Total supplied story effort is 52. These estimates are the supplied values interpreted as story points, not measured hours. Foundation/cleanup work is not silently added to them. Future sprint capacity must be adjusted after actual team delivery data becomes available.

The source labels US9 as HC&LV even though its value deserves review. Its original flag is preserved; the Product Owner should re-evaluate that priority. The source estimates use values such as 6 and 7 rather than a strict Fibonacci sequence. No estimates are changed merely to match a different convention.

Course defence dates and team availability were not supplied. The source deadlines from November 2026-February 2027 remain visible in `product_backlog.csv`, but the lab calendar should govern actual sprint dates. No past or future team meetings are fabricated.

## Scrum participation

The Product Owner prioritizes and accepts increments. The Scrum Master facilitates planning, stand-up, review, and retrospective. Developers/testers implement and verify the selected stories. The linked grading sheet uses rotating Scrum Master roles; the team should apply its actual assigned rotation.

Use `team_and_process.md` for responsibilities and the meeting record convention. Use `kanban.html` for a local progress board, or import the CSV tasks into the team's existing Trello/Notion/Jira board.
