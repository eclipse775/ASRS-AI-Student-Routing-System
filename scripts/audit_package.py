"""Check repository completeness, supplied-source integrity and captured evidence."""
import csv,hashlib,json,sys,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

REQUIRED=['README.md','API_START_RU.md','run.py','start_windows.bat','start_mac_linux.sh','requirements.txt',
 'setup_gemini_windows.bat','.env.example','app/config.py','app/llm.py',
 'scripts/configure_gemini.py','scripts/check_ai.py','tests/test_gemini.py',
 'app/university.py','tests/test_university.py','docs/SDU_REGISTRATION.md',
 'app/schema.sql','app/security.py','app/ml.py','app/service.py','app/server.py',
 'static/index.html','static/app.js','static/style.css','data/training.json','data/evaluation.json',
 'tests/test_acceptance.py','tests/seed_browser_load.py','scripts/verify.py','scripts/create_staff.py',
 'scripts/browser_checks.mjs','package.json','.github/workflows/tests.yml',
 'docs/proposal.md','docs/requirements.md','docs/architecture.md','docs/api.md','docs/ai_explanation.md',
 'docs/roadmap.md','docs/team_and_process.md','docs/demo_guide.md','docs/criteria_audit.md',
 'docs/testing.md','docs/product_backlog.csv','docs/Sprint_1_2_Plan.xlsx','docs/kanban.html',
 'docs/source_manifest.json','docs/sprint_1/report.md','docs/sprint_2/report.md',
 'docs/sprint_1/backlog.csv','docs/sprint_2/backlog.csv','docs/sprint_1/burndown.csv','docs/sprint_2/burndown.csv',
 'docs/reports/Sprint_1_Report.pdf','docs/reports/Sprint_2_Report.pdf',
 'docs/evidence/verification.json','docs/evidence/model_evaluation.json','docs/evidence/test_results.txt',
 'docs/evidence/browser_checks.json',
 'docs/evidence/01_login.png','docs/evidence/02_student_portal.png','docs/evidence/03_notifications.png',
 'docs/evidence/04_support_queue.png','docs/evidence/05_admin_settings.png',
 'docs/evidence/06_mobile_student.png','docs/evidence/07_sprint_board.png','docs/evidence/08_sdu_registration.png']


def main():
    errors=[]
    for path in REQUIRED:
        p=ROOT/path
        if not p.is_file() or p.stat().st_size==0:errors.append('Missing or empty: '+path)
    if errors:
        print('\n'.join(errors));raise SystemExit(1)
    for row in json.loads((ROOT/'docs/source_manifest.json').read_text()):
        p=ROOT/'docs/source'/row['file']
        if not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest()!=row['sha256']:errors.append('Source changed: '+row['file'])
    with (ROOT/'docs/product_backlog.csv').open(encoding='utf-8-sig',newline='') as f:stories=list(csv.DictReader(f))
    if len(stories)!=10 or sum(int(s['story_estimation']) for s in stories)!=52:errors.append('Backlog source totals do not match.')
    selected=[s for s in stories if int(s['Course Sprint'])<=2]
    if [int(s['#story']) for s in selected]!=[1,2,3,4,5]:errors.append('Sprint 1-2 story selection does not match the workbook.')
    for s in stories:
        if int(s['#story'])<=5 and s['Source Iteration']!=s['Course Sprint']:errors.append('Sprint 1-2 source assignment changed.')
    evidence=json.loads((ROOT/'docs/evidence/verification.json').read_text())
    if not evidence['unit_and_acceptance_tests']['passed'] or not evidence['performance']['targets_met']:errors.append('Verification did not pass.')
    if evidence['model_evaluation']['accuracy']<.9:errors.append('Model target did not pass.')
    browser=json.loads((ROOT/'docs/evidence/browser_checks.json').read_text())
    if browser['status']!='passed' or browser['console_errors'] or any(s['status']!='passed' for s in browser['steps']):
        errors.append('Captured browser checks did not pass.')
    if evidence['browser']!=browser:errors.append('Combined browser evidence is out of date; run scripts/verify.py.')
    test_log=(ROOT/'docs/evidence/test_results.txt').read_text()
    for name in ['test_requested_2024_student_is_year_three_in_2026_2027',
                 'test_other_domains_subdomains_and_suffix_spoofing_are_rejected_on_server',
                 'test_role_course_and_admission_year_cannot_be_forged_by_client',
                 'test_old_demo_migration_preserves_account_id_password_and_request_ownership']:
        if not any(name in line and line.endswith(' ... ok') for line in test_log.splitlines()):
            errors.append('Missing successful SDU acceptance evidence: '+name)
    with zipfile.ZipFile(ROOT/'docs/Sprint_1_2_Plan.xlsx') as z:
        if z.testzip():errors.append('Planning workbook is corrupt.')
    for p in ROOT.rglob('*'):
        if p.is_file() and not any(part in ['.git','__pycache__','instance'] for part in p.parts):
            if p.suffix in ['.py','.json','.js','.html','.css'] and p.stat().st_size==0 and p.name!='__init__.py':errors.append('Empty implementation file: '+str(p.relative_to(ROOT)))
    if errors:print('\n'.join(errors));raise SystemExit(1)
    report={'status':'passed','required_files':len(REQUIRED),'source_files_verified':7,'source_story_points':52,
            'sprint_1_points':8,'sprint_2_points':15,'implemented_stories':['US1','US2','US3','US4','US5'],
            'limits':'This audit checks package/evidence consistency, not real teacher acceptance or institutional compliance.'}
    if '--save' in sys.argv:(ROOT/'docs/evidence/package_audit.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
