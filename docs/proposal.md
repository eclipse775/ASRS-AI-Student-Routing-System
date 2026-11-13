# Project proposal

**Project:** AI Student Request Routing and Support System  
**Course:** INF 451, Fall 2026  
**Current deliverable:** All 16 revised user stories are implemented; the latest feature increment still needs acceptance testing

## Problem

Students often do not know which department can resolve an issue. Contacting several offices repeats the same information, delays support, and makes request progress difficult to follow. Support staff need one place to review requests and correct routing decisions.

## Goal and measurable objectives

Provide one student-facing intake portal that classifies requests into IT Helpdesk, Financial Aid, Academic Advising, Health Services, or Campus Security, with a human review path when routing is uncertain.

- Route at least 9 of 10 representative acceptance examples to the correct department, within 30 seconds.
- Deliver an in-app confirmation containing the request reference, department, and estimated response time within 60 seconds.
- Show current status to the request owner within one minute of a staff update.
- Load a queue of up to 500 open requests within three seconds in the target demonstration environment.
- Store a four-business-hour review deadline and visibly identify overdue escalations.
- Require authentication and role-based access to all student/staff/admin data.

The operational review target requires available staff. The software records and exposes the deadline; it cannot guarantee that a person responds.

## Users and stakeholders

Students submit requests and read updates. Support officers review escalations, choose routes, and resolve requests. Administrators tune the confidence threshold, service targets, contacts, and retention period. The current admin interface does not expose AI-routing correction or model-retraining controls. Department representatives are stakeholders in the shared support workflow. The initial model and datasets use synthetic examples only.

## Scope

All seven course sprint groups have an implementation: intake and routing (US1-US7), feedback and analytics (US8-US9), student request search, messaging, and the profile panel (US10-US12), and service-level tracking, attachments, audit, retention, and deletion (US13-US16). The latest US8-US16 acceptance paths have not been run in this delivery; see `testing.md`.

## Epics

| Epic | Included stories |
| --- | --- |
| E1. Request intake and intelligent routing | US1, US3, US6, US7 |
| E2. Student communication and progress | US2, US5, US8, US10, US11, US12, US14 |
| E3. Support operations | US4, US13 |
| E4. Administration and governance | US9, US15, US16 |

## Architecture choice

A modular monolith uses a responsive browser interface, a JSON API, SQLite, and a configurable AI routing provider (Gemini API or the in-process supervised model). This matches the recommended Frontend -> Backend/API -> Database architecture; the local mode supports an offline defence. External mode requires a user-configured key and internet access.
