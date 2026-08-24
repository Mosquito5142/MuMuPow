// ==================================================================
//  Flow Editor — ผังบล็อกแบบตัวต่อ (โหลดต่อจาก app.js + tools.js)
//  ใช้ global ร่วม: PY, hasPy, esc, icons, notReady, openModal, closeModal,
//  fillStepForm, collectStepPatch, STEP_FIELD_MAP, FALLBACK_TYPE_OPTIONS
// ==================================================================
let SCRIPT_VIEW = 'list';     // 'list' | 'flow'
let FLOW = null;              // tree ล่าสุดจาก get_flow()
let SEL_PATH = null;          // path ของบล็อกที่เลือก เช่น [1,'then',0]
let FLOW_HL = null;           // path ไฮไลต์สดตอนรัน (string เช่น "1.then.0")
let CUT_PATH = null;          // บล็อกที่กด 'ย้ายไปที่อื่น' ค้างไว้ — ระหว่างนี้จุด + จะกลายเป็นปุ่ม 'วาง'
let FLOW_RANGE = null;        // [pathA, pathB] ช่วงที่ Shift+คลิกคลุมไว้ (ต้องอยู่ระดับเดียวกัน)
let CUT_RANGE = null;         // ช่วงที่กำลังย้าย (ใช้แทน CUT_PATH เมื่อย้ายหลายบล็อกพร้อมกัน)

// ---------- ตัวช่วยเรื่อง path ----------
const samePath = (a,b) => !!a && !!b && JSON.stringify(a) === JSON.stringify(b);
const sameParent = (a,b) => !!a && !!b && a.length===b.length
  && JSON.stringify(a.slice(0,-1)) === JSON.stringify(b.slice(0,-1));
// บล็อกนี้อยู่ในช่วงที่คลุมไว้ไหม (ใช้ทั้งตอนไฮไลต์และตอนย้าย)
function inRange(path, range){
  if(!range || !sameParent(range[0], path)) return false;
  const lo = Math.min(range[0][range[0].length-1], range[1][range[1].length-1]);
  const hi = Math.max(range[0][range[0].length-1], range[1][range[1].length-1]);
  const i = path[path.length-1];
  return i >= lo && i <= hi;
}
function rangeCount(range){
  if(!range) return 0;
  return Math.abs(range[1][range[1].length-1] - range[0][range[0].length-1]) + 1;
}

// คลิกบล็อกบนผัง — Shift+คลิก = คลุมช่วง (เหมือนหน้าลิสต์), คลิกธรรมดา = เลือกทีละอัน
function flowClick(ev, path){
  if(ev && ev.shiftKey && SEL_PATH){
    if(!sameParent(SEL_PATH, path)){
      notReady('เลือกคลุมได้เฉพาะบล็อกที่อยู่ระดับเดียวกัน (เส้นเดียวกัน/กิ่งเดียวกัน)');
      return;
    }
    FLOW_RANGE = [SEL_PATH.slice(), path.slice()];
    renderFlow();
    return;
  }
  FLOW_RANGE = null;
  flowSelect(path);
}
function flowClearRange(){ FLOW_RANGE = null; renderFlow(); }

async function flowClearPreview(){
  if(!hasPy() || !SEL_PATH) return;
  FLOW = await PY.flow_clear_preview(SEL_PATH);
  await flowSelect(SEL_PATH);
}
let RETRY_ARROWS = [];        // เส้นวนกลับที่ต้องวาด: [{from, to}] (path string ทั้งคู่) — เก็บระหว่างเรนเดอร์บล็อก

const DEMO_FLOW = { name: 'ล็อกอิน + เก็บของ', typeOptions: null, steps: [
  { type: 'start_app', text: 'com.game.app', desc: 'เปิดเกม', delay: 5 },
  { type: 'if_image', desc: 'มีป๊อปอัพโฆษณา?', text: 'ads.png', timeout: 2,
    then: [ { type: 'tap', x: '880', y: '40', desc: 'กดปิดโฆษณา', delay: 0.5 },
            { type: 'keyevent', code: '4', desc: 'กันเด้งซ้ำ' } ],
    else: [] },
  { type: 'tap', x: '480', y: '270', desc: 'กดรับของ', delay: 1 },
  { type: 'read_diamond', desc: 'อ่านเพชร', delay: 1 },
]};

// ---------- สลับมุมมอง ----------
function setScriptView(v){
  SCRIPT_VIEW = v;
  const chipL = document.getElementById('viewChipList'), chipF = document.getElementById('viewChipFlow');
  const on = 'background:#10B981;color:#04120C;font-weight:600', off = 'background:transparent;color:#90A0B7';
  if(chipL) chipL.style.cssText = chipL.dataset.base + (v==='list'?on:off);
  if(chipF) chipF.style.cssText = chipF.dataset.base + (v==='flow'?on:off);
  document.getElementById('stepList').style.display = v==='list' ? 'flex' : 'none';
  document.getElementById('listBtnRow').style.display = v==='list' ? 'flex' : 'none';
  document.getElementById('flowCanvas').style.display = v==='flow' ? 'block' : 'none';
  // การเลือกช่วง (คลิกคลุม) ใช้ได้เฉพาะโหมดลิสต์ — ซ่อนตัวช่วย+ยกเลิกช่วงที่ค้างเมื่อสลับไปโฟลว์
  const rh=document.getElementById('rangeHint'), rb=document.getElementById('rangeBar');
  if(rh) rh.style.display = v==='list' ? 'block' : 'none';
  if(v!=='list' && rb){ rb.style.display='none'; if(typeof RANGE!=='undefined') RANGE=null; }
  if(v==='flow') renderFlow();
}

// ---------- ดึงข้อมูล + เรนเดอร์ ----------
async function renderFlow(){
  FLOW = hasPy() ? await PY.get_flow() : DEMO_FLOW;
  const cv = document.getElementById('flowCanvas');
  if(!cv) return;
  const steps = FLOW.steps || [];
  RETRY_ARROWS = [];   // flowChain/flowBlock เก็บคู่ {from,to} เข้ามาระหว่างสร้าง HTML ด้านล่าง
  const chainHtml = flowChain(steps, []);
  cv.innerHTML = cutBanner()
    + '<div id="flowInner" style="position:relative;display:flex;flex-direction:column;align-items:center;padding:14px 6px">'
    + '<svg id="flowArrowsSvg" style="position:absolute;top:0;left:0;pointer-events:none;overflow:visible"></svg>'
    + '<div style="display:flex;align-items:center;gap:7px;padding:7px 16px;border-radius:999px;background:rgba(16,185,129,.12);border:1px solid rgba(16,185,129,.3);color:#6EE7B7;font-size:12px;font-weight:600"><i data-lucide="play" width="12" height="12" stroke-width="2.5"></i>เริ่ม</div>'
    + chainHtml
    + '<div style="display:flex;align-items:center;gap:7px;padding:7px 16px;border-radius:999px;background:#121A28;border:1px solid #24344B;color:#7C8CA3;font-size:12px;font-weight:600;margin-top:2px"><i data-lucide="flag" width="12" height="12" stroke-width="2"></i>จบ</div>'
    + '</div>';
  icons();
  drawRetryArrows();  // ต่อจาก icons() เสมอ — ไอคอนแทนที่ <i> ด้วย <svg> ทำให้ขนาดบล็อกเปลี่ยนนิดหน่อย ต้องวัดตำแหน่งหลังสุด
}

