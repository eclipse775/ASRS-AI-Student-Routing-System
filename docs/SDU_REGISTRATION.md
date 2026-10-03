# SDU registration and student year

This requirement was supplied by the project owner on 3 October 2026 and extends the Sprint 1 authentication foundation. It does not change the source US1-US5 estimates or overwrite the original workbook.

| Rule | Implemented behavior | Evidence |
| --- | --- | --- |
| University student address | Exactly nine ASCII digits followed by `@sdu.edu.kz` | Server validation and browser input pattern |
| Admission year | First two digits are interpreted as `2000 + YY` | `app/university.py`, academic-year tests |
| Current study year | Academic-year start minus admission year plus one | Profile returned by registration/login/session; displayed in student portal |
| Requested example | `240103030@sdu.edu.kz` -> admission 2024 -> Year 3 in 2026-2027 | Fixed-date unit test and browser profile screenshot |
| Helpdesk | `helpdesk@sdu.edu.kz`, support role | Provisioned demo account and staff-only queue |
| Public signup permissions | Always student; cannot create helpdesk/admin or supply their own course/role | Role-forgery and reserved-address tests |

Leading/trailing whitespace is trimmed; address case is normalized. Other domains, subdomains, extra suffixes, letter IDs, short/long IDs, aliases and non-ASCII numeral lookalikes are rejected. A future admission year is rejected. No maximum course or enrollment status was supplied, so the system does not invent one.

## Academic calendar assumption

The implemented academic year begins on **1 September at UTC+5** and runs through the following August. This makes January 2027 part of 2026-2027, rather than increasing the course on 1 January. The boundary is documented and tested. Course is recalculated from the email whenever the server returns a user profile; it is not stored as a value that becomes stale every year. The September boundary is an implementation assumption, not a verified SDU calendar policy. Course is derived metadata, not an official enrollment record.

## Account setup and existing data

`python run.py --demo` provisions synthetic SDU student accounts, `helpdesk@sdu.edu.kz` and `admin@sdu.edu.kz`. The README lists classroom passwords. Public signup never provisions staff. Without demo mode, the local administrator can use `scripts/create_staff.py`: support is restricted to the requested helpdesk address; administrator addresses must be named addresses at `sdu.edu.kz`.

If a previous default demo database is reused, demo startup updates the four recognized legacy demo accounts to the new addresses while retaining their IDs, password hashes, request ownership and notifications. It never merges identities when a destination account already exists. Other non-SDU student accounts are not rewritten; they can no longer sign in under this policy. The delivered ZIP contains no runtime database.

## Ownership verification boundary

This increment validates the address format and domain. **It does not send verification emails or prove that the registrant controls the mailbox.** Actual university identity verification needs an authorized SDU SSO integration or a verified-mail flow with a delivery service. Neither was supplied. Running the classroom project requires only Python; enabling external routing adds the user's Gemini API key and internet access.

Student ID, admission year and course are not appended to Gemini input. The external routing request contains only the submitted issue text. No real university students or staff accounts were queried or created outside the local application.
