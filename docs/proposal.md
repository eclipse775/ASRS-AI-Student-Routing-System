# Project proposal

**Project:** AI Student Request Routing and Support System  
**Course:** INF 451, Fall 2026  
**Current deliverable:** Sprint 1-2 combined increment

## Problem

Students often do not know which department can resolve an issue. Contacting several offices repeats the same information, delays support, and makes request progress difficult to follow. Support staff need one place to review requests and correct routing decisions.

## Goal and measurable objectives

Provide one student-facing intake portal that classifies requests into IT Helpdesk, Financial Aid, Academic Advising, or Health Services, with a human review path when routing is uncertain.

- Route at least 9 of 10 representative acceptance examples to the correct department, within 30 seconds.
- Deliver an in-app confirmation containing the request reference, department, and estimated response time within 60 seconds.
- Show current status to the request owner within one minute of a staff update.
- Load a queue of up to 500 open requests within three seconds in the target demonstration environment.
- Store a four-business-hour review deadline and visibly identify overdue escalations.
- Require authentication and role-based access to all student/staff/admin data.

The operational review target requires available staff. The software records and exposes the deadline; it cannot guarantee that a person responds.

## Users and stakeholders

Students submit requests and read updates. Support officers review escalations, choose routes, and resolve requests. Administrators tune the confidence threshold. Department representatives are stakeholders in the shared support workflow. The initial model and datasets use synthetic examples only.

## Scope

Sprint 1 delivers authentication/database foundations, request intake, classification/routing, and notification history. Sprint 2 delivers configurable escalation, the manual routing dashboard, staff correction logs, and live student status tracking. Later sprints deliver automatic urgency detection, multilingual support, feedback, analytics, and retraining.

## Epics

| Epic | Included stories |
| --- | --- |
| E1. Request intake and intelligent routing | US1, US3, US6, US7 |
| E2. Student communication and progress | US2, US5, US8 |
| E3. Support operations | US4 |
| E4. Administration and model improvement | US9, US10 |

## Architecture choice

A modular monolith uses a responsive browser interface, a JSON API, SQLite, and a configurable AI routing provider (Gemini API or the in-process supervised model). This matches the recommended Frontend -> Backend/API -> Database architecture; the local mode supports an offline defence. External mode requires a user-configured key and internet access.
