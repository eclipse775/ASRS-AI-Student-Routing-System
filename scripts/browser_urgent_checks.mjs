import fs from 'node:fs/promises';
import {spawn,spawnSync} from 'node:child_process';
import path from 'node:path';
import os from 'node:os';
import {fileURLToPath} from 'node:url';
import {chromium} from 'playwright';

// Optional development checks for User Story 6 (urgent requests). Run: node scripts/browser_urgent_checks.mjs
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const shots=process.env.URGENT_SHOT_DIR||await fs.mkdtemp(path.join(os.tmpdir(),'urgent-shots-'));
const temporary=await fs.mkdtemp(path.join(os.tmpdir(),'campus-route-urgent-'));
const database=path.join(temporary,'urgent.sqlite3');
const python=process.env.PYTHON_BINARY||(process.platform==='win32'?'python':'python3');
const port=Number(process.env.BROWSER_TEST_PORT||8766);
const baseURL=`http://127.0.0.1:${port}`;
const server=spawn(python,['run.py','--demo','--ai','local','--port',String(port),'--database',database],{cwd:root,stdio:['ignore','pipe','pipe']});
server.stderr.on('data',()=>{});
process.on('exit',()=>server.kill());
await new Promise((resolve,reject)=>{server.stdout.on('data',c=>{if(String(c).includes('Open http://'))resolve();});server.once('exit',code=>reject(new Error('Server exited: '+code)));setTimeout(()=>reject(new Error('Server start timeout')),15000).unref();});
const options={headless:true};
if(process.env.BROWSER_EXECUTABLE_PATH)options.executablePath=process.env.BROWSER_EXECUTABLE_PATH;
const emergency='I have severe chest pain and I cannot breathe, please send help to the library.';
const normal='My laptop cannot connect to campus wifi and the wireless network is unavailable.';
const steps=[],timings={},errors=[];
let browser;
try{
browser=await chromium.launch(options);
async function open(email,password){
  const context=await browser.newContext({viewport:{width:1440,height:1000}});
  const page=await context.newPage();
  page.on('pageerror',e=>errors.push(e.message));
  page.on('console',m=>{if(m.type()==='error')errors.push(m.text());});
  await page.goto(baseURL);
  await page.getByLabel('Email address').fill(email);
  await page.getByLabel('Password',{exact:true}).fill(password);
  await page.getByRole('button',{name:'Sign in',exact:true}).click();
  await page.getByRole('button',{name:'Sign out'}).waitFor();
  return page;
}
async function check(label,action){await action();steps.push({check:label,status:'passed'});}
async function send(page,message){
  await page.getByLabel('Subject',{exact:true}).fill('Support request');
  await page.getByLabel('Your request',{exact:true}).fill(message);
  await page.getByRole('button',{name:/Send request/}).click();
}
const staff=await open('helpdesk@sdu.edu.kz','Support123!');
const student=await open('240103030@sdu.edu.kz','Student123!');
const region=staff.locator('#alert-region');

await check('No alert banner while nothing is urgent',async()=>{await staff.locator('.queue-card, .empty').first().waitFor();if(await region.locator('.alert-card').count())throw new Error('Unexpected alert');});

await check('Emergency appears on the staff screen within 30 seconds (target: 5-10 s poll)',async()=>{
  const t0=Date.now();
  await send(student,emergency);
  await region.locator('.alert-card').first().waitFor({timeout:30000});
  timings.alert_visible_seconds=(Date.now()-t0)/1000;
  if(timings.alert_visible_seconds>=30)throw new Error('Alert took '+timings.alert_visible_seconds+'s');
});
await check('Alert names the request, the department and the cause; tab title shows the count',async()=>{
  const text=await region.innerText();
  if(!/Urgent request/.test(text)||!/REQ-\d{5}/.test(text)||!/Health Services/.test(text)||!/chest_pain/.test(text))throw new Error(text);
  if(!(await staff.title()).includes('(1) URGENT'))throw new Error('title: '+await staff.title());
});
await staff.screenshot({path:path.join(shots,'staff_alert.png')});
await check('Urgent request is highlighted with a red badge and listed first in the staff queue',async()=>{
  await staff.locator('.queue-card.urgent .pill.urgent').first().waitFor({timeout:4000}); // must not wait for the 15 s queue refresh
  const first=await staff.locator('.queue-card').first().getAttribute('class');
  if(!first.includes('urgent'))throw new Error('First card is not urgent');
});
await check('Student sees the red Urgent badge and that the team was alerted',async()=>{
  await student.locator('.request-card.urgent .pill.urgent').first().waitFor({timeout:20000});
  await student.getByText('Urgent: the team was alerted immediately').first().waitFor();
});
await check('Staff acknowledges the alert and it clears',async()=>{
  await region.getByRole('button',{name:'Acknowledge'}).first().click();
  await region.locator('.alert-card').waitFor({state:'detached',timeout:10000});
  if(!(await staff.title()).includes('Campus Route - Student Support'))throw new Error('Title not reset');
});
await check('A normal request creates no alert',async()=>{
  await send(student,normal);
  await student.getByText(/Request sent to IT Helpdesk/).waitFor();
  await staff.waitForTimeout(6500);
  if(await region.locator('.alert-card').count())throw new Error('Normal request raised an alert');
});
await check('Student reports a missed emergency and staff are alerted',async()=>{
  const card=student.locator('.request-card').filter({hasText:'campus wifi'}).first();
  await card.getByRole('button',{name:'View request'}).click();
  await student.getByRole('button',{name:'This is an emergency'}).click();
  await student.getByLabel('What is happening? (optional)').fill('I feel very unwell');
  await student.getByRole('button',{name:'Alert staff now'}).click();
  await region.locator('.alert-card').first().waitFor({timeout:30000});
  const text=await region.innerText();
  if(!/Missed emergency reported/.test(text)||!/very unwell/.test(text))throw new Error(text);
});
await staff.screenshot({path:path.join(shots,'staff_missed_emergency.png')});
await check('Unacknowledged alert becomes overdue after 2 minutes and the administrator is warned without seeing request content',async()=>{
  const old=new Date(Date.now()-3*60000).toISOString();
  const r=spawnSync(python,['-c',`import sqlite3,sys;c=sqlite3.connect(sys.argv[1]);c.execute("UPDATE urgent_alerts SET created_at=? WHERE acknowledged_at IS NULL",(sys.argv[2],));c.commit()`,database,old]);
  if(r.status!==0)throw new Error(String(r.stderr));
  await region.getByText('Not acknowledged for over 2 minutes').waitFor({timeout:15000});
  const admin=await open('admin@sdu.edu.kz','Admin12345!');
  await admin.locator('#alert-region .alert-card').first().waitFor({timeout:15000});
  const text=await admin.locator('#alert-region').innerText();
  if(!/not acknowledged for over 2 minutes/.test(text)||!/IT Helpdesk/.test(text)||!/REQ-\d{5}/.test(text))throw new Error(text);
  if(/campus wifi|unwell|Support request/.test(text))throw new Error('Administrator banner leaked request content: '+text);
  await admin.screenshot({path:path.join(shots,'admin_supervisor_banner.png')});
});
await check('Live alert feed failure is shown to staff instead of failing silently',async()=>{
  await staff.route('**/api/staff/alerts',route=>route.abort());
  await staff.getByText('Live urgent alerts are unavailable').waitFor({timeout:15000});
  await staff.unroute('**/api/staff/alerts');
  for(let i=errors.length-1;i>=0;i--)if(/net::ERR_FAILED/.test(errors[i]))errors.splice(i,1); // the aborted request above is intentional
});
await check('No console errors (the strict CSP is respected)',async()=>{if(errors.length)throw new Error(errors.join('\n'));});
console.log(JSON.stringify({status:'passed',checks:steps.length,timings,screenshots:shots},null,1));
}catch(error){
  console.error('FAILED after',steps.length,'checks:',error.message);
  process.exitCode=1;
}finally{
  if(browser)await browser.close();
  server.kill();
}
