// เชื่อม UI ดีไซน์ (index.html) กับ backend Python ผ่าน pywebview.
// ถ้าเปิดในเบราว์เซอร์ธรรมดา (ไม่มี pywebview) จะใช้ข้อมูลตัวอย่างเพื่อให้เห็นดีไซน์ครบ

const DEMO = {
  devices: [
    {addr:"127.0.0.1:7555",selected:true,dot:"#34D399"},
    {addr:"127.0.0.1:7556",selected:true,dot:"#34D399"},
    {addr:"127.0.0.1:7557",selected:true,dot:"#34D399"},
    {addr:"127.0.0.1:7558",selected:true,dot:"#38BDF8"},
    {addr:"127.0.0.1:7559",selected:true,dot:"#F87171"},
    {addr:"127.0.0.1:7560",selected:false,dot:"#58677E"},
  ],
  connected:6, selectedCount:5,
  profiles:["ล็อกอิน + เก็บของประจำวัน","ข้ามโฆษณา","รับของใหม่จับภาพ"],
  currentProfile:"ล็อกอิน + เก็บของประจำวัน",
  steps:18, accountsTotal:63, accountsChecked:50,
  progress:[
    {n:"จอ 1",addr:":7555",label:"กำลังรัน",color:"#38BDF8",dot:"#38BDF8",acct:"thanapon_042",step:"แตะคลังไอเทม (3/18)",pct:17,bar:"#34D399",done:"12 / 50"},
    {n:"จอ 2",addr:":7556",label:"กำลังรัน",color:"#38BDF8",dot:"#38BDF8",acct:"thanapon_043",step:"ยืนยันภาพ anchor (7/18)",pct:39,bar:"#34D399",done:"11 / 50"},
    {n:"จอ 3",addr:":7557",label:"รอคิว",color:"#7C8CA3",dot:"#58677E",acct:"รอเริ่ม",step:"อยู่ในคิว รอจอว่าง",pct:0,bar:"#34D399",done:"0 / 50"},
    {n:"จอ 4",addr:":7558",label:"เสร็จแล้ว",color:"#34D399",dot:"#34D399",acct:"thanapon_017",step:"เก็บของสำเร็จ · ออกจากเกม",pct:100,bar:"#34D399",done:"50 / 50"},
    {n:"จอ 5",addr:":7559",label:"ติด · บันทึกแล้ว",color:"#F87171",dot:"#F87171",acct:"thanapon_051",step:"ล็อกอินไม่ผ่าน (9/18)",pct:50,bar:"#F87171",done:"8 / 50"},
  ],
  log:[{ts:"14:38:07",text:"✕ จอ 5 · thanapon_051 ล็อกอินไม่ผ่าน — บันทึกรายงานปัญหา",kind:"err"}],
};

let PY = null;          // window.pywebview.api เมื่อพร้อม
const hasPy = () => PY !== null;

function icons(){ if(window.lucide) lucide.createIcons(); }

