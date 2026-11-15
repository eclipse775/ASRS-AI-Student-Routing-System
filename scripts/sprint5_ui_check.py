#!/usr/bin/env python3
"""Browser check for Sprint 5 (US10 filters, US11 messages, US12 profile, pressable cards and rows).

Needs Python Playwright with Chromium:  pip install playwright && playwright install chromium
Start a clean demo server first, for example:
    python run.py --demo --ai local --no-scheduler --port 8765 --database /tmp/s5.sqlite3
Then run:
    python scripts/sprint5_ui_check.py --base http://127.0.0.1:8765 --out docs/evidence/sprint5_ui_check.json
"""
import argparse, json, sys
from playwright.sync_api import sync_playwright

STUDENT = ("240103030@sdu.edu.kz", "Student123!")
SUPPORT = ("helpdesk@sdu.edu.kz", "Support123!")
ADMIN = ("admin@sdu.edu.kz", "Admin12345!")
REQUESTS = [("Wi-Fi not working in dorm", "I cannot connect my laptop to campus Wi-Fi, and my portal password needs to be reset."),
            ("Tuition payment receipt", "I paid my tuition fee yesterday but the receipt is missing in the portal."),
            ("Transcript for scholarship", "I need an official transcript for my scholarship application by next week."),
            ("Library access card", "My library access card does not open the reading room doors.")]
checks = []


def check(name, ok, detail=""):
    checks.append({"name": name, "passed": bool(ok), "detail": str(detail)})
    print(("PASS " if ok else "FAIL ") + name + (f"  [{detail}]" if detail else ""))