// ---------- วาดเส้นวนกลับ (แบบ flowchart goto-arrow) ให้บล็อกที่ตั้ง anchor_on_fail='retry' ----------
function drawRetryArrows(){
  const inner = document.getElementById('flowInner');
  const svg = document.getElementById('flowArrowsSvg');
  if(!inner || !svg) return;
  if(!RETRY_ARROWS.length){ svg.setAttribute('width', 0); svg.setAttribute('height', 0); svg.innerHTML = ''; return; }

  const w = inner.scrollWidth, h = inner.scrollHeight;
  svg.setAttribute('width', w);
  svg.setAttribute('height', h);
  svg.setAttribute('viewBox', '0 0 ' + w + ' ' + h);
  const ir = inner.getBoundingClientRect();

  let body = '<defs><marker id="retryArrowHead" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
    + '<path d="M0,0 L10,5 L0,10 z" fill="#FBBF24"/></marker></defs>';

  RETRY_ARROWS.forEach(({from, to}, i) => {
    const a = inner.querySelector('[data-fpath="' + from + '"]');
    const b = inner.querySelector('[data-fpath="' + to + '"]');
    if(!a || !b) return;
    const ar = a.getBoundingClientRect(), br = b.getBoundingClientRect();
    const x1 = ar.right - ir.left, y1 = ar.top - ir.top + ar.height / 2;
    const x2 = br.right - ir.left, y2 = br.top - ir.top + br.height / 2;

    if(from === to){
      // วนกลับหาตัวเอง — วาดเป็นห่วงเล็กๆ ยื่นออกทางขวาของบล็อกเดียวกัน
      const r = 20;
      const path = 'M ' + x1 + ' ' + (y1 - 9) + ' C ' + (x1 + r * 2) + ' ' + (y1 - 9) + ', '
        + (x1 + r * 2) + ' ' + (y1 + 9) + ', ' + (x1 + 4) + ' ' + (y1 + 9);
      body += '<path d="' + path + '" fill="none" stroke="#FBBF24" stroke-width="2" stroke-dasharray="5,4" marker-end="url(#retryArrowHead)" opacity="0.85"/>';
      body += svgLabel(x1 + r * 2 + 6, y1, 'ลองซ้ำ');
      return;
    }

    const bulge = Math.max(x1, x2) + 36 + i * 22;  // เยื้องออกทีละอันกันเส้นทับกันตอนมีหลายจุด
    const path = 'M ' + x1 + ' ' + y1 + ' C ' + bulge + ' ' + y1 + ', ' + bulge + ' ' + y2 + ', ' + (x2 + 4) + ' ' + y2;
    body += '<path d="' + path + '" fill="none" stroke="#FBBF24" stroke-width="2" stroke-dasharray="5,4" marker-end="url(#retryArrowHead)" opacity="0.85"/>';
    body += svgLabel(bulge + 6, (y1 + y2) / 2, 'ไม่เจอ → วนกลับ');
  });

  svg.innerHTML = body;
}
function svgLabel(x, y, text){
  const w = 18 + text.length * 6.2;
  return '<g><rect x="' + x + '" y="' + (y - 9) + '" width="' + w + '" height="18" rx="9" fill="#1A1206" stroke="#7A5A1E" stroke-width="1"/>'
    + '<text x="' + (x + w / 2) + '" y="' + (y + 3.5) + '" fill="#FBBF24" font-size="9" font-family="\'IBM Plex Mono\',monospace" text-anchor="middle">🔁 ' + esc(text) + '</text></g>';
}

