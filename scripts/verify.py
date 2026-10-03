"""Execute the acceptance suite and record actual model/performance evidence."""
from datetime import datetime, timezone
import io,json,platform,statistics,sys,tempfile,time,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from app.database import connection,seed_demo
from app.server import Application
from app.ml import Classifier
from scripts.evaluate_model import evaluate
from tests.test_acceptance import Client


def performance():
    with tempfile.TemporaryDirectory() as temp:
        path=Path(temp)/'performance.sqlite3';app=Application(path,classifier=Classifier(ROOT/"data/training.json"));seed_demo(path)
        student=Client(app);support=Client(app)
        student.login('240103030@sdu.edu.kz','Student123!');support.login('helpdesk@sdu.edu.kz','Support123!')
        samples=[];notification=[];request=None
        for _ in range(20):
            start=time.perf_counter();status,data=student.create();samples.append(time.perf_counter()-start)
            if status!=201:raise RuntimeError(data)
            request=data['request'];notes=student.call('GET','/api/notifications')[1]['notifications']
            notification.append((datetime.fromisoformat(notes[0]['created_at'])-datetime.fromisoformat(request['created_at'])).total_seconds())
        start=time.perf_counter()
        status,data=support.call('POST',f"/api/requests/{request['id']}/status",{'status':'In Progress','version':request['version']})
        observed=student.call('GET',f"/api/requests/{request['id']}")[1]['request']
        if status!=200 or observed['status']!='In Progress':raise RuntimeError('Status propagation failed')
        propagation=time.perf_counter()-start
        with connection(path) as db:
            row=db.execute('SELECT * FROM requests ORDER BY id LIMIT 1').fetchone()
            columns=[key for key in row.keys() if key!='id']
            sql='INSERT INTO requests ('+','.join(columns)+') VALUES ('+','.join('?'*len(columns))+')'
            db.executemany(sql,[tuple(row[k] for k in columns)]*480)
        start=time.perf_counter();status,data=support.call('GET','/api/staff/requests?open=1');queue=time.perf_counter()-start
        if status!=200 or len(data['requests'])!=500:raise RuntimeError('Queue fixture failed')
        return {'environment':'Local in-process WSGI API calls and synthetic SQLite fixtures',
                'routing_samples':len(samples),'routing_mean_seconds':round(statistics.mean(samples),6),
                'routing_max_seconds':round(max(samples),6),'notification_max_seconds':round(max(notification),6),
                'status_update_and_owner_read_seconds':round(propagation,6),'queue_500_response_seconds':round(queue,6),
                'targets_met':max(samples)<30 and max(notification)<60 and propagation<60 and queue<3,
                'limitation':'API timings measure local Naive Bayes only; exclude external Gemini latency, network, browser rendering and human response.'}


def main():
    evidence=ROOT/'docs/evidence';evidence.mkdir(parents=True,exist_ok=True)
    stream=io.StringIO();suite=unittest.defaultTestLoader.discover(str(ROOT/'tests'))
    start=time.perf_counter();result=unittest.TextTestRunner(stream=stream,verbosity=2).run(suite);elapsed=time.perf_counter()-start
    (evidence/'test_results.txt').write_text(stream.getvalue())
    model=evaluate();(evidence/'model_evaluation.json').write_text(json.dumps(model,indent=2)+'\n')
    browser_path=evidence/'browser_checks.json'
    browser=json.loads(browser_path.read_text()) if browser_path.exists() else {'status':'Not executed','reason':'A working browser runtime was not available at this execution.'}
    metrics=performance()
    report={'generated_at_utc':datetime.now(timezone.utc).isoformat(),'python':platform.python_version(),
            'unit_and_acceptance_tests':{'run':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),
                                         'passed':result.wasSuccessful(),'elapsed_seconds':round(elapsed,3)},
            'model_evaluation':{k:v for k,v in model.items() if k!='results'},'performance':metrics,'browser':browser,
            'external_ai':{'integration':'Implemented and tested with mocked HTTP responses', 'live_provider_test':'Not executed: no API key was supplied', 'model':'gemini-3.1-flash-lite', 'activation':'Run setup_gemini_windows.bat, restart, then python scripts/check_ai.py'},
            'university_registration':{'domain':'sdu.edu.kz','student_email':'9 ASCII digits followed by @sdu.edu.kz','support_account':'helpdesk@sdu.edu.kz','course_rule':'Academic-year start minus admission year plus 1','example':{'email':'240103030@sdu.edu.kz','academic_year':'2026-2027','admission_year':2024,'course':3},'ownership_verification':'Not implemented: address-format restriction does not verify control of the mailbox.'},
            'ci_status':'Configured in .github/workflows/tests.yml; no remote GitHub execution claimed.',
            'human_review':'Staffing SLA, Product Owner acceptance, team names and actual ceremonies require real course records.'}
    (evidence/'verification.json').write_text(json.dumps(report,indent=2)+'\n')
    print(f"Tests: {result.testsRun}, failures: {len(result.failures)}, errors: {len(result.errors)}")
    print(json.dumps(metrics,indent=2))
    if not result.wasSuccessful() or not metrics['targets_met']:raise SystemExit(1)


if __name__=='__main__':main()
