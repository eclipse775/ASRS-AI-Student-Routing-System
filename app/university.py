"""SDU address policy and academic-year metadata, derived from the student ID."""
from datetime import datetime, timedelta, timezone
import re

STUDENT_DOMAIN = "sdu.edu.kz"
HELPDESK_EMAIL = "helpdesk@sdu.edu.kz"
STUDENT_EMAIL = re.compile(r"([0-9]{2})[0-9]{7}@sdu\.edu\.kz", re.ASCII)
CAMPUS_ZONE = timezone(timedelta(hours=5))


def current_academic_year(now=None):
    """Return the start year; the academic year changes on 1 September at UTC+5."""
    local = (now or datetime.now(timezone.utc)).astimezone(CAMPUS_ZONE)
    return local.year if local.month >= 9 else local.year - 1


def university_info(now=None):
    start = current_academic_year(now)
    return {"student_email_domain": STUDENT_DOMAIN, "helpdesk_email": HELPDESK_EMAIL,
            "academic_year_start": start, "academic_year": f"{start}-{start + 1}"}


def student_profile(email, now=None):
    """Course is an estimate from admission year, not an official enrollment check."""
    if not isinstance(email, str):
        return None
    match = STUDENT_EMAIL.fullmatch(email.strip().lower())
    if not match:
        return None
    admission = 2000 + int(match.group(1))
    start = current_academic_year(now)
    if admission > start:
        return None
    return {"student_id": email.strip()[:9], "admission_year": admission,
            "academic_year": f"{start}-{start + 1}", "course": start - admission + 1}


def staff_email_allowed(email, role):
    if role == "support":
        return email == HELPDESK_EMAIL
    return role == "admin" and bool(re.fullmatch(r"[a-z][a-z0-9._+-]{0,63}@sdu\.edu\.kz", email, re.ASCII))