function pj(path){ return esc(JSON.stringify(path)).replace(/"/g,'&quot;'); }

// แถบบอกว่ากำลังย้ายบล็อกไหนอยู่ + ทางออก (กันผู้ใช้ค้างอยู่ในโหมดย้ายโดยไม่รู้ตัว)
function nodeAt(path){
  try{
    let cur = (FLOW && FLOW.steps) || [], node = null;
    path.forEach(tok => {
      if(typeof tok === 'string'){ cur = (node && node[tok]) || []; }
      else { node = cur[tok]; }
    });
    return node;
  }catch(e){ return null; }
}
function blockName(path){
  const n = nodeAt(path);
  return n ? (n.desc || typeTH(n.type||'tap')) : 'บล็อกที่เลือก';
}
function cutBanner(){
  // แถบ 1: คลุมช่วงไว้แล้วแต่ยังไม่กดย้าย — บอกจำนวนที่เลือกและทางไปต่อ
  if(!CUT_PATH && !CUT_RANGE && FLOW_RANGE){
    const n = rangeCount(FLOW_RANGE);
    return '<div style="display:flex;align-items:center;gap:10px;padding:9px 13px;margin-bottom:8px;border-radius:9px;background:#0F2F4A;border:1px solid #164E72">'
      + '<i data-lucide="check-square" width="15" height="15" stroke-width="1.9" style="color:#7DD3FC;flex:none"></i>'
      + '<span style="flex:1;font-size:12.5px;color:#7DD3FC">เลือกไว้ <b style="color:#FFF">' + n + ' บล็อก</b> — กด <b>✂ ย้ายไปที่อื่น</b> เพื่อยกทั้งชุด</span>'
      + '<button class="in" onclick="flowClearRange()" style="padding:5px 11px;border-radius:7px;background:#121A28;border:1px solid #24344B;color:#C7D2E0;font-size:11.5px;cursor:pointer">ยกเลิกที่เลือก</button></div>';
  }
  if(!CUT_PATH && !CUT_RANGE){
    // ยังไม่ได้ทำอะไร — บอกวิธีเลือกหลายบล็อกไว้ตรงนี้ ผู้ใช้จะได้ไม่ต้องเดา
    return '<div style="font-size:11px;color:#5C6B82;margin-bottom:6px">'
      + '💡 คลิกบล็อกแรก แล้ว <b style="color:#7DD3FC">Shift+คลิก</b> บล็อกสุดท้าย = เลือกหลายอัน '
      + 'แล้วกด <b style="color:#7DD3FC">✂ ย้ายไปที่อื่น</b> เพื่อยกเข้า/ออกเงื่อนไขทั้งชุด</div>';
  }

  const what = CUT_RANGE
    ? ('<b style="color:#FFF">' + rangeCount(CUT_RANGE) + ' บล็อก</b>')
    : ('<b style="color:#FFF">' + esc(blockName(CUT_PATH)) + '</b>');
  return '<div style="display:flex;align-items:center;gap:10px;padding:9px 13px;margin-bottom:8px;border-radius:9px;background:#0F2F4A;border:1px solid #164E72">'
    + '<i data-lucide="scissors" width="15" height="15" stroke-width="1.9" style="color:#7DD3FC;flex:none"></i>'
    + '<span style="flex:1;font-size:12.5px;color:#7DD3FC">กำลังย้าย ' + what + ' — กดปุ่ม <b style="color:#6EE7B7">วาง</b> สีเขียวตรงจุดที่ต้องการ (วางในกิ่งของเงื่อนไขก็ได้)</span>'
    + '<button class="in" onclick="flowCancelCut()" style="padding:5px 11px;border-radius:7px;background:#2A1113;border:1px solid #7F1D1D;color:#FCA5A5;font-size:11.5px;cursor:pointer">ยกเลิก</button></div>';
}
function connector(insertPath){
  // ปกติจุดนี้คือ "แทรกบล็อกใหม่" แต่ระหว่างย้าย (CUT_PATH) มันจะกลายเป็น "วางตรงนี้"
  // ใช้จุดเดิมเป็นเป้าวางเลย ผู้ใช้จึงไม่ต้องเรียนรู้อะไรใหม่ และวางเข้ากิ่ง then/else ได้ทุกจุด
  const cutting = CUT_PATH !== null || CUT_RANGE !== null;
  const handler = cutting ? ('flowDropAt(' + pj(insertPath) + ')') : ('flowInsertAt(' + pj(insertPath) + ')');
  const style = cutting
    ? 'width:26px;height:20px;border-radius:10px;background:#10B981;border:1px solid #34D399;color:#04120C;font-weight:700;font-size:10px'
    : 'width:20px;height:20px;border-radius:50%;background:#0F2F4A;border:1px solid #164E72;color:#7DD3FC;font-size:13px';
  return '<div style="display:flex;flex-direction:column;align-items:center">'
    + '<div style="width:2px;height:10px;background:#24344B"></div>'
    + '<div onclick="' + handler + '" title="' + (cutting ? 'วางบล็อกที่ย้ายมาตรงนี้' : 'แทรกบล็อกตรงนี้') + '" '
    + 'style="' + style + ';display:flex;align-items:center;justify-content:center;cursor:pointer;line-height:1">'
    + (cutting ? 'วาง' : '+') + '</div>'
    + '<div style="width:2px;height:10px;background:#24344B"></div></div>';
}

function typeTH(t){
  const o = (FLOW && FLOW.typeOptions) || FALLBACK_TYPE_OPTIONS;
  const hit = o.find(x=>x.value===t);
  return hit ? hit.label.replace(/ \(.+\)$/,'') : t;
}
function stepIcon(t){
  return ({tap:'mouse-pointer-click',swipe:'move',text:'type',keyevent:'smartphone',sleep:'clock',
    start_app:'power',stop_app:'power-off',detect_image:'image',wait_for_image:'image',
    tap_text:'text-cursor-input',wait_for_text:'search',clear_ads_loop:'x-circle',fetch_otp:'mail',
    screenshot:'camera',read_diamond:'gem',run_set:'layers',keyboard:'keyboard',
    find_yellow_stage:'star',if_image:'git-branch',tap_until_image:'mouse-pointer-2',tap_around_until_image:'scan-search'})[t] || 'circle';
}
function stepDetail(s){
  const t = s.type||'tap';
  if(t==='tap') return '('+(s.x||'?')+', '+(s.y||'?')+')';
  if(t==='swipe') return '('+(s.x||'?')+','+(s.y||'?')+')→('+(s.x2||'?')+','+(s.y2||'?')+')';
  if(t==='sleep') return (s.seconds||'?')+' วิ';
  if(t==='keyevent') return 'ปุ่ม '+(s.code||'?');
  if(t==='run_set') return s.set||'';
  if(t==='keyboard') return (s.key||'')+' ('+(s.action||'')+')';
  if(t==='tap_until_image') return 'กดรัว ('+(s.x||'?')+','+(s.y||'?')+') ทุก '+(s.interval||0.5)+' วิ จนเจอรูป';
  // บอกให้ชัดว่าเจอแล้วจะกดหรือแค่รอ — เดิมดูจากบล็อกไม่ออก ต้องเดาเอง
  if(t==='tap_around_until_image') return 'ไล่กดรอบๆ ' + (s.find_img?'การ์ดที่เจอ':'('+(s.x||'?')+','+(s.y||'?')+')') + ' ทุก '+(s.interval||0.5)+' วิ จนเจอเป้าหมาย';
  if(t==='wait_for_image') return (s.click===false ? 'รอจนเจอภาพ (ไม่กด)' : 'เจอที่ไหนกดที่นั่น') + (s.wait_img?' · ภาพที่ลากไว้':(s.text?' · '+s.text:''));
  if(t==='detect_image')  return (s.click===false ? 'เช็คภาพ (ไม่กด)' : 'เจอที่ไหนกดที่นั่น') + (s.wait_img?' · ภาพที่ลากไว้':(s.text?' · '+s.text:''));
  return s.text || s.desc || '';
}

function blockWarning(s){
  // ตรวจว่าบล็อกตั้งค่าครบไหม — คืนข้อความเตือน (ไทย) หรือ null ถ้าโอเค
  const t = s.type || 'tap';
  const empty = v => v == null || String(v).trim() === '' || String(v) === '0';
  if(t === 'tap' && (empty(s.x) || empty(s.y)) && !s.anchor_tap) return 'ยังไม่ตั้งพิกัด — กด "ตั้งพิกัดจากภาพจอ"';
  if(t === 'swipe' && (empty(s.x) || empty(s.x2))) return 'ยังไม่ตั้งจุดเริ่ม/ปลายการปัด';
  if(t === 'text' && !String(s.text || '').trim()) return 'ยังไม่ใส่ข้อความที่จะพิมพ์';
  // ตั้งภาพได้ 2 ทาง: ลากกรอบจากจอ (wait_img) หรือใส่ชื่อไฟล์ใน templates/ (text) — มีอย่างใดอย่างหนึ่งก็พอ
  if((t === 'detect_image' || t === 'wait_for_image' || t === 'tap_until_image') && !s.wait_img && !String(s.text || '').trim())
    return 'ยังไม่ตั้งภาพ — กด "ตั้งภาพจากจอ (ลากกรอบ)"';
  if(t === 'tap_until_image' && (empty(s.x) || empty(s.y))) return 'ยังไม่ตั้งพิกัดที่จะกดรัว';
  if(t === 'tap_around_until_image'){
    if(!s.wait_img && !String(s.text||'').trim()) return 'ยังไม่ตั้งภาพเป้าหมาย — กด "ตั้งภาพเป้าหมาย (modal)"';
    if(!s.find_img && (empty(s.x) || empty(s.y))) return 'ยังไม่ตั้งภาพการ์ด หรือพิกัดสำรอง';
  }
  if((t === 'tap_text' || t === 'wait_for_text') && !String(s.text || '').trim()) return 'ยังไม่ใส่ข้อความ/id ที่จะหา';
  if(t === 'run_set' && !String(s.set || '').trim()) return 'ยังไม่เลือกชุดคำสั่ง';
  if(t === 'start_app' || t === 'stop_app'){ if(!String(s.text || '').trim()) return 'ยังไม่ใส่ชื่อแพ็กเกจแอป'; }
  if(s.anchor_img && s.anchor_on_fail === 'retry' && s.anchor_retry_target == null)
    return 'เลือก "วนกลับ" ไว้แต่ยังไม่ได้ตั้งขั้นเป้าหมาย — กด "ตั้งค่ารอภาพ"';
  return null;
}

function flowChain(steps, basePath){
  let html = '';
  steps.forEach((s, i) => {
    const path = basePath.concat([i]);
    html += connector(path);
    html += flowBlock(s, path);
  });
  html += connector(basePath.concat([steps.length]));
  return html;
}

// เลขขั้นที่โชว์บนบล็อก — นับในลิสต์ของตัวเอง (เส้นหลักนับของเส้นหลัก, ในกิ่งนับของกิ่งนั้น)
// ต้องตรงกับเลขในช่อง 'วนกลับไปทำขั้นไหน' ของหน้าตั้งค่ารอภาพ ซึ่งก็อ้างลิสต์เดียวกัน
// ไม่งั้นผู้ใช้จะเลือกเป้าหมายผิดขั้นโดยไม่รู้ตัว
function stepNumBadge(path, color){
  const n = path[path.length - 1] + 1;
  return '<span title="ขั้นที่ ' + n + ' (ใช้เลขนี้ตอนตั้งวนกลับ)" style="flex:none;min-width:20px;height:20px;'
    + 'padding:0 5px;border-radius:6px;background:rgba(255,255,255,.06);border:1px solid ' + color + ';'
    + 'display:flex;align-items:center;justify-content:center;font-family:\'IBM Plex Mono\',monospace;'
    + 'font-size:10.5px;font-weight:600;color:' + color + '">' + n + '</span>';
}

function flowBlock(s, path){
  const t = s.type || 'tap';
  const pathStr = path.join('.');
  const selected = SEL_PATH && SEL_PATH.join('.') === pathStr;
  const running = FLOW_HL === pathStr;
  const hasImg = !!s.anchor_img;
  // อยู่ในช่วงที่คลุมไว้ (หรือกำลังถูกยกไปวาง) — ทำให้เห็นชัดว่ากำลังจะย้ายบล็อกไหนบ้าง
  const picked = inRange(path, FLOW_RANGE) || inRange(path, CUT_RANGE);
  const border = running ? '#10B981'
    : (picked ? '#38BDF8' : (selected ? 'rgba(16,185,129,.55)' : (t==='if_image' ? 'rgba(251,191,36,.45)' : '#24344B')));
  const glow = running ? 'box-shadow:0 0 0 3px rgba(16,185,129,.25);'
    : (picked ? 'box-shadow:0 0 0 2px rgba(56,189,248,.28);' : '');

  if(t === 'if_image'){
    const thenSteps = s.then || [], elseSteps = s['else'] || [];
    return '<div style="display:flex;flex-direction:column;align-items:center">'
      // หัวข้าวหลามตัด (เงื่อนไข)
      + '<div onclick="flowClick(event,' + pj(path) + ')" data-fpath="' + pathStr + '" style="' + glow + 'cursor:pointer;display:flex;gap:9px;align-items:center;padding:11px 16px;border-radius:12px;background:#221B0A;border:1.5px solid ' + border + '">'
      + stepNumBadge(path, '#B99B4A')
      + '<i data-lucide="git-branch" width="15" height="15" stroke-width="2" style="color:#FBBF24"></i>'
      + '<span style="font-size:12.5px;font-weight:600;color:#FBBF24">' + esc(s.desc || 'ถ้าเจอภาพ?') + '</span>'
      + (hasImg ? '<img src="data:image/png;base64,' + s.anchor_img + '" style="height:26px;border-radius:5px;border:1px solid #7A5A1E">'
                : (s.text ? '<span style="font-family:\'IBM Plex Mono\',monospace;font-size:11px;color:#B99B4A">' + esc(s.text) + '</span>'
                          : '<span style="font-size:11px;color:#F87171">⚠ ยังไม่ตั้งภาพ</span>'))
      + '</div>'
      // สองเลน: เจอ / ไม่เจอ
      + '<div style="display:flex;gap:26px;align-items:flex-start;margin-top:4px">'
      +   '<div style="display:flex;flex-direction:column;align-items:center;min-width:150px;padding:8px 10px;border-radius:12px;border:1px dashed rgba(16,185,129,.35)">'
      +     '<span style="font-size:11px;font-weight:600;color:#6EE7B7">✅ เจอ → ทำชุดนี้</span>'
      +     flowChain(thenSteps, path.concat(['then']))
      +   '</div>'
      +   '<div style="display:flex;flex-direction:column;align-items:center;min-width:150px;padding:8px 10px;border-radius:12px;border:1px dashed rgba(248,113,113,.3)">'
      +     '<span style="font-size:11px;font-weight:600;color:#FCA5A5">❌ ไม่เจอ → ทำชุดนี้</span>'
      +     flowChain(elseSteps, path.concat(['else']))
      +   '</div>'
      + '</div>'
      // จุดรวมกลับเส้นหลัก
      + '<div style="width:2px;height:8px;background:#24344B;margin-top:2px"></div>'
      + '<div style="font-size:10px;color:#5C6B82">↩ กลับเส้นหลัก</div>'
      + '</div>';
  }

  // ตั้งวนกลับไว้ (anchor_on_fail='retry' + มีเป้าหมาย) — เก็บคู่ path ไว้วาดเส้นแบบ flowchart หลังเรนเดอร์เสร็จ
  const hasRetry = hasImg && s.anchor_on_fail === 'retry' && s.anchor_retry_target != null;
  if(hasRetry){
    const targetPath = path.slice(0, -1).concat([s.anchor_retry_target]).join('.');
    RETRY_ARROWS.push({from: pathStr, to: targetPath});
  }

  const warn = blockWarning(s);
  const bColor = warn ? '#F87171' : border;
  return '<div onclick="flowClick(event,' + pj(path) + ')" data-fpath="' + pathStr + '" style="' + glow + 'cursor:pointer;min-width:220px;max-width:330px;display:flex;gap:9px;align-items:center;padding:10px 13px;border-radius:11px;background:' + (selected?'rgba(16,185,129,.08)':'#0A0F19') + ';border:1.5px solid ' + bColor + '">'
    + stepNumBadge(path, warn ? '#F87171' : '#5C6B82')
    + '<i data-lucide="' + stepIcon(t) + '" width="15" height="15" stroke-width="1.9" style="color:' + (hasImg?'#FBBF24':'#7DD3FC') + ';flex:none"></i>'
    + '<div style="flex:1;min-width:0"><div style="font-size:12.5px;font-weight:500">' + esc(s.desc || typeTH(t)) + '</div>'
    + '<div style="font-family:\'IBM Plex Mono\',monospace;font-size:10.5px;color:' + (warn?'#FCA5A5':'#7C8CA3') + ';overflow:hidden;text-overflow:ellipsis;white-space:nowrap">' + (warn ? '⚠ ' + esc(warn) : esc(typeTH(t)) + ' · ' + esc(stepDetail(s))) + '</div></div>'
    + (hasRetry ? '<i data-lucide="repeat" width="13" height="13" style="color:#FBBF24;flex:none" title="ไม่เจอภาพ → วนกลับไปทำขั้นก่อนหน้าใหม่"></i>' : '')
    + (hasImg ? '<i data-lucide="image" width="13" height="13" style="color:#FBBF24;flex:none" title="มีภาพ anchor"></i>' : '')
    // ภาพต้นแบบที่ขั้นนี้รอ/จะกด (ลากกรอบไว้) — ขอบเหลืองเพราะมีผลต่อการรันจริง
    + (s.find_img ? '<img src="data:image/png;base64,' + s.find_img + '" title="ภาพการ์ดที่จะไล่กดรอบๆ" '
        + 'style="flex:none;max-width:52px;height:34px;object-fit:contain;border-radius:5px;border:1px solid #164E72;background:#0A0F19">' : '')
    + (s.wait_img ? '<img src="data:image/png;base64,' + s.wait_img + '" title="ภาพที่ขั้นนี้รอให้เจอ" '
        + 'style="flex:none;max-width:52px;height:34px;object-fit:contain;border-radius:5px;border:1px solid #7A5A1E;background:#0A0F19">' : '')
    // ภาพช่วยจำว่าขั้นนี้กดปุ่มอะไร (กากบาทแดง = จุดที่กดจริง) — ไม่มีผลต่อการรัน
    + (s.preview_img ? '<img src="data:image/png;base64,' + s.preview_img + '" title="ตำแหน่งที่กด — กากบาทแดงคือจุดกดจริง" '
        + 'style="flex:none;width:40px;height:40px;object-fit:cover;border-radius:6px;border:1px solid #24344B">' : '')
    + '</div>';
}

// ---------- เลือกบล็อก → ฟอร์มขวา + ปุ่มจัดการ ----------
async function flowSelect(path){
  SEL_PATH = path;
  const r = hasPy() ? await PY.flow_get_step(path) : { ok:true, step: _demoAt(path) };
  if(r && r.ok && r.step){
    const s = r.step;
    fillStepForm({ type:s.type||'tap', desc:s.desc||'', x:s.x||'', y:s.y||'', x2:s.x2||'', y2:s.y2||'',
      duration:s.duration||'', text:s.text||'', code:s.code||'', key:s.key||'', action:s.action||'',
      seconds:s.seconds||'', timeout:s.timeout||'', set:s.set||'', threshold:s.threshold||'',
      block_on_fail:s.block_on_fail||'', block_home:s.block_home||'', block_retries:(s.block_retries!=null?s.block_retries:''),
      delay:(s.delay!=null?s.delay:'') });
    renderFlowActions(s, path);
  }
  renderFlow();
}
function _demoAt(path){
  let cur = DEMO_FLOW.steps, node = null;
  for(let j=0;j<path.length;j++){
    const tok = path[j];
    if(typeof tok === 'string'){ cur = node[tok]||[]; }
    else { if(j===path.length-1) return cur[tok]; node = cur[tok]; }
  }
  return null;
}

function renderFlowActions(s, path){
  const box = document.getElementById('flowActions');
  if(!box) return;
  const t = s.type||'tap';
  const isRoot = path.length === 1;
  const btn = (on, icon, label, style) => '<button class="in" onclick="' + on + '" style="display:flex;align-items:center;justify-content:center;gap:6px;height:34px;border-radius:8px;font-size:11.5px;cursor:pointer;padding:0 10px;' + style + '"><i data-lucide="' + icon + '" width="13" height="13" stroke-width="1.9"></i>' + label + '</button>';
  let html = '<div style="display:grid;grid-template-columns:1fr 1fr;gap:7px">';
  html += btn('flowMoveSel(-1)','arrow-up','ขึ้น','background:#121A28;border:1px solid #24344B;color:#C7D2E0');
  html += btn('flowMoveSel(1)','arrow-down','ลง','background:#121A28;border:1px solid #24344B;color:#C7D2E0');
  html += btn('flowStartCut()','scissors','ย้ายไปที่อื่น','background:#0F2F4A;border:1px solid #164E72;color:#7DD3FC');
  html += btn('flowMoveIntoBranch()','git-branch','ย้ายเข้าเงื่อนไข','background:#2E2410;border:1px solid #7A5A1E;color:#FBBF24');
  if(t==='tap'||t==='swipe'||t==='tap_until_image'){
    html += btn('flowPickCoord()','crosshair','ตั้งพิกัดจากภาพจอ','background:#0F2F4A;border:1px solid #164E72;color:#7DD3FC');
    html += btn('flowPickImage(\'anchor\')','image-plus','อัดภาพรอก่อนกด','background:#2E2410;border:1px solid #7A5A1E;color:#FBBF24');
  }
  if(s.preview_img){
    html += btn('flowClearPreview()','image-off','ลบภาพจุดที่กด','background:#121A28;border:1px solid #24344B;color:#C7D2E0');
  }
  if(t==='if_image'){
    html += btn('flowPickImage(\'cond\')','image-plus','ตั้งภาพเงื่อนไขจากจอ','background:#2E2410;border:1px solid #7A5A1E;color:#FBBF24');
    html += btn('flowTestMatch()','flask-conical','ทดสอบว่าเจอไหม','background:#121A28;border:1px solid #24344B;color:#C7D2E0');
  }
  if(t==='tap_around_until_image'){
    html += btn('flowPickImage(\'find\')','crop','ตั้งภาพการ์ด (ที่จะกดรอบๆ)','background:#0F2F4A;border:1px solid #164E72;color:#7DD3FC');
    html += btn('flowPickImage(\'wait\')','image-plus','ตั้งภาพเป้าหมาย (modal)','background:#2E2410;border:1px solid #7A5A1E;color:#FBBF24');
    if(s.wait_img) html += btn('flowTestWaitMatch()','flask-conical','ทดสอบภาพเป้าหมาย','background:#121A28;border:1px solid #24344B;color:#C7D2E0');
    if(s.find_img) html += btn('flowTestFindMatch()','flask-conical','ทดสอบภาพการ์ด','background:#121A28;border:1px solid #24344B;color:#C7D2E0');
  }
  if(t==='wait_for_image'||t==='detect_image'||t==='tap_until_image'){
    // ลากกรอบจากจอจริงแทนการพิมพ์ชื่อไฟล์ใน templates/ เอง
    html += btn('flowPickImage(\'wait\')','image-plus','ตั้งภาพจากจอ (ลากกรอบ)','background:#2E2410;border:1px solid #7A5A1E;color:#FBBF24');
    if(s.wait_img) html += btn('flowTestWaitMatch()','flask-conical','ทดสอบว่าเจอไหม','background:#121A28;border:1px solid #24344B;color:#C7D2E0');
  }
  if(s.anchor_img && t!=='if_image'){
    html += btn('flowAnchorOpts()','settings-2','ตั้งค่ารอภาพ','background:#121A28;border:1px solid #24344B;color:#C7D2E0');
    html += btn('flowClearImage()','image-off','ลบภาพออก','background:#121A28;border:1px solid #24344B;color:#90A0B7');
  }
  if(isRoot) html += btn('flowRunFrom()','play','ทดลองรันจากนี่','background:rgba(16,185,129,.14);border:1px solid rgba(16,185,129,.3);color:#6EE7B7');
  html += btn('flowDeleteSel()','trash-2','ลบบล็อกนี้','background:#2A1113;border:1px solid #7F1D1D;color:#FCA5A5');
  html += '</div>';
  box.innerHTML = html;
  icons();
}

// ---------- แทรก/แก้/ลบ/ย้าย ----------
async function flowInsertAt(path){
  if(!hasPy() && SCRIPT_VIEW==='flow'){ notReady('แทรกบล็อก (ต้องเปิดผ่าน .exe)'); return; }
  const opts = (FLOW && FLOW.typeOptions) || FALLBACK_TYPE_OPTIONS;
  const items = opts.map(o =>
    '<button class="in" onclick="flowDoInsert(' + pj(path) + ',\'' + o.value + '\')" style="display:flex;gap:9px;align-items:center;width:100%;padding:9px 12px;border-radius:8px;background:#0A0F19;border:1px solid #1B2434;color:#C7D2E0;font-size:12.5px;cursor:pointer;text-align:left">'
    + '<i data-lucide="' + stepIcon(o.value) + '" width="14" height="14" style="color:' + (o.value==='if_image'?'#FBBF24':'#7DD3FC') + ';flex:none"></i>' + esc(o.label) + '</button>').join('');

  // พรีเซ็ตพิกัดที่ผู้ใช้เก็บไว้ — วางตรงจุดนี้ได้เลย (เดิมต่อท้ายเส้นหลักได้อย่างเดียว)
  let presetHtml = '';
  if(hasPy()){
    const pr = await PY.get_presets();
    const list = (pr && pr.presets) || [];
    if(list.length){
      presetHtml = '<div style="margin-top:12px;font-size:11px;font-weight:600;letter-spacing:1px;color:#7C8CA3;text-transform:uppercase">พรีเซ็ตพิกัดที่บันทึกไว้</div>'
        + '<div style="display:flex;flex-direction:column;gap:5px;margin-top:6px">'
        + list.map(p =>
          '<button class="in" onclick="flowDoInsertPreset(' + pj(path) + ',\'' + jsq(p.name) + '\')" style="display:flex;gap:9px;align-items:center;width:100%;padding:9px 12px;border-radius:8px;background:#0A0F19;border:1px solid #1B2434;color:#C7D2E0;font-size:12.5px;cursor:pointer;text-align:left">'
          + '<i data-lucide="bookmark" width="14" height="14" style="color:#6EE7B7;flex:none"></i>'
          + '<span style="flex:1">' + esc(p.name) + '</span>'
          + '<span style="font-family:\'IBM Plex Mono\',monospace;font-size:10.5px;color:#5C6B82">(' + esc(p.x) + ', ' + esc(p.y) + ')</span></button>').join('')
        + '</div>';
    }
  }

  // ชุดคำสั่งย่อยที่บันทึกไว้ — เลือกจากรายการ ไม่ต้องพิมพ์ชื่อเองให้ผิด
  let setHtml = '';
  if(hasPy()){
    const sr = await PY.list_script_sets();
    const sets = (sr && sr.sets) || [];
    if(sets.length){
      setHtml = '<div style="margin-top:12px;font-size:11px;font-weight:600;letter-spacing:1px;color:#7C8CA3;text-transform:uppercase">ชุดคำสั่งย่อยที่บันทึกไว้</div>'
        + '<div style="font-size:11px;color:#5C6B82;margin:4px 0 6px">คลิก = ใช้ชุดนั้นตรง ๆ · กด 🛡 = ทำเป็นบล็อกกันพัง (ถ้าพังให้กลับหน้าแรกแล้วลองใหม่)</div>'
        + '<div style="display:flex;flex-direction:column;gap:5px">'
        + sets.map(s => {
            const n = jsq(s.name);
            return '<div style="display:flex;gap:5px;align-items:center">'
              + '<button class="in" onclick="flowDoInsertSet(' + pj(path) + ',\'' + n + '\',false)" style="flex:1;display:flex;gap:9px;align-items:center;padding:9px 12px;border-radius:8px;background:#0A0F19;border:1px solid #1B2434;color:#C7D2E0;font-size:12.5px;cursor:pointer;text-align:left">'
              + '<i data-lucide="layers" width="14" height="14" style="color:#7DD3FC;flex:none"></i>'
              + '<span style="flex:1">' + esc(s.name) + '</span>'
              + '<span style="font-size:10.5px;color:#5C6B82">' + s.count + ' ขั้น</span></button>'
              + '<button class="in" title="แทรกเป็นบล็อกกันพัง (พังแล้วลองใหม่)" onclick="flowDoInsertSet(' + pj(path) + ',\'' + n + '\',true)" style="flex:none;padding:9px 11px;border-radius:8px;background:#2E2410;border:1px solid #7A5A1E;color:#FBBF24;font-size:12.5px;cursor:pointer">🛡</button>'
              + '</div>';
          }).join('')
        + '</div>';
    }
  }

  openModal('เลือกสิ่งที่จะแทรกตรงนี้', 'plus-circle',
    '<div style="font-size:11px;font-weight:600;letter-spacing:1px;color:#7C8CA3;text-transform:uppercase;margin-bottom:6px">บล็อกเปล่า</div>'
    + '<div style="display:flex;flex-direction:column;gap:5px">' + items + '</div>'
    + setHtml + presetHtml);
}
async function flowDoInsertSet(path, name, asBlock){
  closeModal();
  if(!hasPy()) return;
  // บล็อกกันพัง: ใช้ 'กลับหน้าแรก' เป็นชุดกู้เริ่มต้นถ้ามีอยู่ (แก้ทีหลังได้ในฟอร์ม)
  let home = '';
  if(asBlock){
    const sr = await PY.list_script_sets();
    const names = ((sr && sr.sets) || []).map(s=>s.name);
    if(names.includes('กลับหน้าแรก')) home = 'กลับหน้าแรก';
  }
  const r = await PY.flow_add_set(path, name, !!asBlock, home, '');
  if(r && r.flow) FLOW = r.flow;
  if(r && !r.ok && r.error) notReady(r.error);
  renderFlow();
  if(r && r.ok && r.path) await flowSelect(r.path);
}
async function flowDoInsertPreset(path, name){
  closeModal();
  if(!hasPy()) return;
  const r = await PY.flow_add_preset(path, name);
  if(r && r.flow) FLOW = r.flow;
  renderFlow();
  if(r && r.ok && r.path) await flowSelect(r.path);
}
async function flowDoInsert(path, type){
  closeModal();
  if(!hasPy()) return;
  FLOW = await PY.flow_add(path, type);
  await flowSelect(path);
}
async function flowSaveSel(){
  if(!hasPy() || !SEL_PATH){ notReady('เลือกบล็อกก่อน'); return; }
  FLOW = await PY.flow_update(SEL_PATH, collectStepPatch());
  renderFlow();
}
async function flowDeleteSel(){
  if(!hasPy() || !SEL_PATH) return;
  FLOW = await PY.flow_delete(SEL_PATH);
  SEL_PATH = null;
  const box = document.getElementById('flowActions'); if(box) box.innerHTML='';
  renderFlow();
}
async function flowMoveSel(dir){
  if(!hasPy() || !SEL_PATH) return;
  FLOW = await PY.flow_move(SEL_PATH, dir);
  const p = SEL_PATH.slice(); p[p.length-1] = Math.max(0, p[p.length-1]+dir);
  SEL_PATH = p;
  renderFlow();
}

// ---------- ย้ายบล็อกข้ามที่ (ตัด -> วาง) ----------
// ปุ่ม 'ขึ้น/ลง' ย้ายได้แค่ในลิสต์เดียวกัน ย้ายเข้า/ออกกิ่ง if ไม่ได้ — โหมดนี้เลยเติมช่องว่างนั้น
// ตัดค้างไว้ แล้วจุด + ทุกจุดบนผัง (รวมจุดในกิ่ง then/else) จะกลายเป็นปุ่ม 'วาง' ทันที
function flowStartCut(){
  // ถ้าคลุมช่วงไว้ = ย้ายทั้งชุด ไม่งั้นย้ายบล็อกเดียวที่เลือกอยู่
  if(FLOW_RANGE){
    CUT_RANGE = [FLOW_RANGE[0].slice(), FLOW_RANGE[1].slice()];
    CUT_PATH = null;
  }else if(SEL_PATH){
    CUT_PATH = SEL_PATH.slice();
    CUT_RANGE = null;
  }else{
    notReady('เลือกบล็อกก่อน (Shift+คลิก = เลือกหลายอัน)');
    return;
  }
  FLOW_RANGE = null;
  renderFlow();
}
function flowCancelCut(){
  CUT_PATH = null; CUT_RANGE = null;
  renderFlow();
}
async function flowDropAt(dstPath){
  if(!hasPy()) return;
  let r = null;
  if(CUT_RANGE){
    r = await PY.flow_move_range(CUT_RANGE[0], CUT_RANGE[1], dstPath);
  }else if(CUT_PATH){
    r = await PY.flow_move_to(CUT_PATH, dstPath);
  }else{
    return;
  }
  CUT_PATH = null; CUT_RANGE = null;
  if(r && r.flow) FLOW = r.flow;
  if(r && r.ok){
    SEL_PATH = r.path;                       // เลือกบล็อกเดิมต่อ ทำงานต่อได้ทันทีไม่ต้องหาใหม่
  }else if(r && r.error){
    notReady('ย้ายไม่ได้: ' + r.error);
  }
  renderFlow();
  if(SEL_PATH) await flowSelect(SEL_PATH);
}

// ปุ่มลัดสำหรับเคสที่ใช้บ่อยสุด: เอาบล็อกนี้ยัดเข้าเงื่อนไข if ที่อยู่ในผังเดียวกัน
async function flowMoveIntoBranch(){
  if(!hasPy() || !SEL_PATH){ notReady('เลือกบล็อกก่อน'); return; }
  const r = await PY.flow_branch_targets(SEL_PATH);
  const targets = (r && r.targets) || [];
  if(!targets.length){
    notReady('ผังนี้ยังไม่มีบล็อกเงื่อนไข (ถ้าเจอภาพ) ให้ย้ายเข้า');
    return;
  }
  const items = targets.map(t =>
    '<button class="in" onclick="flowDoMoveInto(' + pj(t.path) + ')" style="display:flex;gap:9px;align-items:center;width:100%;padding:10px 12px;border-radius:8px;background:#0A0F19;border:1px solid #1B2434;color:#C7D2E0;font-size:12.5px;cursor:pointer;text-align:left">'
    + '<i data-lucide="git-branch" width="14" height="14" style="color:#FBBF24;flex:none"></i>'
    + '<span style="flex:1">' + esc(t.label) + '</span>'
    + '<span style="color:#5C6B82;font-size:11px">' + t.count + ' ขั้น</span></button>').join('');
  openModal('ย้ายเข้าเงื่อนไขไหน', 'git-branch',
    '<div style="display:flex;flex-direction:column;gap:5px">' + items + '</div>'
    + '<div style="margin-top:10px;font-size:11.5px;color:#5C6B82">บล็อกจะไปต่อท้ายกิ่งที่เลือก '
    + 'ถ้าอยากวางตำแหน่งอื่นให้ใช้ปุ่ม “ย้ายไปที่อื่น” แล้วกดจุด “วาง” บนผังแทน</div>');
}
async function flowDoMoveInto(dstPath){
  closeModal();
  CUT_PATH = SEL_PATH ? SEL_PATH.slice() : null;
  await flowDropAt(dstPath);
}
async function flowRunFrom(){
  if(!hasPy() || !SEL_PATH || SEL_PATH.length!==1) return;
  const r = await PY.run_from(SEL_PATH[0]);
  if(r && r.ok){ setRunBtn(true); startRunPoll(); }
}

// ---------- ตั้งพิกัด/ภาพ จากภาพจอจริง ----------
async function flowPickCoord(){
  if(!hasPy() || !SEL_PATH) return;
  const st = (await PY.flow_get_step(SEL_PATH)).step || {};
  const isSwipe = st.type === 'swipe';
  const shot = await PY.screenshot_b64();
  if(!shot || !shot.ok){ openModal('ตั้งพิกัด','crosshair','<div style="font-size:12.5px;color:#FCA5A5">แคปจอไม่ได้ — เลือกจอก่อน</div>'); return; }
  openModal('ตั้งพิกัดจากภาพจอ · ' + esc(shot.device||''), 'crosshair',
    '<div id="fpHint" style="font-size:12px;color:#7C8CA3;margin-bottom:8px">' + (isSwipe?'คลิก 2 จุด: จุดเริ่มปัด → จุดปล่อย':'คลิกตำแหน่งที่จะให้กด') + ' (จอ ' + shot.w + '×' + shot.h + ')</div>'
    + '<div style="position:relative;display:inline-block;max-width:100%"><img id="fpImg" src="' + shot.img + '" data-w="' + shot.w + '" data-h="' + shot.h + '" style="max-width:100%;border-radius:10px;border:1px solid #24344B;cursor:crosshair;display:block"></div>');
  const img = document.getElementById('fpImg');
  let first = null;
  // ใช้ขนาดจริงของภาพ (naturalWidth) เป็นหลัก — พื้นที่เดียวกับ input tap เสมอ
  const toReal = ev => { const rc = img.getBoundingClientRect();
    const rw = img.naturalWidth || +img.dataset.w, rh = img.naturalHeight || +img.dataset.h;
    return { x: (ev.clientX-rc.left)/rc.width*rw, y: (ev.clientY-rc.top)/rc.height*rh }; };
  img.addEventListener('click', async ev => {
    const p = toReal(ev);
    if(isSwipe && !first){
      first = p;
      document.getElementById('fpHint').textContent = 'จุดเริ่ม (' + Math.round(p.x) + ',' + Math.round(p.y) + ') ✓ — คลิกจุดปล่อย';
      return;
    }
    // ส่งภาพจอที่คลิกไปด้วย -> ฝั่ง Python ครอปเก็บภาพรอบจุดกดไว้เป็นตัวช่วยจำ
    // (ใช้ภาพเดียวกับที่ผู้ใช้เพิ่งเห็นและคลิก ไม่แคปใหม่ กันจอเปลี่ยนระหว่างนั้น)
    if(isSwipe){ FLOW = await PY.flow_set_xy(SEL_PATH, first.x, first.y, p.x, p.y, shot.img); }
    else { FLOW = await PY.flow_set_xy(SEL_PATH, p.x, p.y, null, null, shot.img); }
    closeModal();
    await flowSelect(SEL_PATH);
  });
}

async function flowPickImage(mode){
  if(!hasPy() || !SEL_PATH) return;
  const shot = await PY.screenshot_b64();
  if(!shot || !shot.ok){ openModal('ตั้งภาพ','image-plus','<div style="font-size:12.5px;color:#FCA5A5">แคปจอไม่ได้ — เลือกจอก่อน</div>'); return; }
  const hint = mode==='cond' ? 'ลากกรอบคลุม "ภาพที่ใช้เป็นเงื่อนไข" (เช่น ป๊อปอัพ/ปุ่มที่จะเช็คว่าโผล่ไหม)'
             : mode==='wait' ? 'ลากกรอบคลุม "ภาพที่จะรอ/จะกด" — ระบบจะวนเช็คจนเจอ แล้วกดตรงกลางภาพนั้นให้'
                             : 'ลากกรอบคลุม "ภาพที่ต้องเห็นก่อนกด" (เลือกจุดนิ่งๆ ใกล้ปุ่ม)';
  openModal('ตั้งภาพจากการลากกรอบ · ' + esc(shot.device||''), 'image-plus',
    '<div style="font-size:12px;color:#7C8CA3;margin-bottom:8px">' + hint + '</div>'
    + '<div id="fiInfo" style="font-family:\'IBM Plex Mono\',monospace;font-size:12px;color:#6EE7B7;margin-bottom:8px">ยังไม่ได้ลากกรอบ</div>'
    + '<div style="position:relative;display:inline-block;max-width:100%"><img id="fiImg" src="' + shot.img + '" data-w="' + shot.w + '" data-h="' + shot.h + '" style="max-width:100%;border-radius:10px;border:1px solid #24344B;cursor:crosshair;display:block;user-select:none">'
    + '<div id="fiRect" style="position:absolute;border:2px solid #FBBF24;background:rgba(251,191,36,.15);display:none;pointer-events:none"></div></div>'
    + '<div style="display:flex;gap:8px;margin-top:12px">'
    + '<button class="in" onclick="flowSaveImage(\'' + mode + '\')" style="flex:1;display:flex;align-items:center;justify-content:center;gap:7px;height:40px;border-radius:9px;background:#10B981;color:#04120C;font-size:13px;font-weight:600;cursor:pointer"><i data-lucide="save" width="15" height="15" stroke-width="2"></i>ใช้กรอบนี้</button>'
    + '<button class="in" onclick="flowTestDraft()" style="flex:1;display:flex;align-items:center;justify-content:center;gap:7px;height:40px;border-radius:9px;background:#2E2410;border:1px solid #7A5A1E;color:#FBBF24;font-size:12.5px;cursor:pointer"><i data-lucide="flask-conical" width="14" height="14" stroke-width="1.9"></i>ทดสอบว่าเจอไหม</button></div>');
  icons();
  const img = document.getElementById('fiImg'), rect = document.getElementById('fiRect');
  let sx, sy, drag = false; window._flowReg = null; window._flowShot = shot;
  const rel = ev => { const rc = img.getBoundingClientRect(); return { x: ev.clientX-rc.left, y: ev.clientY-rc.top }; };
  img.addEventListener('mousedown', ev => { ev.preventDefault(); const p = rel(ev); sx=p.x; sy=p.y; drag=true;
    rect.style.display='block'; rect.style.left=sx+'px'; rect.style.top=sy+'px'; rect.style.width='0'; rect.style.height='0'; });
  window.addEventListener('mousemove', ev => { if(!drag) return; const p = rel(ev);
    const x=Math.min(sx,p.x), y=Math.min(sy,p.y), w=Math.abs(p.x-sx), h=Math.abs(p.y-sy);
    rect.style.left=x+'px'; rect.style.top=y+'px'; rect.style.width=w+'px'; rect.style.height=h+'px';
    const rc = img.getBoundingClientRect();
    const rw = img.naturalWidth || +img.dataset.w, rh = img.naturalHeight || +img.dataset.h;
    window._flowReg = { x:Math.round(x/rc.width*rw), y:Math.round(y/rc.height*rh),
                        w:Math.round(w/rc.width*rw), h:Math.round(h/rc.height*rh) };
    const g = window._flowReg;
    document.getElementById('fiInfo').textContent = 'กรอบ: x='+g.x+' y='+g.y+' กว้าง='+g.w+' สูง='+g.h; });
  window.addEventListener('mouseup', () => { drag=false; });
}
async function flowSaveImage(mode){
  const g = window._flowReg;
  if(!g || g.w<8 || g.h<8){ document.getElementById('fiInfo').textContent = '⚠ ลากกรอบให้ใหญ่กว่านี้ก่อน'; return; }
  const b64 = await PY.crop_image_b64(window._flowShot.img, g.x, g.y, g.w, g.h);
  if(!b64 || !b64.ok){ document.getElementById('fiInfo').textContent = '⚠ ครอปภาพไม่สำเร็จ'; return; }
  FLOW = await PY.flow_set_image(SEL_PATH, b64.img, g, mode);
  closeModal();
  await flowSelect(SEL_PATH);
}
async function flowTestDraft(){
  const g = window._flowReg;
  if(!g || g.w<8 || g.h<8){ document.getElementById('fiInfo').textContent = '⚠ ลากกรอบก่อนถึงทดสอบได้'; return; }
  const b64 = await PY.crop_image_b64(window._flowShot.img, g.x, g.y, g.w, g.h);
  if(!b64 || !b64.ok) return;
  const r = await PY.test_anchor_match(b64.img, 0.8);
  document.getElementById('fiInfo').textContent = (r && r.found)
    ? '✅ เจอบนจอตอนนี้ (' + r.x + ',' + r.y + ') — ใช้ได้'
    : '❌ ไม่เจอ/ความเหมือนต่ำ — ลองเลือกบริเวณที่นิ่งกว่านี้';
}
async function flowTestFindMatch(){
  if(!hasPy() || !SEL_PATH) return;
  const st = (await PY.flow_get_step(SEL_PATH)).step || {};
  if(!st.find_img){ notReady('ยังไม่ได้ตั้งภาพการ์ด'); return; }
  const r = await PY.test_anchor_match(st.find_img, st.threshold || 0.8);
  openModal('ทดสอบภาพการ์ด', 'flask-conical',
    '<div style="font-size:13px;color:' + (r&&r.found?'#6EE7B7':'#FCA5A5') + '">'
    + (r&&r.found ? '✅ เจอการ์ดบนจอตอนนี้ ที่ (' + r.x + ',' + r.y + ') — จะไล่กดรอบจุดนี้'
                  : '❌ ไม่เจอการ์ดบนจอตอนนี้ — ' + esc((r&&(r.msg||r.error))||'')) + '</div>');
}

async function flowTestWaitMatch(){
  if(!hasPy() || !SEL_PATH) return;
  const st = (await PY.flow_get_step(SEL_PATH)).step || {};
  if(!st.wait_img){ notReady('ยังไม่ได้ลากกรอบภาพ'); return; }
  const r = await PY.test_anchor_match(st.wait_img, st.threshold || 0.8);
  openModal('ทดสอบภาพต้นแบบ', 'flask-conical',
    '<div style="font-size:13px;color:' + (r&&r.found?'#6EE7B7':'#FCA5A5') + '">'
    + (r&&r.found ? '✅ เจอบนจอตอนนี้ ที่ (' + r.x + ',' + r.y + ') — ขั้นนี้จะกดตรงนั้น'
                  : '❌ ไม่เจอบนจอตอนนี้ — ' + esc((r&&(r.msg||r.error))||'')) + '</div>');
}

async function flowTestMatch(){
  if(!hasPy() || !SEL_PATH) return;
  const st = (await PY.flow_get_step(SEL_PATH)).step || {};
  if(!st.anchor_img){ notReady('ยังไม่ได้ตั้งภาพเงื่อนไข'); return; }
  const r = await PY.test_anchor_match(st.anchor_img, st.threshold || 0.8);
  openModal('ทดสอบเงื่อนไข', 'flask-conical',
    '<div style="font-size:13px;color:' + (r&&r.found?'#6EE7B7':'#FCA5A5') + '">'
    + (r&&r.found ? '✅ เจอบนจอตอนนี้ ที่ (' + r.x + ',' + r.y + ')' : '❌ ไม่เจอบนจอตอนนี้ — ' + esc((r&&(r.msg||r.error))||'')) + '</div>');
}
async function flowClearImage(){
  if(!hasPy() || !SEL_PATH) return;
  FLOW = await PY.flow_clear_image(SEL_PATH);
  await flowSelect(SEL_PATH);
}
async function flowAnchorOpts(){
  if(!hasPy() || !SEL_PATH) return;
  const st = (await PY.flow_get_step(SEL_PATH)).step || {};
  const sib = await PY.list_siblings(SEL_PATH);
  const cur = st.anchor_on_fail || 'pause';
  const opt = (v, label) => '<label style="display:flex;gap:8px;align-items:center;padding:8px 10px;border-radius:8px;background:#0A0F19;border:1px solid #1B2434;cursor:pointer;font-size:12.5px"><input type="radio" name="aof" value="' + v + '" onchange="toggleRetryFields()"' + (cur===v?' checked':'') + '>' + label + '</label>';
  const steps = (sib && sib.ok) ? sib.steps : [];
  const targetOpts = steps.map(s =>
    '<option value="' + s.idx + '"' + (st.anchor_retry_target===s.idx?' selected':'') + '>ขั้น ' + (s.idx+1) + ': ' + esc(s.desc) + '</option>').join('');
  openModal('ตั้งค่ารอภาพก่อนกด', 'settings-2',
    '<div style="display:flex;flex-direction:column;gap:10px">'
    + '<div style="font-size:12px;color:#90A0B7">ถ้ารอจนหมดเวลาแล้ว "ไม่เจอภาพ" ให้ทำยังไง:</div>'
    // 'pause' เป็นค่าเริ่มต้น/ตัวหลักแล้ว (เรียนรู้ทีละจอ) เลยเอาไว้บนสุด — ระบบไม่รีเซ็ตเกมอัตโนมัติอีกแล้ว
    // ไม่ว่าจะเลือกอันไหนก็ตาม (retry ยังต้องตั้งเองเสมอ ไม่ใช่ค่าเริ่มต้น)
    + opt('pause','⏸ หยุดรอผู้ใช้แก้ไข (เรียนรู้ทีละจอ) — แนะนำ')
    + '<div style="display:' + (cur==='pause'?'block':'none') + ';font-size:11px;color:#5C6B82;margin-left:4px" id="aofPauseNote">ถ้าไม่เจอ จะลองย้อนไปกดขั้นก่อนหน้าซ้ำ 1 ครั้งแล้วเช็คใหม่ก่อน (เผื่อจอ/เครื่องค้างตอนกดรอบแรก) — ถ้ายังไม่เจอจริง ๆ จอจะหยุดค้างไว้ตามที่เห็น (ไม่รีเซ็ตเกม) แล้วขึ้นในแผง "จอที่รอแก้ไข" หน้าแรก — เข้าไปเพิ่มเงื่อนไข/if แล้วกด "รันต่อ" ได้เลย</div>'
    + opt('retry','🔁 วนกลับไปทำขั้นที่เลือกใหม่ (ลองซ้ำ)')
    + opt('skip','ข้ามสเต็ปนี้ไป') + opt('tap','กดตามพิกัดเดิม (เสี่ยง)') + opt('abort','หยุดจอนี้เฉยๆ (ไม่รอ ไม่วน)')
    + '<div id="aofRetryBox" style="display:' + (cur==='retry'?'flex':'none') + ';flex-direction:column;gap:8px;padding:10px;border-radius:8px;background:#0A0F19;border:1px dashed #24344B;margin-left:4px">'
    +   '<div style="display:flex;flex-direction:column;gap:5px"><span style="font-size:11.5px;color:#90A0B7">วนกลับไปทำขั้นไหน (ในลิสต์เดียวกัน)</span>'
    +   '<select id="aofTarget" class="in" style="height:36px;border-radius:8px;background:#0E1420;border:1px solid #24344B;padding:0 10px;font-size:12.5px;color:#C7D2E0;cursor:pointer">' + targetOpts + '</select></div>'
    +   '<div style="display:flex;gap:10px;align-items:center"><span style="font-size:12px;color:#90A0B7">วนได้สูงสุด (รอบ):</span>'
    +   '<input id="aofRetryLimit" class="in" value="' + (st.anchor_retry_limit!=null?st.anchor_retry_limit:3) + '" style="width:60px;height:34px;border-radius:8px;background:#0E1420;border:1px solid #24344B;padding:0 10px;font-family:\'IBM Plex Mono\',monospace;font-size:12.5px;color:#C7D2E0"></div>'
    +   '<div style="font-size:11px;color:#5C6B82">ครบรอบแล้วยังไม่เจอ จะ fallback ไปหยุดจอนี้เอง กันวนไม่รู้จบ</div>'
    + '</div>'
    + '<div style="display:flex;gap:10px;align-items:center"><span style="font-size:12px;color:#90A0B7">รอสูงสุด (วิ):</span>'
    + '<input id="aofTimeout" class="in" value="' + (st.anchor_timeout!=null?st.anchor_timeout:30) + '" style="width:70px;height:34px;border-radius:8px;background:#0A0F19;border:1px solid #24344B;padding:0 10px;font-family:\'IBM Plex Mono\',monospace;font-size:12.5px;color:#C7D2E0"></div>'
    + '<label style="display:flex;gap:8px;align-items:center;font-size:12.5px;cursor:pointer"><input type="checkbox" id="aofTap"' + (st.anchor_tap?' checked':'') + '>🎯 กดตรงที่เจอภาพ (ปุ่มขยับก็กดโดน)</label>'
    + '<button class="in" onclick="flowSaveAnchorOpts()" style="display:flex;align-items:center;justify-content:center;gap:7px;height:40px;border-radius:9px;background:#10B981;color:#04120C;font-size:13px;font-weight:600;cursor:pointer"><i data-lucide="check" width="15" height="15" stroke-width="2.25"></i>บันทึก</button>'
    + '</div>');
}
function toggleRetryFields(){
  const sel = document.querySelector('input[name="aof"]:checked');
  const box = document.getElementById('aofRetryBox');
  if(box) box.style.display = (sel && sel.value === 'retry') ? 'flex' : 'none';
  const note = document.getElementById('aofPauseNote');
  if(note) note.style.display = (sel && sel.value === 'pause') ? 'block' : 'none';
}
async function flowSaveAnchorOpts(){
  const sel = document.querySelector('input[name="aof"]:checked');
  const to = parseFloat((document.getElementById('aofTimeout')||{}).value);
  const isRetry = sel && sel.value === 'retry';
  const target = isRetry ? (document.getElementById('aofTarget')||{}).value : null;
  const limit = isRetry ? (document.getElementById('aofRetryLimit')||{}).value : null;
  if(isRetry && (target === null || target === '')){ notReady('เลือกขั้นเป้าหมายก่อน'); return; }
  FLOW = await PY.flow_set_anchor_opts(SEL_PATH, sel ? sel.value : null, isNaN(to)?null:to,
                                       (document.getElementById('aofTap')||{}).checked, target, limit);
  closeModal();
  renderFlow();
}

// ---------- ไฮไลต์สดตอนรัน ----------
function flowApplyHighlight(progress){
  if(SCRIPT_VIEW !== 'flow') return;
  let np = null;
  if(progress && progress.length){
    const p = progress.find(x => x.path) || progress[0];
    np = (p && p.path) ? p.path : null;
  }
  if(np === FLOW_HL) return;   // ไม่เปลี่ยน → ไม่ต้องวาดใหม่
  FLOW_HL = np;                // null = รันจบ → เคลียร์ไฮไลต์
  renderFlow();
}

// ================= จอที่รอแก้ไข (anchor_on_fail='pause') =================
// เรียนรู้ทีละจอ: รันแล้วไม่เจอตามที่ตั้งไว้ -> จอหยุดค้าง (ไม่รีเซ็ต) -> ผู้ใช้เปิดที่นี่ ดูภาพที่ค้าง
// -> ไปเพิ่มเงื่อนไข/if ในผัง -> กด "รันต่อ" ไปต่อจากจุดเดิมด้วยบัญชี/จอเดิม
let PAUSED_ITEMS = [];
function pathStrToArr(p){
  return String(p||'').split('.').filter(s=>s!=='').map(s => (s==='then'||s==='else') ? s : parseInt(s,10));
}
async function pollPausedList(){
  if(!hasPy()) return;
  const r = await PY.list_paused();
  renderPausedList((r && r.items) || []);
}
function renderPausedList(items){
  PAUSED_ITEMS = items || [];
  const panel = document.getElementById('pausedPanel');
  const box = document.getElementById('pausedList');
  if(!panel || !box) return;
  if(!PAUSED_ITEMS.length){ panel.style.display = 'none'; box.innerHTML = ''; return; }
  panel.style.display = 'flex';
  box.innerHTML = PAUSED_ITEMS.map(it => (
    '<div style="display:flex;gap:12px;align-items:center;border-radius:11px;background:#1A1608;border:1px solid #7A5A1E;padding:11px 13px">'
    + (it.shot ? '<img src="data:image/png;base64,' + it.shot + '" style="width:54px;height:96px;object-fit:cover;border-radius:7px;border:1px solid #7A5A1E;flex:none;cursor:pointer" onclick="previewPausedShot(\'' + it.device + '\')">'
               : '<div style="width:54px;height:96px;border-radius:7px;background:#0A0F19;border:1px solid #7A5A1E;flex:none"></div>')
    + '<div style="flex:1;min-width:0;display:flex;flex-direction:column;gap:3px">'
    +   '<div style="display:flex;align-items:center;gap:8px"><span style="font-weight:600;font-size:13px">จอ ' + esc(it.port) + '</span><span style="font-size:11px;color:#7C8CA3">' + esc(it.ts) + '</span></div>'
    +   '<div style="font-family:\'IBM Plex Mono\',monospace;font-size:11.5px;color:#C7D2E0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">' + esc(it.name || it.email || '-') + '</div>'
    +   '<div style="font-size:12px;color:#FBBF24;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">' + esc(it.desc || 'ไม่เจอภาพตามที่ตั้งไว้') + '</div>'
    + '</div>'
    + '<div style="display:flex;flex-direction:column;gap:6px;flex:none">'
    +   '<button class="in" onclick="jumpToPausedStep(\'' + it.device + '\')" style="display:flex;align-items:center;justify-content:center;gap:6px;height:32px;padding:0 12px;border-radius:8px;background:#0F2F4A;border:1px solid #164E72;color:#7DD3FC;font-size:12px;cursor:pointer"><i data-lucide="wand-2" width="13" height="13" stroke-width="1.9"></i>แก้ไขที่นี่</button>'
    +   '<button class="in" onclick="resumePaused(\'' + it.device + '\')" style="display:flex;align-items:center;justify-content:center;gap:6px;height:32px;padding:0 12px;border-radius:8px;background:' + (it.resuming?'#1B2434':'rgba(16,185,129,.14)') + ';border:1px solid ' + (it.resuming?'#24344B':'rgba(16,185,129,.3)') + ';color:' + (it.resuming?'#7C8CA3':'#6EE7B7') + ';font-size:12px;cursor:pointer" ' + (it.resuming?'disabled':'') + '><i data-lucide="' + (it.resuming?'loader':'play') + '" width="13" height="13" stroke-width="2" ' + (it.resuming?'style="animation:spin 1.4s linear infinite"':'') + '></i>' + (it.resuming?'กำลังรันต่อ…':'รันต่อ') + '</button>'
    + '</div>'
    + '<i data-lucide="x" width="15" height="15" stroke-width="2" style="color:#7A5A1E;cursor:pointer;flex:none" title="ยกเลิกจุดนี้" onclick="dismissPaused(\'' + it.device + '\')"></i>'
    + '</div>'
  )).join('');
  icons();
}
function previewPausedShot(device){
  const it = PAUSED_ITEMS.find(x => x.device === device);
  if(!it || !it.shot) return;
  openModal('จอ ' + it.port + ' — ภาพ ณ ตอนติด', 'image',
    '<img src="data:image/png;base64,' + it.shot + '" style="width:100%;border-radius:10px;border:1px solid #24344B">');
}
async function jumpToPausedStep(device){
  const it = PAUSED_ITEMS.find(x => x.device === device);
  if(!it) return;
  switchPage('script');
  setScriptView('flow');
  await flowSelect(pathStrToArr(it.step_path));
  setTimeout(() => {
    const el = document.querySelector('[data-fpath="' + it.step_path + '"]');
    if(el) el.scrollIntoView({behavior: 'smooth', block: 'center'});
  }, 150);
}
async function resumePaused(device){
  if(!hasPy()) return;
  const r = await PY.resume_paused(device);
  if(r && r.ok){
    if(!RUN_POLL && typeof startRunPoll === 'function') startRunPoll();
    await pollPausedList();
    return;
  }
  // ของเดิมไม่บอกอะไรเลยเมื่อรันต่อไม่ได้ ผู้ใช้เลยเห็นเป็น 'กดแล้วไม่มีอะไรเกิดขึ้น'
  openModal('รันต่อไม่ได้', 'alert-triangle',
    '<div style="font-size:13px;color:#FCA5A5;line-height:1.7">' + esc((r && r.error) || 'ไม่ทราบสาเหตุ') + '</div>'
    + '<div style="margin-top:10px;font-size:11.5px;color:#7C8CA3">ถ้าไม่อยากรันต่อจอนี้แล้ว กดกากบาทที่การ์ดเพื่อเอาออกจากแผงได้</div>');
  await pollPausedList();
}
async function dismissPaused(device){
  if(!hasPy()) return;
  await PY.dismiss_paused(device);
  await pollPausedList();
}