def login(ctx, creds, base):
    page = ctx.new_page(); page.goto(base); page.wait_for_selector("input[name=email]")
    page.fill("input[name=email]", creds[0]); page.fill("input[name=password]", creds[1])
    page.click("button[type=submit]:has-text('Sign in')"); page.wait_for_selector(".workspace"); page.wait_for_timeout(600)
    return page


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--base", default="http://127.0.0.1:8765"); ap.add_argument("--out", default="")
    args = ap.parse_args(); base = args.base
    with sync_playwright() as p:
        browser = p.chromium.launch()
        sctx = browser.new_context(permissions=["clipboard-read", "clipboard-write"], viewport={"width": 1280, "height": 1300})
        st = login(sctx, STUDENT, base)
        before = int(st.inner_text(".stats .stat:nth-child(1) .stat-value"))
        for title, text in REQUESTS:
            st.fill("#request-title", title); st.fill("#request-message", text)
            st.click("#request-form button[type=submit]"); st.wait_for_timeout(900)
        sp = login(browser.new_context(viewport={"width": 1280, "height": 1300}), SUPPORT, base)
        items = sp.evaluate("async()=>(await api('/api/staff/requests')).requests.map(x=>({id:x.id,title:x.title}))")
        tuition = next(x for x in items if x["title"] == "Tuition payment receipt")
        sp.evaluate("async(id)=>{await api(`/api/requests/${id}/messages`,'POST',{body:'Could you send the payment date and the bank reference number?',client_id:'check-msg-0001'})}", tuition["id"])

        # US10 with pressable cards
        st.reload(); st.wait_for_selector(".request-list"); st.wait_for_timeout(800)
        count = lambda: st.inner_text("#student-request-filter-count")
        total = before + len(REQUESTS)
        check("US10 list starts unfiltered", count() == f"Showing {total} of {total} requests", count())
        st.click("button.stat-btn[data-status='Open']"); st.wait_for_timeout(300)
        check("Open requests card applies the Open filter", st.input_value("#student-request-status") == "Open" and "Showing" in count(), count())
        st.click("button.stat-btn[data-status='Resolved']"); st.wait_for_timeout(300)
        check("Resolved card applies the Resolved filter", st.input_value("#student-request-status") == "Resolved", count())
        st.click("button.stat-btn[data-status='']"); st.wait_for_timeout(300)
        check("Total card clears the filters", count() == f"Showing {total} of {total} requests", count())
        st.fill("#student-request-search", "receipt"); st.wait_for_timeout(300)
        check("Search finds the request by message text", count() == f"Showing 1 of {total} requests", count())
        st.fill("#student-request-search", "")

        # US11
        st.locator(".request-card:has-text('Tuition payment receipt') [data-action=detail]").first.click()
        st.wait_for_selector(".thread"); st.wait_for_timeout(800)
        check("US11 student sees the staff message", "bank reference number" in st.inner_text(".thread-list"))
        st.fill("#message-body", "I paid on 12 November, reference TR-48213. Thank you!"); st.click(".thread-form button[type=submit]"); st.wait_for_timeout(800)
        check("US11 student reply appears in the thread", "TR-48213" in st.inner_text(".thread-list"))
        st.keyboard.press("Escape"); st.wait_for_timeout(300)

        # US12 + pressable rows
        st.click(".nav-link[data-view=profile]"); st.wait_for_selector(".ph-card"); st.wait_for_timeout(1500)
        check("US12 profile shows student ID and academic year", st.inner_text("[data-testid=profile-student-id]") == "240103030" and "2026" in st.inner_text("[data-testid=profile-academic-year]"))
        st.click(".detail-row:has-text('Student ID')"); st.wait_for_timeout(300)
        check("Clicking the Student ID row copies it", st.inner_text("#toast") == "Student ID copied." and st.evaluate("navigator.clipboard.readText()") == "240103030")
        st.click(".detail-row:has-text('Academic year')"); st.wait_for_timeout(300)
        check("Clicking the Academic year row copies it", st.evaluate("navigator.clipboard.readText()").startswith("2026-"))
        st.click("button.stat-btn[data-status='Resolved']"); st.wait_for_selector("#student-request-filters"); st.wait_for_timeout(400)
        check("Profile Resolved card opens the filtered request list", st.input_value("#student-request-status") == "Resolved")

        # support and admin
        sp.reload(); sp.wait_for_selector(".stats"); sp.wait_for_timeout(900)
        sp.click("button.stat-btn[data-preset=urgent]"); sp.wait_for_timeout(600)
        check("Queue Marked urgent card sets the priority filter", sp.input_value("#filter-priority") == "urgent")
        sp.click("button.stat-btn[data-preset=review]"); sp.wait_for_timeout(600)
        check("Queue Awaiting review card sets the status filter", sp.input_value("#filter-status") == "Escalated")
        sp.click("button.stat-btn[data-preset=all]"); sp.wait_for_timeout(600)
        check("Queue In this view card clears the filters", sp.input_value("#filter-status") == "" and sp.input_value("#filter-priority") == "")
        sp.click(".nav-link[data-view=profile]"); sp.wait_for_selector(".ph-card"); sp.wait_for_timeout(500)
        sp.click("a.stat-btn:has-text('Unread messages')"); sp.wait_for_timeout(500)
        check("Support profile Unread messages card opens the queue", sp.evaluate("location.pathname") == "/staff")
        ad = login(browser.new_context(viewport={"width": 1280, "height": 900}), ADMIN, base)
        ad.click(".nav-link[data-view=profile]"); ad.wait_for_selector(".ph-card"); ad.wait_for_timeout(400)
        ad.click("a.stat-btn:has-text('Settings and audit')"); ad.wait_for_timeout(500)
        check("Admin profile Access card opens routing settings", ad.evaluate("location.pathname") == "/settings")
        mob = login(browser.new_context(viewport={"width": 390, "height": 844}, is_mobile=True), STUDENT, base)
        mob.goto(base + "/profile"); mob.wait_for_selector(".ph-card"); mob.wait_for_timeout(600)
        check("Profile has no horizontal overflow at 390x844", not mob.evaluate("document.documentElement.scrollWidth>document.documentElement.clientWidth"))
        browser.close()
    result = {"status": "passed" if all(c["passed"] for c in checks) else "failed", "checks": checks}
    if args.out:
        open(args.out, "w", encoding="utf-8").write(json.dumps(result, indent=2) + "\n")
    print(result["status"], f"{sum(c['passed'] for c in checks)}/{len(checks)}")
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    sys.exit(main())