function esc(s){ return String(s==null?"":s).replace(/[&<>"]/g, c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c])); }
// ใส่ค่าลงใน onclick="fn('...')" ให้ปลอดภัย: ต้อง escape ให้ JS ก่อน (\ และ ') แล้วค่อย escape ให้ HTML
// สลับลำดับไม่ได้ — เบราว์เซอร์ decode entity ก่อน JS parse เสมอ (&#39; จะกลายเป็น ' แล้วปิดสตริงกลางคัน)
function jsq(s){ return esc(String(s==null?"":s).replace(/\\/g,"\\\\").replace(/\x27/g,"\\\x27")); }

// ---------- nav rail ----------
let CURRENT = "home";
function renderNav(){
  document.querySelectorAll('#navRail .nav').forEach(el=>{
    const page = el.dataset.page, active = page===CURRENT;
    const color = active ? "#E7EDF6" : "#5C6B82";
    const barDisp = active ? "block" : "none";
    el.style.cssText = "position:relative;display:flex;flex-direction:column;align-items:center;gap:6px;padding:13px 0;cursor:pointer;color:"+color+(el.dataset.bottom?";margin-top:auto":"");
    el.innerHTML = '<div style="position:absolute;left:0;top:9px;bottom:9px;width:3px;border-radius:0 3px 3px 0;background:#34D399;display:'+barDisp+'"></div>'
      + '<i data-lucide="'+el.dataset.icon+'" width="21" height="21" stroke-width="1.85"></i>'
      + '<span style="font-size:9.5px;font-weight:500">'+esc(el.dataset.label)+'</span>';
    el.onclick = ()=> switchPage(page);
  });
  icons();
}
function switchPage(page){
  CURRENT = page;
  document.querySelectorAll('#content .page').forEach(p=>{
    p.style.display = (p.dataset.page===page) ? "flex" : "none";
  });
  renderNav();
  if(page==="acc") renderAccounts();
  // กลับเข้าหน้าสคริปต์ต้องวาดมุมมองที่ค้างไว้ให้ถูก — ถ้าค้างโหมดโฟลว์แล้วเรียกแค่ renderSteps
  // ผังจะยังเป็นของเดิม (บั๊กคลาสเดียวกับตอนกดแก้ไขชุดคำสั่งย่อย)
  else if(page==="script"){ if(typeof refreshScriptView==='function') refreshScriptView(); else renderSteps(); }
  else if(page==="tools") initToolTabs();
  else if(page==="set"){ loadSettings(); if(typeof loadResetCfg==='function') loadResetCfg(); }
  icons();
}
function notReady(name){ window.onLog({ts:new Date().toTimeString().slice(0,8),text:"'"+name+"' กำลังย้ายมาเฟสถัดไป",kind:"warn"}); }

// ---------- render state ----------
function render(s){
  // sidebar header + badge
  document.getElementById('connCount').textContent = s.connected + " เชื่อมต่อ";
  const badge = document.getElementById('connBadge');
  if(s.connected>0){
    badge.style.background="rgba(16,185,129,.09)"; badge.style.borderColor="rgba(16,185,129,.22)";
    badge.innerHTML = '<span style="width:8px;height:8px;border-radius:50%;background:#34D399;flex:none"></span><span style="font-size:12.5px;color:#A7F3D0;font-weight:500">เชื่อมต่อ '+s.connected+' จอ · เลือก '+s.selectedCount+'</span>';
  } else {
    badge.style.background="rgba(163,98,7,.10)"; badge.style.borderColor="rgba(163,98,7,.28)";
    badge.innerHTML = '<span style="width:8px;height:8px;border-radius:50%;background:#F59E0B;flex:none"></span><span style="font-size:12.5px;color:#FCD9A5;font-weight:500">ยังไม่พบจอ — กดสแกน</span>';
  }

  // device list
  const dl = document.getElementById('deviceList');
  dl.innerHTML = s.devices.map(d=>{
    const boxBg = d.selected ? "#10B981" : "transparent";
    const boxBorder = d.selected ? "#10B981" : "#2A3547";
    const checkOp = d.selected ? "1" : "0";
    const dot = d.dot || "#34D399";
    return '<div style="display:flex;align-items:center;gap:10px;padding:9px 10px;border-radius:9px;background:#121A28;border:1px solid #1B2434">'
      + '<span onclick="toggleDevice(\''+d.addr+'\')" style="width:16px;height:16px;border-radius:5px;flex:none;display:flex;align-items:center;justify-content:center;cursor:pointer;background:'+boxBg+';border:1.5px solid '+boxBorder+'"><i data-lucide="check" width="11" height="11" stroke-width="3" style="color:#04120C;opacity:'+checkOp+'"></i></span>'
      + '<i data-lucide="monitor" width="15" height="15" stroke-width="1.75" style="color:#5C6B82;flex:none"></i>'
      + '<span style="flex:1;font-family:\'IBM Plex Mono\',monospace;font-size:11.5px;color:#C7D2E0">'+esc(d.addr)+'</span>'
      + '<span style="width:7px;height:7px;border-radius:50%;background:'+dot+';flex:none"></span>'
      + '<i data-lucide="x" width="13" height="13" stroke-width="2" style="color:#455266;flex:none;cursor:pointer" onclick="removeDevice(\''+d.addr+'\')" title="เอาจอนี้ออก"></i>'
      + '</div>';
  }).join("") || '<div style="font-size:12px;color:#5C6B82;padding:8px 2px">— ยังไม่พบจอ กดสแกนพอร์ต —</div>';

  // profile select
  const sel = document.getElementById('profileSelect');
  sel.innerHTML = (s.profiles.length?s.profiles:["(ไม่มีสคริปต์)"]).map(p=>'<option '+(p===s.currentProfile?'selected':'')+'>'+esc(p)+'</option>').join("");

  // pre-flight card
  const ok="#34D399", no="#F59E0B";
  setPf('pfDevices', s.selectedCount>0, "จอที่เลือก", s.selectedCount+" จอ");
  setPf('pfAccounts', s.accountsChecked>0, "บัญชีที่จะทำ", s.accountsChecked+" รหัส");
  setPf('pfScript', s.steps>0, "สคริปต์", s.steps+" สเต็ป");

  renderProgressList(s.progress);
  if(s.log && s.log.length) onLog(s.log[s.log.length-1]);
  icons();
}
let LAST_PROGRESS_SIG = null;
function renderProgressList(arr){
  const box = document.getElementById('progressList');
  if(!box) return;
  // ข้ามรีเรนเดอร์ถ้าข้อมูลเหมือนเดิมทุกตัวอักษร — poll ทุก 1 วิ แต่หลายขั้น (sleep/รอภาพ) ไม่ขยับ
  // สถานะหลายวิ ถ้ารีบิลด์ DOM+ไอคอนทุกครั้งอยู่ดี จะแย่ง CPU จากจอ ADB โดยเปล่าประโยชน์
  // โดยเฉพาะตอนรันพร้อมกันหลายจอ (10 จอ = 10 การ์ดรีบิลด์ทุกวิ ทั้งที่ส่วนใหญ่ไม่เปลี่ยน)
  const sig = JSON.stringify(arr || []);
  if(sig === LAST_PROGRESS_SIG) return;
  LAST_PROGRESS_SIG = sig;
  if(arr && arr.length){
    box.innerHTML = arr.map(p=>(
      '<div style="border-radius:11px;background:#121A28;border:1px solid #1B2434;padding:13px 15px;display:flex;flex-direction:column;gap:9px">'
      + '<div style="display:flex;align-items:center;gap:10px"><span style="width:9px;height:9px;border-radius:50%;background:'+p.dot+';flex:none"></span><span style="font-weight:600;font-size:13.5px">'+esc(p.n)+'</span><span style="font-family:\'IBM Plex Mono\',monospace;font-size:11px;color:#5C6B82">'+esc(p.addr)+'</span><span style="margin-left:auto;font-size:12px;font-weight:500;color:'+p.color+'">'+esc(p.label)+'</span></div>'
      + '<div style="display:flex;align-items:center;gap:8px;font-size:12px;color:#90A0B7"><i data-lucide="user" width="13" height="13" stroke-width="1.75" style="color:#5C6B82"></i><span style="color:#C7D2E0;font-family:\'IBM Plex Mono\',monospace;font-size:11.5px">'+esc(p.acct)+'</span><span style="color:#455266">·</span><span>'+esc(p.step)+'</span></div>'
      + '<div style="display:flex;align-items:center;gap:10px"><div style="flex:1;height:5px;border-radius:9px;background:#1B2434;overflow:hidden"><div style="height:100%;border-radius:9px;background:'+p.bar+';width:'+p.pct+'%"></div></div><span style="font-family:\'IBM Plex Mono\',monospace;font-size:11px;color:#7C8CA3;min-width:56px;text-align:right">'+esc(p.done)+'</span></div>'
      + '</div>')).join("");
  } else {
    box.innerHTML = '<div style="font-size:12.5px;color:#5C6B82;padding:8px 2px">ยังไม่ได้รัน — เลือกจอ+สคริปต์ แล้วกดรัน</div>';
  }
  icons();
}
function setPf(id, good, label, val){
  const el = document.getElementById(id);
  const color = good ? "#34D399" : "#F59E0B";
  el.innerHTML = '<i data-lucide="'+(good?'check':'alert-triangle')+'" width="16" height="16" stroke-width="2.25" style="color:'+color+'"></i>'
    + '<span style="color:#C7D2E0">'+esc(label)+'</span><span style="margin-left:auto;font-family:\'IBM Plex Mono\',monospace">'+esc(val)+'</span>';
}

// ---------- log ----------
window.onLog = function(entry){
  document.getElementById('logTs').textContent = "["+entry.ts+"]";
  const c = {ok:"#6EE7B7",err:"#FCA5A5",warn:"#FBBF24",info:"#90A0B7"}[entry.kind] || "#90A0B7";
  const t = document.getElementById('logText'); t.textContent = entry.text; t.style.color = c;
};

// ---------- actions (เรียก Python เมื่อมี, ไม่งั้นใช้ demo) ----------
async function refresh(fn){
  let s;
  if(hasPy()){ s = await (fn ? fn() : PY.get_state()); }
  else { s = DEMO; }
  render(s);
}
async function scanPorts(btn){ if(btn) btn.querySelector('span,i'); if(hasPy()){ await refresh(()=>PY.scan()); } else { window.onLog({ts:"--:--:--",text:"(เดโม) สแกน — รันจริงผ่าน python web_app.py",kind:"info"}); } }
async function connectManual(){ const a=document.getElementById('manualAddr').value; if(hasPy()) await refresh(()=>PY.connect_manual(a)); }
async function toggleDevice(a){ if(hasPy()) await refresh(()=>PY.toggle_device(a)); }
async function removeDevice(a){ if(hasPy()) await refresh(()=>PY.remove_device(a)); }
async function selectProfile(n){ if(hasPy()) await refresh(()=>PY.select_profile(n)); }
let RUN_POLL = null;
let AWAITING_BATCH = false;   // โหมด "หยุดรอตรวจทานทีละชุด" — รอผู้ใช้กด "รันชุดถัดไป"
function onRunBtnClick(){ AWAITING_BATCH ? continueBatch() : runMacro(); }
async function runMacro(){
  if(!hasPy()){ notReady('รัน (ต้องเปิดผ่าน .exe)'); return; }
  const poll = (document.getElementById('anchorPoll')||{}).value || '2.0';
  const mode = (document.getElementById('runMode')||{}).value || 'parallel';
  // 'sequential' = ยิงทีละจอ (กันแคปช่าเวลาเว็บจับได้ว่ากดพร้อมกันหลายเครื่อง)
  const stuck = (document.getElementById('stuckMode')||{}).value || 'next';
  const r = await PY.run(poll, mode==='batch', mode==='sequential', null, stuck);
  if(r && r.ok){ LAST_PROGRESS_SIG = null; setRunBtn('running'); startRunPoll(); }
}
async function continueBatch(){
  if(!hasPy()) return;
  const r = await PY.continue_batch();
  if(r && r.ok){ LAST_PROGRESS_SIG = null; setRunBtn('running'); startRunPoll(); }
}
async function stopMacro(){ if(hasPy()) await PY.stop(); AWAITING_BATCH=false; setRunBtn('idle'); }
function startRunPoll(){
  if(RUN_POLL) clearInterval(RUN_POLL);
  RUN_POLL = setInterval(async ()=>{
    if(!hasPy()) return;
    const rs = await PY.get_run_state();
    renderProgressList(rs.progress);
    if(rs.log && rs.log.length){ onLog(rs.log[rs.log.length-1]); }
    if(typeof flowApplyHighlight==='function') flowApplyHighlight(rs.progress); // ไฮไลต์บล็อกสดบนผัง
    if(typeof pollPausedList==='function') pollPausedList(); // แผง 'จอที่รอแก้ไข' (anchor_on_fail='pause')
    // มีจอรอแก้ไข/กำลังรันต่อ (resume) อยู่ -> ต้อง poll ต่อแม้ rs.running จะเป็น false แล้ว
    // (จอที่เหลือรันจบ/ค้างหมดแล้ว แต่ยังมีจอรอผู้ใช้อยู่ ไม่งั้นแผงจะหยุดอัปเดตทันทีที่จอสุดท้ายค้าง)
    const stillActive = (rs.pausedCount||0) > 0 || (rs.activeResumes||0) > 0;
    if(rs.running){
      setRunBtn('running');
    } else if(stillActive){
      setRunBtn('idle');
    } else {
      clearInterval(RUN_POLL); RUN_POLL=null;
      if(typeof flowApplyHighlight==='function') flowApplyHighlight([]);
      if(rs.awaitingNextBatch){ setRunBtn('awaiting', rs.remainingBatch); }
      else { setRunBtn('idle'); }
    }
  }, 1000);
}
function setRunBtn(state, remaining){
  const b = document.getElementById('runBtn'); if(!b) return;
  AWAITING_BATCH = (state === 'awaiting');
  if(state === 'running'){
    b.innerHTML = '<i data-lucide="loader" width="18" height="18" stroke-width="2.25" style="animation:spin 1.4s linear infinite"></i>กำลังรัน…';
    b.style.cursor = 'default';
  } else if(state === 'awaiting'){
    b.innerHTML = '<i data-lucide="play" width="18" height="18" stroke-width="2.25"></i>รันชุดถัดไป (เหลือ '+(remaining||0)+')';
    b.style.cursor = 'pointer';
  } else {
    b.innerHTML = '<i data-lucide="play" width="18" height="18" stroke-width="2.25"></i>รัน';
    b.style.cursor = 'pointer';
  }
  icons();
}

// ---------- window controls ----------
function winMin(){ if(hasPy()&&PY.win_min) PY.win_min(); }
function winMax(){ if(hasPy()&&PY.win_max) PY.win_max(); }
function winClose(){ if(hasPy()&&PY.win_close) PY.win_close(); }

// ================= ACCOUNTS =================
const DEMO_ACC = {groupNames:["หลัก (A)","สำรอง (B)"], groups:[
  {name:"หลัก (A)",count:3,allChecked:true,accounts:[
    {email:"a@x.com",name:"thanapon_017",grp:"หลัก (A)",tok:"ya29.a0Af…9Qk",checked:true,dot:"#38BDF8"},
    {email:"b@x.com",name:"thanapon_042",grp:"หลัก (A)",tok:"ya29.a0Af…2Lm",checked:true,dot:"#34D399"},
    {email:"c@x.com",name:"thanapon_051",grp:"หลัก (A)",tok:"ya29.a0Af…7Zx",checked:true,dot:"#F87171"}]},
  {name:"สำรอง (B)",count:2,allChecked:false,accounts:[
    {email:"d@x.com",name:"thanapon_088",grp:"สำรอง (B)",tok:"—",checked:false,dot:"#58677E"},
    {email:"e@x.com",name:"thanapon_090",grp:"สำรอง (B)",tok:"ya29.a0Af…4Rt",checked:true,dot:"#58677E"}]},
]};
// เก็บข้อมูลบัญชีดิบไว้ฝั่ง JS แล้วให้ปุ่มดินสออ้างด้วยอีเมล — ไม่ยัด JSON (ที่มีรหัสผ่าน/โทเคน)
// ลงใน onclick attribute เพราะอักขระอย่าง & หรือ ' จะทำ HTML พังแล้วฟอร์มเติมค่าเพี้ยน
let ACCT_CACHE = {};
async function renderAccounts(){
  const q = (document.getElementById('accSearch')||{}).value || "";
  const s = hasPy() ? await PY.get_accounts_grouped(q) : DEMO_ACC;
  ACCT_CACHE = {};
  (s.groups||[]).forEach(g=>(g.accounts||[]).forEach(a=>{ ACCT_CACHE[a.email] = a; }));
  const dl = document.getElementById('groupNamesList');
  if(dl) dl.innerHTML = (s.groupNames||[]).map(n=>'<option value="'+esc(n)+'">').join("");
  const box = document.getElementById('accGroups');
  box.innerHTML = s.groups.map(g=>(
    '<div style="display:flex;flex-direction:column;gap:7px">'
    + '<div style="display:flex;align-items:center;gap:10px;padding:8px 10px">'
    + '<span onclick="toggleGroup(\''+esc(g.name)+'\','+(!g.allChecked)+')" style="width:16px;height:16px;border-radius:5px;flex:none;cursor:pointer;display:flex;align-items:center;justify-content:center;background:'+(g.allChecked?'#10B981':'transparent')+';border:1.5px solid '+(g.allChecked?'#10B981':'#2A3547')+'" title="ติ๊กเลือกทั้งกลุ่ม"><i data-lucide="check" width="11" height="11" stroke-width="3" style="color:#04120C;opacity:'+(g.allChecked?'1':'0')+'"></i></span>'
    + '<i data-lucide="folder" width="16" height="16" stroke-width="1.75" style="color:#7C8CA3"></i><span style="font-size:13px;font-weight:600">กลุ่ม: '+esc(g.name)+'</span><span style="font-size:11.5px;color:#5C6B82;font-family:\'IBM Plex Mono\',monospace">'+g.count+' บัญชี</span>'
    + '<i data-lucide="trash-2" width="14" height="14" stroke-width="1.75" style="color:#455266;cursor:pointer;margin-left:auto" title="ลบทั้งกลุ่ม" onclick="deleteGroup(\''+esc(g.name)+'\')"></i>'
    + '</div>'
    + g.accounts.map(a=>(
        '<div style="display:flex;align-items:center;gap:11px;padding:11px 12px;margin-left:8px;border-radius:10px;background:#121A28;border:1px solid #1B2434">'
        + '<span style="width:9px;height:9px;border-radius:50%;background:'+a.dot+';flex:none"></span>'
        + '<span onclick="toggleAccount(\''+a.email+'\')" style="width:16px;height:16px;border-radius:5px;flex:none;cursor:pointer;display:flex;align-items:center;justify-content:center;background:'+(a.checked?'#10B981':'transparent')+';border:1.5px solid '+(a.checked?'#10B981':'#2A3547')+'"><i data-lucide="check" width="11" height="11" stroke-width="3" style="color:#04120C;opacity:'+(a.checked?'1':'0')+'"></i></span>'
        + '<div style="flex:1;min-width:0"><div style="font-size:13px;font-weight:500">'+esc(a.name)+'</div><div style="font-size:11px;color:#5C6B82;font-family:\'IBM Plex Mono\',monospace">กลุ่ม '+esc(a.grp)+' · '+esc(a.tok)+'</div></div>'
        + '<i data-lucide="pencil" width="15" height="15" stroke-width="1.75" style="color:#7C8CA3;cursor:pointer" onclick="editAccount(\''+jsq(a.email)+'\')"></i>'
        + '<i data-lucide="x" width="15" height="15" stroke-width="2" style="color:#455266;cursor:pointer" onclick="deleteAccount(\''+a.email+'\')"></i>'
        + '</div>')).join("")
    + '</div>')).join("") || '<div style="font-size:12.5px;color:#5C6B82;padding:8px 2px">ไม่พบบัญชี</div>';

  let checkedCount = 0;
  if(typeof s.accountsChecked === 'number'){
    checkedCount = s.accountsChecked;
  } else if(s.groups){
    s.groups.forEach(g=>(g.accounts||[]).forEach(a=>{ if(a.checked) checkedCount++; }));
  }
  setPf('pfAccounts', checkedCount > 0, "บัญชีที่จะทำ", checkedCount + " รหัส");

  icons();
}
async function toggleAccount(e){ if(hasPy()){ await PY.toggle_account(e); renderAccounts(); } }
async function deleteAccount(e){ if(hasPy()){ await PY.delete_account(e); renderAccounts(); } }
async function delSelectedAccounts(){ if(hasPy()){ await PY.del_selected_accounts(); renderAccounts(); } }
async function selAccByStatus(k){ if(hasPy()){ await PY.select_accounts_by_status(k); renderAccounts(); } }
async function toggleGroup(g,checked){ if(hasPy()){ await PY.toggle_group(g,checked); renderAccounts(); } }
async function deleteGroup(g){ if(hasPy()){ await PY.delete_group(g); renderAccounts(); } }
async function moveSelectedGroup(){
  const v = (document.getElementById('moveGroupInput')||{}).value || "";
  if(!v.trim()){ notReady('พิมพ์ชื่อกลุ่มก่อน'); return; }
  if(hasPy()){ await PY.move_selected_to_group(v); document.getElementById('moveGroupInput').value=''; renderAccounts(); }
}
// ต้องใช้ค่าดิบ (rawname/password/token) ไม่ใช่ค่าที่ใช้โชว์ในลิสต์ (name = ชื่อที่คำนวณมาโชว์,
// tok = โทเคนที่ถูกหั่นเหลือ 14 ตัว) ไม่งั้นกดบันทึกแล้วเขียนทับของจริงด้วยค่าที่เพี้ยน
function editAccount(email){
  const a = ACCT_CACHE[email]; if(!a) return;
  document.getElementById('accEmail').value = a.email;
  document.getElementById('accName').value = a.rawname || '';
  document.getElementById('accGroup').value = a.grp;
  document.getElementById('accPass').value = a.password || '';
  document.getElementById('accToken').value = a.token || '';
  document.getElementById('accFormTitle').textContent = 'แก้ไขบัญชี';
}
function resetAccForm(){ ['accEmail','accName','accToken','accPass'].forEach(i=>document.getElementById(i).value=''); document.getElementById('accGroup').value='ทั่วไป'; document.getElementById('accFormTitle').textContent='เพิ่ม / แก้ไขบัญชี'; }
async function saveAccount(){ if(!hasPy()) return; const p={email:accEmail.value,name:accName.value,group:accGroup.value,password:accPass.value,token:accToken.value}; await PY.save_account(p); resetAccForm(); renderAccounts(); }

// ================= SCRIPT =================
const DEMO_STEPS = {name:"ล็อกอิน + เก็บของประจำวัน",count:8,steps:[
  {no:"01",type:"เปิดแอป",icon:"power",detail:"com.mumu.game/.Main",delay:"2.0s",x:"-",y:"-",desc:"เปิดเกม"},
  {no:"02",type:"แตะ",icon:"mouse-pointer-click",detail:"(540, 1180)",delay:"0.6s",x:"540",y:"1180",desc:"แตะกลางจอ"},
  {no:"03",type:"anchor + แตะ",icon:"image",detail:"ปุ่มล็อกอิน",delay:"0.8s",x:"540",y:"1420",desc:"แตะตรงที่เจอปุ่มล็อกอิน"},
  {no:"04",type:"พิมพ์",icon:"type",detail:"{{email}}",delay:"0.4s",x:"-",y:"-",desc:"กรอกอีเมล"},
]};
let SEL_STEP = null;
const FALLBACK_TYPE_OPTIONS = [
  {value:'tap',label:'แตะ (tap)'},{value:'swipe',label:'ปัด (swipe)'},{value:'text',label:'พิมพ์ (text)'},
  {value:'keyevent',label:'ปุ่มระบบ (keyevent)'},{value:'sleep',label:'รอเวลา (sleep)'},
  {value:'start_app',label:'เปิดแอป (start_app)'},{value:'stop_app',label:'ปิดแอป (stop_app)'},
  {value:'detect_image',label:'เจอรูปกด (detect_image)'},{value:'wait_for_image',label:'รอรูป (wait_for_image)'},
  {value:'tap_text',label:'กดตามข้อความ (tap_text)'},{value:'wait_for_text',label:'รอข้อความ (wait_for_text)'},
  {value:'clear_ads_loop',label:'เคลียร์โฆษณา (clear_ads_loop)'},{value:'fetch_otp',label:'กรอก OTP (fetch_otp)'},
  {value:'read_diamond',label:'อ่านเพชร (read_diamond)'},{value:'run_set',label:'ชุดคำสั่ง (run_set)'},
  {value:'keyboard',label:'คีย์บอร์ด (keyboard)'},{value:'screenshot',label:'ถ่ายภาพ (screenshot)'},
  {value:'find_yellow_stage',label:'ด่านเหลือง (find_yellow_stage)'},
  {value:'if_image',label:'ทางเลือก ถ้าเจอภาพ (if_image)'},
];
function ensureTypeOptions(opts){
  const sel=document.getElementById('sfType');
  if(!sel || sel.options.length) return;
  (opts||FALLBACK_TYPE_OPTIONS).forEach(o=>{
    const op=document.createElement('option'); op.value=o.value; op.textContent=o.label; sel.appendChild(op);
  });
}
async function renderSteps(){
  const s = hasPy() ? await PY.get_steps() : DEMO_STEPS;
  ensureTypeOptions(s.typeOptions);
  const nm = document.getElementById('scriptName');
  if(document.activeElement !== nm) nm.value = s.name==="—" ? "" : s.name;
  document.getElementById('stepCount').textContent = "ขั้นตอน ("+s.count+")";
  document.getElementById('stepList').innerHTML = s.steps.map((st,i)=>{
    const active = SEL_STEP===i;
    const inRange = RANGE && i>=RANGE[0] && i<=RANGE[1];
    const bg = inRange ? 'rgba(125,211,252,.14)' : (active?'rgba(16,185,129,.10)':'transparent');
    const bd = inRange ? 'rgba(125,211,252,.45)' : (active?'rgba(16,185,129,.35)':'transparent');
    return '<div onclick="onStepClick(event,'+i+')" style="display:flex;align-items:center;gap:11px;padding:9px 11px;border-radius:8px;cursor:pointer;background:'+bg+';border:1px solid '+bd+'">'
    + '<span style="font-family:\'IBM Plex Mono\',monospace;font-size:11.5px;color:#5C6B82;width:20px">'+st.no+'</span>'
    + '<i data-lucide="'+st.icon+'" width="15" height="15" stroke-width="1.9" style="color:'+(st.icon==='image'?'#FBBF24':'#7DD3FC')+';flex:none"></i>'
    + '<span style="font-size:12.5px;font-weight:500;min-width:80px">'+esc(st.type)+'</span>'
    + '<span style="font-family:\'IBM Plex Mono\',monospace;font-size:11.5px;color:#90A0B7;flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">'+esc(st.detail)+'</span>'
    + '<span style="font-family:\'IBM Plex Mono\',monospace;font-size:11px;color:#5C6B82">'+esc(st.delay)+'</span></div>';
  }).join("") || '<div style="font-size:12px;color:#5C6B82;padding:10px">— ยังไม่มีขั้นตอน เลือกสคริปต์ที่หน้าแรก —</div>';
  window._steps = s.steps;
  icons();
}
// ---- ฟอร์มแก้ขั้นตอน: ฟิลด์ที่โชว์ต่อชนิด + ป้ายชื่อช่องข้อความ ----
const STEP_FIELD_MAP = {
  tap:['XY','Delay'], swipe:['XY','XY2','Duration','Delay'], text:['Text','Delay'],
  keyevent:['Code','Delay'], sleep:['Seconds'], start_app:['Text','Delay'],
  stop_app:['Text','Delay'], detect_image:['Text','Threshold','Click','Delay'],
  wait_for_image:['Text','Timeout','Threshold','Click','Delay'], tap_text:['Text','Delay'],
  wait_for_text:['Text','Timeout','Delay'], clear_ads_loop:['Text','Delay'],
  fetch_otp:['Text','Delay'], read_diamond:['Delay'], run_set:['Set','Block'],
  keyboard:['Key','Action','Delay'], screenshot:['Text','Delay'], find_yellow_stage:['Delay'],
  if_image:['Text','Threshold','Timeout','Delay'],
  tap_until_image:['XY','Text','Interval','Timeout','Threshold','Delay'],
  tap_around_until_image:['XY','Text','Radius','Interval','Timeout','Threshold','Delay'],
  answer_quiz:['Points','Submit','Box','Mode','Text','Interval','Timeout','Threshold','Delay'],
};
const STEP_TEXT_LABEL = {
  text:'ข้อความที่พิมพ์ (ใช้ {EMAIL} {PASSWORD} {NAME} ได้)',
  start_app:'ชื่อแพ็กเกจแอป (เช่น com.game.app)',
  stop_app:'ชื่อแพ็กเกจแอปที่จะปิด',
  detect_image:'ชื่อไฟล์รูปต้นแบบ (.png ในโฟลเดอร์ templates)',
  wait_for_image:'ชื่อไฟล์รูปต้นแบบ (.png ในโฟลเดอร์ templates)',
  tap_text:'ข้อความ หรือ  id:resource-id  ที่จะแตะ',
  wait_for_text:'ข้อความ หรือ  id:resource-id  ที่รอ',
  clear_ads_loop:'lobby.png | ปุ่มปิด1.png,ปุ่มปิด2.png (เว้นว่าง=อัตโนมัติ)',
  fetch_otp:'แพทเทิร์น OTP (regex เช่น \\d{6})',
  screenshot:'ที่เก็บไฟล์ภาพ ({NAME} {DATE} {TIME} ได้)',
  if_image:'ไฟล์รูปเงื่อนไข (.png ใน templates) — หรือกด "ตั้งภาพเงื่อนไขจากจอ" ในโหมดโฟลว์',
  tap_until_image:'ไฟล์รูปเป้าหมาย (.png ใน templates) — หรือกด "ตั้งภาพจากจอ (ลากกรอบ)" ในโหมดโฟลว์',
  tap_around_until_image:'ไฟล์รูปเป้าหมายที่รอให้ขึ้น (.png) — หรือกด "ตั้งภาพเป้าหมายจากจอ" ในโหมดโฟลว์',
  answer_quiz:'ไฟล์รูปที่บอกว่า "ตอบครบแล้ว" เช่นป๊อปอัพรับรางวัล — หรือกด "ตั้งภาพเป้าหมายจากจอ"',
};
const ALL_FLD = ['XY','XY2','Duration','Text','Set','Block','Code','Key','Action','Seconds','Timeout','Interval','Radius','Points','Submit','Box','Mode','Threshold','Click','Delay'];
function toggleBlockFields(){ const on=(document.getElementById('sfBlockOn')||{}).checked; const box=document.getElementById('sfBlockOpts'); if(box) box.style.display=on?'flex':'none'; }
function applyTypeFields(t){
  const show = STEP_FIELD_MAP[t] || ['Delay'];
  ALL_FLD.forEach(f=>{
    const el = document.getElementById('fld'+f);
    if(!el) return;
    const on = show.includes(f);
    el.style.display = on ? (f==='XY'||f==='XY2' ? 'flex' : 'flex') : 'none';
  });
  if(show.includes('Text')){ const lbl=document.getElementById('sfTextLabel'); if(lbl) lbl.textContent = STEP_TEXT_LABEL[t] || 'ข้อความ'; }
}
function fillStepForm(st){
  const g=id=>document.getElementById(id);
  g('sfType').value = st.type;
  g('sfX').value = st.x===''||st.x==='-'?'':st.x;
  g('sfY').value = st.y===''||st.y==='-'?'':st.y;
  g('sfX2').value = st.x2||''; g('sfY2').value = st.y2||'';
  g('sfDuration').value = st.duration||''; g('sfText').value = st.text||'';
  g('sfSet').value = st.set||'';
  g('sfBlockOn').checked = (st.block_on_fail === 'home_retry');
  g('sfBlockHome').value = st.block_home||''; g('sfBlockRetries').value = (st.block_retries!=null?st.block_retries:'');
  toggleBlockFields();
  g('sfCode').value = st.code||'';
  g('sfKey').value = st.key||''; if(st.action) g('sfAction').value = st.action;
  g('sfSeconds').value = st.seconds||''; g('sfTimeout').value = st.timeout||'';
  g('sfThreshold').value = st.threshold||'';
  g('sfInterval').value = (st.interval!=null&&st.interval!=='')?st.interval:'';
  g('sfRadius').value = (st.radius!=null&&st.radius!=='')?st.radius:'';
  g('sfPoints').value = st.points||'';
  g('sfSubmit').value = st.submit||'';
  g('sfBox').value = st.box||'';
  if(st.mode) g('sfMode').value = st.mode;
  // ไม่ได้ตั้งค่ามา = เปิด (ตัวรันดีฟอลต์ click=True) ต้องโชว์ให้ตรงกับที่จะเกิดขึ้นจริง
  g('sfClick').checked = (st.click === undefined || st.click === null || st.click === '' ) ? true : !!st.click;
  g('sfDesc').value = st.desc===''||st.desc==='-'?'':st.desc;
  g('sfDelay').value = st.delay===''||st.delay==null?'':String(st.delay).replace('s','');
  applyTypeFields(st.type);
}
function onTypeChange(){ applyTypeFields(document.getElementById('sfType').value); }
function collectStepPatch(){
  const g=id=>(document.getElementById(id)||{}).value;
  const t=g('sfType');
  const p={type:t, desc:g('sfDesc')};
  const show=STEP_FIELD_MAP[t]||[];
  if(show.includes('XY')){ p.x=g('sfX'); p.y=g('sfY'); }
  if(show.includes('XY2')){ p.x2=g('sfX2'); p.y2=g('sfY2'); }
  if(show.includes('Duration')) p.duration=g('sfDuration');
  if(show.includes('Text')) p.text=g('sfText');
  if(show.includes('Set')) p.set=g('sfSet');
  if(show.includes('Block')){
    // ติ๊ก = บล็อกกันพัง (block_on_fail='home_retry'); ไม่ติ๊ก = ส่งค่าว่างให้ backend ลบทิ้ง (กลับเป็น run_set ธรรมดา)
    if((document.getElementById('sfBlockOn')||{}).checked){
      p.block_on_fail='home_retry'; p.block_home=g('sfBlockHome'); p.block_retries=g('sfBlockRetries');
    } else { p.block_on_fail=''; p.block_home=''; p.block_retries=''; }
  }
  if(show.includes('Code')) p.code=g('sfCode');
  if(show.includes('Key')) p.key=(g('sfKey')||'').toLowerCase();
  if(show.includes('Action')) p.action=g('sfAction');
  if(show.includes('Seconds')) p.seconds=g('sfSeconds');
  if(show.includes('Timeout')) p.timeout=g('sfTimeout');
  if(show.includes('Threshold')) p.threshold=g('sfThreshold');
  if(show.includes('Interval')) p.interval=g('sfInterval');
  if(show.includes('Radius')) p.radius=g('sfRadius');
  if(show.includes('Points')) p.points=g('sfPoints');
  if(show.includes('Submit')) p.submit=g('sfSubmit');
  if(show.includes('Box')) p.box=g('sfBox');
  if(show.includes('Mode')) p.mode=g('sfMode');
  if(show.includes('Click')) p.click=!!(document.getElementById('sfClick')||{}).checked;
  if(show.includes('Delay')) p.delay=g('sfDelay');
  return p;
}
let RANGE=null;  // [start,end] (0-based, รวมปลาย) ของช่วงที่คลิกคลุมไว้ — ใช้ทำเป็นบล็อก
function onStepClick(ev, i){
  // Shift+คลิก = เลือกช่วงจากขั้นที่เลือกไว้ก่อนหน้าถึงขั้นนี้ (คลิกคลุม) ; คลิกธรรมดา = เลือกแก้ขั้นเดียว
  if(ev && ev.shiftKey && SEL_STEP!=null){
    RANGE=[Math.min(SEL_STEP,i), Math.max(SEL_STEP,i)];
    const n=RANGE[1]-RANGE[0]+1;
    const bar=document.getElementById('rangeBar'), txt=document.getElementById('rangeBarText');
    if(txt) txt.textContent='เลือก '+n+' ขั้น (ขั้น '+(RANGE[0]+1)+'–'+(RANGE[1]+1)+')';
    if(bar) bar.style.display='flex';
    renderSteps();
    return;
  }
  if(RANGE){ RANGE=null; const bar=document.getElementById('rangeBar'); if(bar) bar.style.display='none'; }
  selectStep(i);
}
function clearRange(){ RANGE=null; const bar=document.getElementById('rangeBar'); if(bar) bar.style.display='none'; renderSteps(); }
function openBlockFromRange(){
  if(!RANGE){ notReady('เลือกช่วงก่อน (Shift+คลิก)'); return; }
  const n=RANGE[1]-RANGE[0]+1, from=RANGE[0]+1, to=RANGE[1]+1;
  openModal('ทำ '+n+' ขั้นนี้เป็นบล็อก','scissors',
    '<div style="font-size:12px;color:#7C8CA3;margin-bottom:12px">ขั้น '+from+'–'+to+' จะถูกย้ายไปเก็บเป็นชุดใหม่ แล้วแทนที่ด้วยบล็อก 1 ก้อน</div>'
    +'<div style="display:flex;flex-direction:column;gap:10px">'
    +'<div style="display:flex;flex-direction:column;gap:5px"><span style="font-size:11.5px;color:#90A0B7">ชื่อบล็อก</span><input id="brName" class="in" placeholder="เช่น เก็บของ" style="height:38px;border-radius:8px;background:#0A0F19;border:1px solid #24344B;padding:0 12px;font-size:12.5px;color:#C7D2E0"></div>'
    +'<label style="display:flex;gap:8px;align-items:center;font-size:12.5px;color:#C7D2E0;cursor:pointer"><input type="checkbox" id="brBlock" checked onchange="document.getElementById(\'brOpts\').style.display=this.checked?\'flex\':\'none\'">ถ้าพัง: กลับหน้าแรกแล้วลองใหม่ทั้งบล็อก</label>'
    +'<div id="brOpts" style="display:flex;gap:8px"><input id="brHome" class="in" value="กลับหน้าแรก" placeholder="ชุดกลับหน้าแรก" style="flex:1;height:36px;border-radius:8px;background:#0E1420;border:1px solid #24344B;padding:0 11px;font-size:12.5px;color:#C7D2E0"><input id="brRetries" class="in" placeholder="รอบ (3)" style="width:80px;height:36px;border-radius:8px;background:#0E1420;border:1px solid #24344B;padding:0 11px;font-family:\'IBM Plex Mono\',monospace;font-size:12.5px;color:#C7D2E0"></div>'
    +'<button class="in" onclick="confirmBlockFromRange()" style="display:flex;align-items:center;justify-content:center;gap:7px;height:40px;border-radius:9px;background:#10B981;color:#04120C;font-size:13px;font-weight:600;cursor:pointer;margin-top:4px"><i data-lucide="scissors" width="15" height="15" stroke-width="2"></i>ตัดเป็นบล็อก</button>'
    +'</div>');
  icons();
}
async function confirmBlockFromRange(){
  if(!RANGE) return;
  const g=id=>(document.getElementById(id)||{}).value;
  const name=(g('brName')||'').trim();
  if(!name){ notReady('ตั้งชื่อบล็อกก่อน'); return; }
  const block=(document.getElementById('brBlock')||{}).checked;
  if(hasPy()){
    await PY.extract_range_to_block(RANGE[0]+1, RANGE[1]+1, name, block?g('brHome'):'', block?g('brRetries'):'', block);
  }
  RANGE=null; closeModal(); renderSteps();
}
function selectStep(i){ SEL_STEP=i; const st=(window._steps||[])[i]; if(st){ fillStepForm(st.raw||st); } renderSteps(); }
async function saveProfile(){ if(hasPy()){ await PY.save_profile(document.getElementById('scriptName').value); await refreshScriptView(); refresh(); } }
async function deleteProfile(){ if(hasPy()){ await PY.delete_profile(); SEL_STEP=null; await refreshScriptView(); refresh(); } }
async function updateStep(){
  // โหมดโฟลว์ → บันทึกผ่าน path API (แก้บล็อกในกิ่งได้)
  if(typeof SCRIPT_VIEW!=='undefined' && SCRIPT_VIEW==='flow'){ await flowSaveSel(); return; }
  if(!hasPy()||SEL_STEP===null){ notReady('เลือกขั้นก่อน'); return; }
  await PY.update_step(SEL_STEP, collectStepPatch()); await refreshScriptView();
}
async function addStep(){ if(hasPy()){ const at=SEL_STEP===null?9999:SEL_STEP; const t=(document.getElementById('sfType')||{}).value||'tap'; await PY.add_step(at, t); SEL_STEP=(SEL_STEP===null?0:SEL_STEP+1); await refreshScriptView(); selectStep(SEL_STEP); } }
async function deleteStep(){ if(!hasPy()||SEL_STEP===null){ notReady('เลือกขั้นก่อน'); return; } await PY.delete_step(SEL_STEP); SEL_STEP=null; await refreshScriptView(); }
async function moveStep(dir){ if(!hasPy()||SEL_STEP===null){ notReady('เลือกขั้นก่อน'); return; } await PY.move_step(SEL_STEP,dir); const nj=SEL_STEP+dir; if(nj>=0) SEL_STEP=nj; await refreshScriptView(); }
async function duplicateStep(){
  // โหมดโฟลว์ → คัดลอกบล็อกตาม path (ในกิ่งก็คัดลอกได้ วางต่อท้ายในเลนเดียวกัน)
  if(typeof SCRIPT_VIEW!=='undefined' && SCRIPT_VIEW==='flow'){
    if(!hasPy()||!SEL_PATH){ notReady('คลิกเลือกบล็อกบนผังก่อน'); return; }
    FLOW = await PY.flow_duplicate(SEL_PATH);
    // เลือกบล็อกที่คัดลอกมาใหม่ (วางต่อท้ายตัวเดิมในเลนเดียวกันทันที)
    const np = SEL_PATH.slice(); np[np.length-1] = np[np.length-1] + 1;
    await flowSelect(np);
    return;
  }
  if(!hasPy()||SEL_STEP===null){ notReady('เลือกขั้นก่อน'); return; }
  await PY.duplicate_step(SEL_STEP);
  SEL_STEP = SEL_STEP + 1;  // เลือกตัวที่คัดลอกมาใหม่ (วางต่อท้ายตัวเดิมทันที)
  renderSteps();
  selectStep(SEL_STEP);
}
async function testStep(){
  // โหมดโฟลว์ → ทดสอบตาม path (บล็อกในกิ่งก็ทดสอบได้ / if_image = เช็คว่าเจอภาพไหม)
  if(typeof SCRIPT_VIEW!=='undefined' && SCRIPT_VIEW==='flow'){
    if(!hasPy()||!SEL_PATH){ notReady('คลิกเลือกบล็อกบนผังก่อน'); return; }
    await PY.flow_test_step(SEL_PATH); return;
  }
  if(!hasPy()||SEL_STEP===null){ notReady('เลือกขั้นก่อน'); return; }
  await PY.test_step(SEL_STEP);
}
async function importWebGame(){ if(hasPy()){ await PY.import_save_web_game(); renderAccounts(); } }

// ================= TOOLS =================
let SUB = "manual";
function initToolTabs(){ switchSub(SUB); }
function switchSub(sub){
  SUB = sub;
  document.querySelectorAll('#toolTabs .ttab').forEach(t=>{
    const on = t.dataset.sub===sub;
    t.style.background = on ? "#10B981" : "transparent";
    t.style.color = on ? "#04120C" : "#90A0B7";
    t.onclick = ()=>switchSub(t.dataset.sub);
  });
  document.querySelectorAll('.sub').forEach(s=>{ s.style.display = (s.dataset.sub===sub) ? (sub==='manual'?'grid':'flex') : 'none'; });
  icons();
}
async function mClick(){ if(hasPy()) await PY.manual_click(mX.value, mY.value); }
async function mType(){ if(hasPy()) await PY.manual_type(mText.value); }
async function mKey(c){ if(hasPy()) await PY.manual_key(c); }
async function mShot(){ if(hasPy()) await PY.manual_screenshot(); }
async function adbShell(){ if(hasPy()) await PY.adb_shell(adbCmd.value); }
async function startStory(){
  if(!hasPy()){ notReady('Story Auto (ต้องเปิดผ่าน .exe)'); return; }
  const r = await PY.start_story(document.getElementById('storyInterval').value);
  if(r && r.ok){ switchPage('home'); setRunBtn(true); startRunPoll(); }
}

// ================= SETTINGS =================
async function loadSettings(){
  if(!hasPy()){ document.getElementById('setAdb').value="C:\\MuMuPlayer\\shell\\adb.exe"; document.getElementById('setPorts').textContent="7555 – 7564"; return; }
  const s = await PY.get_settings();
  document.getElementById('setAdb').value = s.adb || "";
  document.getElementById('setPorts').textContent = s.ports || "—";
  if(s.gemini) document.getElementById('setGemini').placeholder = s.gemini;
}
async function saveAdb(){ if(hasPy()) await PY.save_adb(document.getElementById('setAdb').value); }
async function saveGemini(){ if(hasPy()){ await PY.save_gemini(document.getElementById('setGemini').value); document.getElementById('setGemini').value=''; } }
async function checkCap(){ if(hasPy()){ const r=await PY.check_capacity(); document.getElementById('setCap').textContent=r.cap; } }

// ---------- script set editing mode ----------
window.CURRENT_SET_EDITING = null;
function updateSetEditBanner(){
  const banner = document.getElementById('setEditBanner');
  const nameEl = document.getElementById('setEditBannerName');
  if(!banner || !nameEl) return;
  if(window.CURRENT_SET_EDITING){
    nameEl.textContent = window.CURRENT_SET_EDITING;
    banner.style.display = 'flex';
  } else {
    banner.style.display = 'none';
  }
}
async function exitSetEditMode(){
  window.CURRENT_SET_EDITING = null;
  updateSetEditBanner();
  // ให้ backend โหลดสคริปต์ที่ค้างไว้กลับมาเอง แล้วรีเฟรชมุมมองที่เปิดอยู่
  // เดิมแค่ซ่อนแบนเนอร์ ตัวแก้ไขยังถือขั้นของ 'ชุด' อยู่ ผู้ใช้ต้องไปเลือกสคริปต์เดิมใหม่เอง
  if(hasPy()){
    await PY.exit_set_edit();
    if(typeof refresh === 'function') await refresh();
  }
  if(typeof refreshScriptView === 'function') await refreshScriptView();
  else renderSteps();
}
async function saveCurrentEditingSet(){
  if(!window.CURRENT_SET_EDITING) return;
  const name = window.CURRENT_SET_EDITING;
  if(!hasPy()) return;
  const r = await PY.save_script_set_steps(name);
  if(!(r && r.ok)) return;
  if(typeof onLog === 'function') onLog({ts: new Date().toLocaleTimeString('th-TH'), text: "บันทึกทับชุดคำสั่งย่อย '" + name + "' สำเร็จ", kind: "ok"});
  // บันทึกเสร็จ = จบงานกับชุดนี้ -> พากลับสคริปต์เดิมให้เลย ไม่ต้องไปเลือกใหม่เอง
  await exitSetEditMode();
}

// ---------- boot ----------
// สแกนหา Emulator ทันทีที่เปิดแอป (แอปเดิม Tkinter ทำแบบนี้ตั้งแต่ __init__ — เว็บเคยลืมทำจุดนี้
// ต้องกดปุ่มสแกนเองก่อนถึงจะเห็นจอ) ใน DEMO mode (ไม่มี Python) scanPorts() แค่ log เฉยๆ ไม่พัง
async function saveStuckMode(v){ if(hasPy()) await PY.save_stuck_mode(v); }
async function loadStuckMode(){
  if(!hasPy()) return;
  const r = await PY.get_stuck_mode();
  const el = document.getElementById('stuckMode');
  if(el && r && r.on_stuck) el.value = r.on_stuck;
}
function boot(){ renderNav(); switchPage("home"); loadStuckMode(); if(hasPy()){ scanPorts(); } else { refresh(); } icons(); }
window.addEventListener('pywebviewready', ()=>{ PY = window.pywebview.api; boot(); });
// เผื่อเปิดในเบราว์เซอร์ธรรมดา (พรีวิว) — ไม่มี pywebviewready
setTimeout(()=>{ if(!hasPy()) boot(); }, 400);
