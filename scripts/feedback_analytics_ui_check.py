#!/usr/bin/env python3
"""Browser check: support sees student feedback, and administrator analytics include today's new requests.

Needs Python Playwright with Chromium. Start a throwaway demo server first:
    python run.py --demo --ai local --no-scheduler --port 8765 --database /tmp/fb.sqlite3
Then:
    python scripts/feedback_analytics_ui_check.py --out docs/evidence/feedback_analytics_ui_check.json --shots /tmp/shots
"""
import argparse, json, os, sys
from datetime import date
from playwright.sync_api import sync_playwright

checks = []


def check(name, ok, detail=""):
    checks.append({"name": name, "passed": bool(ok), "detail": str(detail)})
    print(("PASS " if ok else "FAIL ") + name + (f"  [{detail}]" if detail else ""))


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--base", default="http://127.0.0.1:8765"); ap.add_argument("--out", default=""); ap.add_argument("--shots", default="")
    args = ap.parse_args(); base = args.base
    if args.shots: os.makedirs(args.shots, exist_ok=True)
    shot = lambda page, name: page.screenshot(path=os.path.join(args.shots, name)) if args.shots else None

    def login(ctx, email, password):
        page = ctx.new_page(); page.set_viewport_size({"width": 1280, "height": 1100}); page.goto(base)
        page.wait_for_selector("input[name=email]"); page.fill("input[name=email]", email); page.fill("input[name=password]", password)
        page.click("button[type=submit]:has-text('Sign in')"); page.wait_for_selector(".workspace"); page.wait_for_timeout(700)
        return page

    with sync_playwright() as p:
        browser = p.chromium.launch()
        ad = login(browser.new_context(viewport={"width": 1280, "height": 1100}), "admin@sdu.edu.kz", "Admin12345!")
        ad.goto(base + "/analytics"); ad.wait_for_selector(".feature-metric"); ad.wait_for_timeout(500)
        before = int(ad.locator(".feature-metric strong").first.inner_text())

        st = login(browser.new_context(viewport={"width": 1280, "height": 1100}), "240103030@sdu.edu.kz", "Student123!")
        for title, text in [("Wi-Fi login fails in dorm", "I cannot connect my laptop to campus Wi-Fi in the dorm."),
                            ("Tuition receipt missing", "I paid my tuition yesterday but the receipt is missing in the portal.")]:
            st.fill("#request-title", title); st.fill("#request-message", text); st.click("#request-form button[type=submit]"); st.wait_for_timeout(1000)
        ad.reload(); ad.wait_for_selector(".feature-metric"); ad.wait_for_timeout(500)
        after = int(ad.locator(".feature-metric strong").first.inner_text())
        check("Analytics counts the two requests created a moment ago", after == before + 2, f"{before} -> {after}")
        check("Analytics says the figures are live through today", f"Live figures through {date.today().isoformat()}" in ad.inner_text("body") or "Live figures through" in ad.inner_text("body"))
        shot(ad, "01_admin_analytics_live.png")

        sp = login(browser.new_context(viewport={"width": 1280, "height": 1100}), "helpdesk@sdu.edu.kz", "Support123!")
        ids = sp.evaluate("""async()=>{const rows=(await api('/api/staff/requests')).requests;const out={};
            for(const r of rows){if(!['Wi-Fi login fails in dorm','Tuition receipt missing'].includes(r.title))continue;
              const a=await api(`/api/requests/${r.id}/status`,'POST',{status:'In Progress',version:r.version});
              await api(`/api/requests/${r.id}/status`,'POST',{status:'Resolved',resolution:'Done, please check.',version:a.request.version});out[r.title]=r.id;}
            return out}""")
        before_ratings = sp.evaluate("async()=>(await api('/api/staff/feedback')).summary.count")
        st.reload(); st.wait_for_selector(".request-list"); st.wait_for_timeout(800)
        st.evaluate("""async(ids)=>{await api(`/api/requests/${ids['Wi-Fi login fails in dorm']}/feedback`,'POST',{rating:5,comment:'Fast and very clear instructions, thank you!'});
            await api(`/api/requests/${ids['Tuition receipt missing']}/feedback`,'POST',{rating:2,comment:'The answer took three days.'});}""", ids)

        sp.reload(); sp.wait_for_selector(".stats"); sp.wait_for_timeout(1200)
        nav = sp.inner_text(".nav") if sp.locator(".nav").count() else sp.inner_text("body")
        check("Support navigation has a Student feedback page", "Student feedback" in nav)
        sp.click(".nav-link[data-view=feedback]"); sp.wait_for_selector("#feature-feedback-filter"); sp.wait_for_timeout(900)
        text = sp.inner_text("body")
        check("Feedback page shows both ratings with their comments",
              "Fast and very clear instructions" in text and "The answer took three days." in text and "★★★★★" in text)
        check("Feedback page counts the two new ratings and shows the average and low ratings",
              f"{before_ratings + 2} rating(s)" in text and "Average rating" in text and "Low ratings" in text, f"{before_ratings} -> {before_ratings + 2}")
        shot(sp, "02_support_feedback_page.png")
        sp.select_option("#feedback-filter-rating", "low"); sp.click("#feature-feedback-filter button[type=submit]"); sp.wait_for_timeout(900)
        text = sp.inner_text("body")
        check("Low-rating filter keeps only the 2-star feedback", "The answer took three days." in text and "Fast and very clear" not in text)
        sp.select_option("#feedback-filter-rating", ""); sp.click("#feature-feedback-filter button[type=submit]"); sp.wait_for_timeout(900)
        sp.locator("[data-action=feature-open-feedback-request]").first.click(); sp.wait_for_selector(".feature-request-extra, .feature-detail-section"); sp.wait_for_timeout(1200)
        body = sp.inner_text("body")
        check("Open request shows the student's feedback inside the request details", "Student feedback" in body and ("The answer took three days." in body or "Fast and very clear" in body))
        shot(sp, "03_support_request_feedback.png")
        sp.keyboard.press("Escape"); sp.wait_for_timeout(400)
        check("Resolved card in the queue carries the star rating", sp.locator(".feedback-tag").count() >= 1, sp.locator(".feedback-tag").all_inner_texts())
        shot(sp, "04_support_queue_rating_tag.png")

        ad.reload(); ad.wait_for_selector(".feature-metric"); ad.wait_for_timeout(600)
        body = ad.inner_text("body")
        check("Analytics shows the new ratings and no comment text", "Fast and very clear" not in body and "took three days" not in body)
        shot(ad, "05_admin_analytics_after_feedback.png")
        browser.close()
    result = {"status": "passed" if all(c["passed"] for c in checks) else "failed", "checks": checks}
    if args.out: open(args.out, "w", encoding="utf-8").write(json.dumps(result, indent=2) + "\n")
    print(result["status"], f"{sum(c['passed'] for c in checks)}/{len(checks)}")
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    sys.exit(main())
