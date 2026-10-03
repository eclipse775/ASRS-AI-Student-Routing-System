import fs from 'node:fs/promises';
import {spawn} from 'node:child_process';
import path from 'node:path';
import os from 'node:os';
import {fileURLToPath} from 'node:url';
import {chromium,request as apiRequest} from 'playwright';

// Optional development checks; the application itself needs only Python.
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const output=path.join(root,'docs','evidence');
await fs.mkdir(output,{recursive:true});
const temporary=await fs.mkdtemp(path.join(os.tmpdir(),'campus-route-e2e-'));
const database=path.join(temporary,'browser.sqlite3');
const python=process.env.PYTHON_BINARY||(process.platform==='win32'?'python':'python3');
const port=Number(process.env.BROWSER_TEST_PORT||8765);
if(!Number.isInteger(port)||port<1024||port>65535)throw new Error('BROWSER_TEST_PORT must be 1024-65535');
const baseURL=`http://127.0.0.1:${port}`;
const server=spawn(python,['run.py','--demo','--ai','local','--port',String(port),'--database',database],{cwd:root,stdio:['ignore','pipe','pipe']});
// Drain server logs to avoid filling pipes during the 500-request fixture.
server.stderr.on('data',()=>{});
process.on('exit',()=>server.kill());
await new Promise((resolve,reject)=>{server.stdout.on('data',chunk=>{if(String(chunk).includes('Open http://'))resolve();});server.once('exit',code=>reject(new Error('Server exited: '+code)));setTimeout(()=>reject(new Error('Server start timeout')),15000).unref();});
const options={headless:true};
if(process.env.BROWSER_EXECUTABLE_PATH)options.executablePath=process.env.BROWSER_EXECUTABLE_PATH;
if(process.env.BROWSER_SINGLE_PROCESS==='1')options.args=['--no-sandbox','--single-process','--no-zygote','--disable-gpu'];
let browser;
try {
browser=await chromium.launch(options);
const context=await browser.newContext({viewport:{width:1440,height:1000}});
const page=await context.newPage();
const errors=[];
page.on('pageerror',e=>errors.push(e.message));
page.on('console',m=>{if(m.type()==='error')errors.push(m.text());});
const steps=[];
const timings={};
async function check(label,action){await action();steps.push({check:label,status:'passed'});}
async function login(email,password){await page.getByLabel('Email address').fill(email);await page.getByLabel('Password',{exact:true}).fill(password);await page.getByRole('button',{name:'Sign in',exact:true}).click();await page.getByRole('button',{name:'Sign out'}).waitFor();}
async function logout(){await page.getByRole('button',{name:'Sign out'}).click();await page.getByRole('heading',{name:'Welcome back'}).waitFor();}
await page.goto(baseURL);
await page.getByRole('heading',{name:'Welcome back'}).waitFor();
await page.screenshot({path:output+'/01_login.png',fullPage:true});
await check('Student signs in',()=>login('240103030@sdu.edu.kz','Student123!'));
await check('Student profile shows the SDU address, admission year and current course',async()=>{const session=await(await page.request.get(baseURL+'/api/session')).json();const expected=session.university.academic_year_start-2024+1;await page.getByRole('region',{name:'Student profile'}).getByText('240103030@sdu.edu.kz',{exact:true}).waitFor();await page.getByTestId('student-course').getByText(`Year ${expected} · ${session.university.academic_year}`,{exact:true}).waitFor();});
await check('AI mode is visibly local and does not claim a Gemini connection',async()=>{await page.getByTestId('ai-mode').getByText('Local ML · offline',{exact:true}).waitFor();});
await check('Submit an IT request and see correct department',async()=>{await page.getByLabel('Subject',{exact:true}).fill('Campus Wi-Fi connection');await page.getByLabel('Your request',{exact:true}).fill('My laptop cannot connect to campus wifi and the wireless network keeps dropping.');await page.getByRole('button',{name:'Send request'}).click();await page.locator('.request-card').filter({hasText:'Campus Wi-Fi connection'}).getByText('IT Helpdesk',{exact:true}).waitFor();});
await check('Unclear request escalates to staff',async()=>{await page.getByLabel('Subject',{exact:true}).fill('A confusing campus issue');await page.getByLabel('Your request',{exact:true}).fill('I have a confusing situation and would like somebody to look into it.');await page.getByRole('button',{name:'Send request'}).click();await page.locator('.request-card').filter({hasText:'A confusing campus issue'}).getByText('Escalated',{exact:true}).waitFor();});
await page.screenshot({path:output+'/02_student_portal.png',fullPage:true});
await check('Routing confirmation and notifications appear',async()=>{await page.getByRole('link',{name:/Notifications/}).click();await page.getByRole('heading',{name:'Notifications',exact:true}).waitFor();await page.getByText(/Estimated initial response: 8 business hours/).waitFor();});
await page.screenshot({path:output+'/03_notifications.png',fullPage:true});
await logout();
await check('Support signs in and sees pending request',async()=>{await login('helpdesk@sdu.edu.kz','Support123!');await page.locator('.queue-card').filter({hasText:'A confusing campus issue'}).waitFor();});
await page.screenshot({path:output+'/04_support_queue.png',fullPage:true});
await check('Route directly from queue using department selector and Route button',async()=>{const card=page.locator('.queue-card').filter({hasText:'A confusing campus issue'});await card.locator('select').selectOption('academic');await card.getByRole('button',{name:'Route',exact:true}).click();await card.getByRole('button',{name:'Start work'}).waitFor();});
await check('Start work and resolve with a student-visible explanation',async()=>{const card=page.locator('.queue-card').filter({hasText:'Campus Wi-Fi connection'});await card.getByRole('button',{name:'Start work'}).click();await card.getByRole('button',{name:'Resolve request'}).click();await page.getByLabel('Resolution message for the student').fill('Your wireless account has been restored. Please reconnect to campus wifi.');await page.getByRole('button',{name:'Mark resolved'}).click();await page.locator('#request-dialog').waitFor({state:'hidden'});});
await logout();
await login('240103030@sdu.edu.kz','Student123!');
await check('Student sees resolved status and history',async()=>{const card=page.locator('.request-card').filter({hasText:'Campus Wi-Fi connection'});await card.getByText('Resolved',{exact:true}).waitFor();await card.getByRole('button',{name:'View request'}).click();await page.locator('#request-dialog .notice').filter({hasText:'Your wireless account has been restored. Please reconnect to campus wifi.'}).waitFor();await page.getByRole('button',{name:'Close dialog'}).click();});
await check('15-second status polling preserves a typed request draft',async()=>{await page.getByLabel('Subject',{exact:true}).fill('Keep this draft');await page.getByLabel('Your request',{exact:true}).fill('I am typing and do not want to lose these details.');await page.getByLabel('Your request',{exact:true}).focus();const requestContext=await apiRequest.newContext({baseURL:baseURL});const anon=await(await requestContext.get('/api/session')).json();const loginResult=await(await requestContext.post('/api/auth/login',{data:{email:'helpdesk@sdu.edu.kz',password:'Support123!'},headers:{'X-CSRF-Token':anon.csrf_token}})).json();const queue=await(await requestContext.get('/api/staff/requests')).json();const r=queue.requests.find(r=>r.title==='A confusing campus issue');const started=performance.now();const changed=await requestContext.post(`/api/requests/${r.id}/status`,{data:{status:'In Progress',version:r.version},headers:{'X-CSRF-Token':loginResult.csrf_token}});if(!changed.ok())throw new Error('Staff change failed');await page.locator('.request-card').filter({hasText:'A confusing campus issue'}).getByText('In Progress',{exact:true}).waitFor({timeout:20000});timings.status_visible_seconds=(performance.now()-started)/1000;if(await page.getByLabel('Subject',{exact:true}).inputValue()!=='Keep this draft'||await page.getByLabel('Your request',{exact:true}).inputValue()!=='I am typing and do not want to lose these details.')throw new Error('Draft was lost');await requestContext.dispose();});
await check('Mobile layout has no horizontal overflow',async()=>{await page.setViewportSize({width:390,height:844});await page.screenshot({path:output+'/06_mobile_student.png',fullPage:true});const overflow=await page.evaluate(()=>document.documentElement.scrollWidth>window.innerWidth);if(overflow)throw new Error('Mobile viewport overflow');});
await page.setViewportSize({width:1440,height:1000});
await logout();
await check('Administrator adjusts threshold through UI',async()=>{await login('admin@sdu.edu.kz','Admin12345!');await page.getByLabel('Minimum score for automatic routing').fill('0.70');await page.getByRole('button',{name:'Save threshold'}).click();await page.getByRole('status').getByText('Routing threshold saved.').waitFor();});
await page.screenshot({path:output+'/05_admin_settings.png',fullPage:true});
await logout();
await login('helpdesk@sdu.edu.kz','Support123!');
await check('500-request staff queue renders within three seconds',async()=>{await new Promise((resolve,reject)=>{const child=spawn(python,[path.join(root,'tests','seed_browser_load.py'),database]);child.once('exit',code=>code===0?resolve():reject(new Error('Load fixture failed')));});const started=performance.now();await page.reload();await page.waitForFunction(()=>document.querySelectorAll('.queue-card').length===500,{},{timeout:10000});timings.queue_500_navigation_and_render_seconds=(performance.now()-started)/1000;if(timings.queue_500_navigation_and_render_seconds>=3)throw new Error('500-card render exceeded target');});
await logout();
await page.getByRole('button',{name:'Create an account'}).click();
await check('Registration form rejects non-SDU student addresses',async()=>{await page.getByLabel('Full name').fill('Browser Test Student');await page.getByLabel('Email address').fill('240999999@gmail.com');await page.getByLabel('Password',{exact:true}).fill('BrowserStudent123!');await page.getByRole('button',{name:'Create account',exact:true}).click();if(!await page.getByLabel('Email address').evaluate(el=>el.validity.patternMismatch))throw new Error('Wrong-domain email passed browser validation');await page.getByRole('heading',{name:'Create your account'}).waitFor();});
await check('Direct API registration also blocks wrong domains and spoofed suffixes',async()=>{const session=await(await page.request.get(baseURL+'/api/session')).json();for(const email of ['240999999@gmail.com','240999999@sdu.edu.kz.attacker.example']){const response=await page.request.post(baseURL+'/api/auth/register',{data:{name:'Browser Test Student',email,password:'BrowserStudent123!'},headers:{'X-CSRF-Token':session.csrf_token}});if(response.status()!==400)throw new Error('Server accepted a non-SDU registration');}});
await check('Public registration cannot create the helpdesk account',async()=>{const session=await(await page.request.get(baseURL+'/api/session')).json();const response=await page.request.post(baseURL+'/api/auth/register',{data:{name:'Fake Helpdesk',email:'helpdesk@sdu.edu.kz',password:'BrowserStudent123!',role:'support'},headers:{'X-CSRF-Token':session.csrf_token}});if(response.status()!==400)throw new Error('Helpdesk registered through student signup');});
await check('Registration previews course from admission year',async()=>{const session=await(await page.request.get(baseURL+'/api/session')).json();await page.getByLabel('Email address').fill('240999999@sdu.edu.kz');await page.locator('#student-email-hint').getByText(`Admission 2024 · Year ${session.university.academic_year_start-2024+1} · ${session.university.academic_year}`,{exact:true}).waitFor();});
await page.screenshot({path:output+'/08_sdu_registration.png',fullPage:true});
await check('SDU student can register through the interface and gets a student profile',async()=>{await page.getByRole('button',{name:'Create account',exact:true}).click();await page.getByRole('heading',{name:'How can we help?'}).waitFor();await page.getByRole('region',{name:'Student profile'}).getByText('240999999@sdu.edu.kz',{exact:true}).waitFor();});
await check('Student navigating to staff page returns to own portal',async()=>{await page.goto(baseURL+'/staff');await page.getByRole('heading',{name:'How can we help?'}).waitFor();if(page.url()!==baseURL+'/')throw new Error('Unauthorized staff navigation was not redirected');});
await check('Offline sprint board supports filtering, owner edits, status changes and export',async()=>{
  await page.goto(new URL('../docs/kanban.html',import.meta.url).href);
  await page.locator('#sprint').selectOption('1');
  if(await page.locator('.card').count()!==10)throw new Error('Sprint 1 card count mismatch');
  await page.getByLabel('Owner for S1-T01',{exact:true}).fill('Example team member');
  await page.getByLabel('Owner for S1-T01',{exact:true}).press('Tab');
  await page.getByLabel('State for S1-T01',{exact:true}).selectOption('Review');
  await page.reload();
  await page.locator('#sprint').selectOption('1');
  if(await page.getByLabel('Owner for S1-T01',{exact:true}).inputValue()!=='Example team member')throw new Error('Owner not persisted');
  if(await page.getByLabel('State for S1-T01',{exact:true}).inputValue()!=='Review')throw new Error('State not persisted');
  const downloaded=page.waitForEvent('download');
  await page.getByRole('button',{name:'Export current board JSON'}).click();
  const download=await downloaded;
  const exported=JSON.parse(await fs.readFile(await download.path(),'utf8'));
  if(exported.length!==25||exported.find(r=>r.id==='S1-T01').status!=='Review')throw new Error('Export mismatch');
  page.once('dialog',dialog=>dialog.accept());
  await page.getByRole('button',{name:'Reset to delivered snapshot'}).click();
  await page.locator('#sprint').selectOption('all');
  await page.screenshot({path:output+'/07_sprint_board.png',fullPage:true});
});
if(errors.length)throw new Error('Browser errors: '+errors.join('\n'));
await fs.writeFile(output+'/browser_checks.json',JSON.stringify({status:'passed',generated_at_utc:new Date().toISOString(),browser:'Chromium '+browser.version(),viewport:'1440x1000 and 390x844',steps,timings,console_errors:errors,scope:'Local end-to-end demonstration using synthetic accounts. Timings exclude human response.'},null,2)+'\n');
console.log(JSON.stringify({passed:steps.length,errors,screenshots:8}));
} finally {
  if(browser)await browser.close();
  await new Promise(resolve=>{if(server.exitCode!==null)resolve();else{server.once('exit',resolve);server.kill();}});
  await fs.rm(temporary,{recursive:true,force:true});
}
