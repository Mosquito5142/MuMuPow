// ==================================================================
//  เครื่องมือ (🟢): modal + inspector + หาพิกัด + ผังงาน + set + ฯลฯ
//  โหลดต่อจาก app.js — ใช้ตัวแปร/ฟังก์ชัน global ร่วมกัน (PY, hasPy, esc, icons…)
// ==================================================================
function openModal(title, icon, html){
  document.getElementById('modalTitle').textContent = title;
  const ic = document.getElementById('modalIcon'); if(ic){ ic.setAttribute('data-lucide', icon || 'wrench'); }
  document.getElementById('modalBody').innerHTML = html;
  document.getElementById('modalWrap').style.display = 'flex';
  icons();
}
function closeModal(){ document.getElementById('modalWrap').style.display = 'none'; }
function needPy(name){ if(!hasPy()){ notReady((name || 'เครื่องมือนี้') + ' (ต้องเปิดผ่าน .exe)'); return false; } return true; }
document.addEventListener('keydown', e => { if(e.key === 'Escape') closeModal(); });

// ---- ปุ่มง่ายๆ (ไม่ต้องมี modal) ----
async function exportProfile(){ if(needPy('Export')) await PY.export_profile(); }
async function importProfile(){ if(needPy('Import')){ await PY.import_profile(); renderSteps(); refresh(); } }
async function setupKeyboard(){ if(needPy('เปิดคีย์บอร์ดไทย')) await PY.setup_adb_keyboard(); }
async function restoreKeyboard(){ if(needPy('คืนคีย์บอร์ด')) await PY.restore_keyboard(); }

function copyText(t){
  try { navigator.clipboard.writeText(t); } catch(_){}
  if(window.onLog) window.onLog({ ts:new Date().toTimeString().slice(0,8), text:'คัดลอก: ' + t, kind:'ok' });
}

// ---- อ่านเพชร → JSON ----
async function readDiamond(){
  if(!needPy('อ่านเพชร')) return;
  openModal('อ่านเพชร', 'gem', '<div style="font-size:12.5px;color:#90A0B7">กำลังอ่านเพชรบนจอที่เลือก…</div>');
  const r = await PY.read_diamond_manual();
  const rows = (r && r.rows) || [];
  const body = rows.length
    ? '<div style="font-size:12px;color:#7C8CA3;margin-bottom:10px">อ่านได้ ' + rows.length + ' รายการ — บันทึกไฟล์ + ส่งเข้าเว็บให้แล้ว (ดูผลส่งที่ล็อก)</div>'
      + '<div style="display:flex;flex-direction:column;gap:6px">'
      + rows.map(x => '<div style="display:flex;gap:10px;align-items:center;padding:8px 11px;border-radius:8px;background:#0A0F19;border:1px solid #1B2434"><i data-lucide="gem" width="14" height="14" style="color:#7DD3FC"></i><span style="flex:1;font-size:12.5px">' + esc(x.name || x.device || '-') + '</span><span style="font-family:\'IBM Plex Mono\',monospace;font-size:13px;color:#6EE7B7">' + esc(String(x.diamonds)) + '</span></div>').join('')
      + '</div>'
    : '<div style="font-size:12.5px;color:#FCA5A5">อ่านเพชรไม่ได้ — ตรวจว่าตั้งพื้นที่ตัวเลขเพชร (diamond_ocr.json) และมี Tesseract แล้ว</div>';
  openModal('อ่านเพชร', 'gem', body);
}

// ---- UI Inspector ----
async function openInspector(){
  if(!needPy('UI Inspector')) return;
  openModal('UI Inspector', 'scan-search', '<div style="font-size:12.5px;color:#90A0B7">กำลังอ่าน element บนหน้าจอ…</div>');
  const r = await PY.inspect_ui();
  const els = (r && r.elements) || [];
  if(!r || !r.ok){ openModal('UI Inspector', 'scan-search', '<div style="font-size:12.5px;color:#FCA5A5">อ่าน UI ไม่ได้ ' + esc((r && r.error) || '') + '</div>'); return; }
  const rows = els.map(e => {
    const q = e.id ? 'id:' + e.id : (e.text || e.desc || '');
    const label = [e.text ? ('text: ' + e.text) : '', e.id ? ('id: ' + e.id) : '', e.desc ? ('desc: ' + e.desc) : ''].filter(Boolean).join('  ·  ') || '(ไม่มีข้อความ)';
    const at = (e.cx != null) ? ('@(' + e.cx + ',' + e.cy + ')') : '';
    return '<div onclick="copyText(\'' + esc(q).replace(/'/g, "\\'") + '\')" title="คลิกเพื่อคัดลอกไปใส่ step กดตามข้อความ" style="display:flex;gap:9px;align-items:center;padding:8px 11px;border-radius:8px;cursor:pointer;background:#0A0F19;border:1px solid #1B2434">'
      + '<span style="flex:1;font-size:12px;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">' + esc(label) + '</span>'
      + (e.clickable ? '<span style="font-size:10px;color:#6EE7B7;flex:none">คลิกได้</span>' : '')
      + '<span style="font-family:\'IBM Plex Mono\',monospace;font-size:11px;color:#5C6B82;flex:none">' + esc(at) + '</span></div>';
  }).join('');
  openModal('UI Inspector · ' + esc(r.device || ''), 'scan-search',
    '<div style="font-size:12px;color:#7C8CA3;margin-bottom:10px">พบ ' + els.length + ' element — คลิกแถวเพื่อคัดลอกข้อความ/id ไปใส่ step “กดตามข้อความ”</div>'
    + '<div style="display:flex;flex-direction:column;gap:5px">' + (rows || '<div style="color:#5C6B82;font-size:12px">ไม่พบ element ที่มีข้อความ/id (น่าจะเป็นหน้าจอเกม → ใช้จับภาพแทน)</div>') + '</div>');
}

// ---- ตัวช่วยหาพิกัด (แคปจอ → ชี้/คลิกอ่านพิกัดจริง) ----
async function openCoordPicker(){
  if(!needPy('ตัวช่วยหาพิกัด')) return;
  openModal('ตัวช่วยหาพิกัด', 'crosshair', '<div style="font-size:12.5px;color:#90A0B7">กำลังแคปหน้าจอ…</div>');
  const r = await PY.screenshot_b64();
  if(!r || !r.ok){ openModal('ตัวช่วยหาพิกัด', 'crosshair', '<div style="font-size:12.5px;color:#FCA5A5">แคปจอไม่ได้ — เลือกจออย่างน้อย 1 เครื่องก่อน</div>'); return; }
  openModal('ตัวช่วยหาพิกัด · ' + esc(r.device || ''), 'crosshair',
    '<div style="font-size:12px;color:#7C8CA3;margin-bottom:8px">ชี้เมาส์บนภาพเพื่ออ่านพิกัด · คลิกเพื่อคัดลอกพิกัดจริง (จอ ' + r.w + '×' + r.h + ')</div>'
    + '<div style="font-family:\'IBM Plex Mono\',monospace;font-size:14px;color:#6EE7B7;margin-bottom:8px">X: <span id="cpX">–</span>&nbsp;&nbsp;&nbsp;Y: <span id="cpY">–</span></div>'
    + '<div style="position:relative;display:inline-block;max-width:100%"><img id="cpImg" src="' + r.img + '" data-w="' + r.w + '" data-h="' + r.h + '" style="max-width:100%;border-radius:10px;border:1px solid #24344B;cursor:crosshair;display:block"></div>');
  const img = document.getElementById('cpImg');
  const toReal = ev => { const rc = img.getBoundingClientRect(); const rw = img.naturalWidth || +img.dataset.w, rh = img.naturalHeight || +img.dataset.h;
    return { x: Math.round((ev.clientX - rc.left) / rc.width * rw), y: Math.round((ev.clientY - rc.top) / rc.height * rh) }; };
  img.addEventListener('mousemove', ev => { const p = toReal(ev); document.getElementById('cpX').textContent = p.x; document.getElementById('cpY').textContent = p.y; });
  img.addEventListener('click', ev => { const p = toReal(ev); copyText(p.x + ',' + p.y); });
}

// ---- ตั้งพื้นที่ชื่อชมรม (ลากกรอบบนภาพ) ----
async function openGuildRegion(){
  if(!needPy('ตั้งพื้นที่ชื่อ')) return;
  openModal('ตั้งพื้นที่คอลัมน์ชื่อ', 'crop', '<div style="font-size:12.5px;color:#90A0B7">กำลังแคปหน้าจอ…</div>');
  const r = await PY.screenshot_b64();
  if(!r || !r.ok){ openModal('ตั้งพื้นที่ชื่อ', 'crop', '<div style="font-size:12.5px;color:#FCA5A5">แคปจอไม่ได้ — เลือกจอก่อน</div>'); return; }
  openModal('ตั้งพื้นที่คอลัมน์ชื่อ · ' + esc(r.device || ''), 'crop',
    '<div style="font-size:12px;color:#7C8CA3;margin-bottom:8px">ลากคลุมเฉพาะคอลัมน์ “ชื่อสมาชิก” แล้วกดบันทึก (จอ ' + r.w + '×' + r.h + ')</div>'
    + '<div id="grInfo" style="font-family:\'IBM Plex Mono\',monospace;font-size:12.5px;color:#6EE7B7;margin-bottom:8px">ยังไม่ได้ลากกรอบ</div>'
    + '<div style="position:relative;display:inline-block;max-width:100%"><img id="grImg" src="' + r.img + '" data-w="' + r.w + '" data-h="' + r.h + '" style="max-width:100%;border-radius:10px;border:1px solid #24344B;cursor:crosshair;display:block;user-select:none">'
    + '<div id="grRect" style="position:absolute;border:2px solid #10B981;background:rgba(16,185,129,.18);display:none;pointer-events:none"></div></div>'
    + '<button class="in" onclick="saveGuildRegion()" style="margin-top:12px;display:flex;align-items:center;justify-content:center;gap:7px;height:40px;border-radius:9px;background:#10B981;color:#04120C;font-size:13px;font-weight:600;cursor:pointer"><i data-lucide="save" width="15" height="15" stroke-width="2"></i>บันทึกพื้นที่นี้</button>');
  icons();
  const img = document.getElementById('grImg'), rect = document.getElementById('grRect');
  let sx, sy, drag = false; window._guildReg = null;
  const rel = ev => { const rc = img.getBoundingClientRect(); return { x: ev.clientX - rc.left, y: ev.clientY - rc.top }; };
  img.addEventListener('mousedown', ev => { ev.preventDefault(); const p = rel(ev); sx = p.x; sy = p.y; drag = true; rect.style.display = 'block'; rect.style.left = sx + 'px'; rect.style.top = sy + 'px'; rect.style.width = '0px'; rect.style.height = '0px'; });
  window.addEventListener('mousemove', ev => { if(!drag) return; const p = rel(ev); const x = Math.min(sx, p.x), y = Math.min(sy, p.y), w = Math.abs(p.x - sx), h = Math.abs(p.y - sy);
    rect.style.left = x + 'px'; rect.style.top = y + 'px'; rect.style.width = w + 'px'; rect.style.height = h + 'px';
    const rw = img.naturalWidth || +img.dataset.w, rh = img.naturalHeight || +img.dataset.h, rc = img.getBoundingClientRect();
    window._guildReg = { x: Math.round(x / rc.width * rw), y: Math.round(y / rc.height * rh), w: Math.round(w / rc.width * rw), h: Math.round(h / rc.height * rh) };
    const g = window._guildReg; document.getElementById('grInfo').textContent = 'กรอบ: x=' + g.x + ' y=' + g.y + ' w=' + g.w + ' h=' + g.h; });
  window.addEventListener('mouseup', () => { drag = false; });
}
async function saveGuildRegion(){
  const g = window._guildReg;
  if(!g || g.w < 5 || g.h < 5){ notReady('ลากกรอบให้ใหญ่พอก่อน'); return; }
  if(hasPy()){ await PY.save_guild_region(g.x, g.y, g.w, g.h); closeModal(); }
}

// ---- ดึงรายชื่อสมาชิกชมรม ----
async function grabGuild(){
  if(!needPy('ดึงรายชื่อ')) return;
  openModal('ดึงรายชื่อสมาชิกชมรม', 'list', '<div style="font-size:12.5px;color:#90A0B7">กำลังเลื่อน + แคป + OCR… (อาจใช้เวลาสักครู่)</div>');
  const r = await PY.grab_guild_members();
  const names = (r && r.names) || [];
  if(!r || !r.ok){ openModal('ดึงรายชื่อ', 'list', '<div style="font-size:12.5px;color:#FCA5A5">ดึงไม่สำเร็จ ' + (r && r.error === 'no_tesseract' ? '(ไม่พบ Tesseract OCR)' : '') + '</div>'); return; }
  openModal('ดึงรายชื่อสมาชิกชมรม', 'list',
    '<div style="font-size:12px;color:#7C8CA3;margin-bottom:8px">OCR ได้ ' + names.length + ' ชื่อ (ตัดซ้ำแล้ว)' + ((r.region_used) ? '' : ' — ยังไม่ได้ตั้งพื้นที่ชื่อ อาจปนเลข') + ' · แก้ไข/คัดลอกได้</div>'
    + '<textarea id="guildNames" class="in" style="width:100%;height:300px;border-radius:9px;background:#0A0F19;border:1px solid #24344B;padding:11px;font-size:12.5px;color:#C7D2E0;line-height:1.7;resize:vertical">' + esc(names.join('\n')) + '</textarea>'
    + '<button class="in" onclick="copyText(document.getElementById(\'guildNames\').value)" style="margin-top:10px;display:flex;align-items:center;justify-content:center;gap:7px;height:38px;border-radius:9px;background:#0F2F4A;border:1px solid #164E72;color:#7DD3FC;font-size:12.5px;cursor:pointer"><i data-lucide="copy" width="14" height="14" stroke-width="1.75"></i>คัดลอกทั้งหมด</button>');
}

// ---- ผังงาน: สลับหน้าสคริปต์เข้าโหมดโฟลว์ (ตัวแก้ไขเต็มรูปแบบใน flow.js) ----
async function openFlowView(){
  if(typeof setScriptView === 'function'){ setScriptView('flow'); return; }
  return openFlowViewModal();
}
async function openFlowViewModal(){
  const s = hasPy() ? await PY.get_steps() : DEMO_STEPS;
  const steps = s.steps || [];
  const nodes = steps.map((st, i) => (
    '<div style="display:flex;flex-direction:column;align-items:center">'
    + '<div style="min-width:220px;max-width:340px;display:flex;gap:10px;align-items:center;padding:11px 14px;border-radius:11px;background:#0A0F19;border:1px solid ' + (st.icon === 'image' ? 'rgba(251,191,36,.4)' : '#24344B') + '">'
    + '<span style="font-family:\'IBM Plex Mono\',monospace;font-size:11px;color:#5C6B82">' + st.no + '</span>'
    + '<i data-lucide="' + st.icon + '" width="15" height="15" stroke-width="1.9" style="color:' + (st.icon === 'image' ? '#FBBF24' : '#7DD3FC') + ';flex:none"></i>'
    + '<span style="font-size:12.5px;font-weight:500;flex:none">' + esc(st.type) + '</span>'
    + '<span style="font-family:\'IBM Plex Mono\',monospace;font-size:11px;color:#90A0B7;flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">' + esc(st.detail) + '</span></div>'
    + (i < steps.length - 1 ? '<div style="width:2px;height:16px;background:#24344B"></div><i data-lucide="chevron-down" width="15" height="15" style="color:#3A4A63;margin:-4px 0"></i><div style="width:2px;height:16px;background:#24344B"></div>' : '')
    + '</div>'
  )).join('');
  openModal('ผังงานสคริปต์' + (s.name && s.name !== '—' ? ' · ' + esc(s.name) : ''), 'git-fork',
    steps.length ? '<div style="display:flex;flex-direction:column;align-items:center;gap:0">' + nodes + '</div>'
                 : '<div style="font-size:12.5px;color:#5C6B82">ยังไม่มีขั้นตอนในสคริปต์นี้</div>');
}

// ---- จัดการชุดคำสั่งย่อย (Script Sets) ----
async function openManageSets(){
  if(!needPy('จัดการ Sets')) return;
  const r = await PY.list_script_sets();
  renderManageSets(r.sets || []);
}
function renderManageSets(sets){
  const list = sets.length ? sets.map(s => (
    '<div style="display:flex;gap:10px;align-items:center;padding:9px 12px;border-radius:8px;background:#0A0F19;border:1px solid #1B2434">'
    + '<i data-lucide="layers" width="15" height="15" style="color:#7DD3FC;flex:none"></i>'
    + '<span style="flex:1;font-size:12.5px">' + esc(s.name) + '</span>'
    + '<span style="font-size:11px;color:#5C6B82">' + s.count + ' ขั้น</span>'
    + '<button class="in" onclick="delSet(\'' + esc(s.name).replace(/'/g, "\\'") + '\')" style="width:28px;height:28px;border-radius:7px;background:#2A1113;border:1px solid #7F1D1D;color:#FCA5A5;cursor:pointer;display:flex;align-items:center;justify-content:center"><i data-lucide="trash-2" width="13" height="13"></i></button></div>'
  )).join('') : '<div style="font-size:12px;color:#5C6B82">ยังไม่มีชุดคำสั่งย่อย</div>';
  openModal('จัดการชุดคำสั่งย่อย (Script Sets)', 'layers',
    '<div style="font-size:12px;color:#7C8CA3;margin-bottom:8px">ชุดคำสั่งย่อยใช้ผ่าน step “ใช้ชุดคำสั่ง (run_set)”</div>'
    + '<div style="display:flex;flex-direction:column;gap:6px;margin-bottom:16px">' + list + '</div>'
    + '<div style="border-top:1px solid #1B2434;padding-top:14px"><div style="font-size:12px;color:#90A0B7;margin-bottom:7px">บันทึกขั้นตอนในสคริปต์ปัจจุบันเป็นชุดใหม่:</div>'
    + '<div style="display:flex;gap:8px"><input id="newSetName" class="in" placeholder="ชื่อชุดคำสั่ง…" style="flex:1;height:38px;border-radius:8px;background:#0A0F19;border:1px solid #24344B;padding:0 12px;font-size:12.5px;color:#C7D2E0"><button class="in" onclick="saveCurrentSet()" style="display:flex;align-items:center;gap:6px;padding:0 14px;height:38px;border-radius:8px;background:#10B981;color:#04120C;font-size:12.5px;font-weight:600;cursor:pointer"><i data-lucide="save" width="14" height="14" stroke-width="2"></i>บันทึกเป็นชุด</button></div></div>'
    + '<div style="border-top:1px solid #1B2434;padding-top:14px;margin-top:14px">'
    +   '<div style="font-size:12px;color:#90A0B7;margin-bottom:7px">✂️ ตัดช่วงขั้นในสคริปต์นี้ออกไปทำเป็น “บล็อกกันพัง” (แบ่งสคริปต์ยาว ๆ ทีหลังได้):</div>'
    +   '<div style="display:flex;gap:8px;margin-bottom:8px"><input id="exFrom" class="in" placeholder="ขั้นเริ่ม" style="width:90px;height:36px;border-radius:8px;background:#0A0F19;border:1px solid #24344B;padding:0 10px;font-family:\'IBM Plex Mono\',monospace;font-size:12.5px;color:#C7D2E0"><span style="align-self:center;color:#5C6B82">ถึง</span><input id="exTo" class="in" placeholder="ขั้นจบ" style="width:90px;height:36px;border-radius:8px;background:#0A0F19;border:1px solid #24344B;padding:0 10px;font-family:\'IBM Plex Mono\',monospace;font-size:12.5px;color:#C7D2E0"><input id="exName" class="in" placeholder="ชื่อบล็อกใหม่…" style="flex:1;height:36px;border-radius:8px;background:#0A0F19;border:1px solid #24344B;padding:0 12px;font-size:12.5px;color:#C7D2E0"></div>'
    +   '<label style="display:flex;gap:8px;align-items:center;font-size:12px;color:#C7D2E0;cursor:pointer;margin-bottom:8px"><input type="checkbox" id="exBlock" checked onchange="document.getElementById(\'exBlockOpts\').style.display=this.checked?\'flex\':\'none\'">ทำเป็นบล็อกกันพัง (ถ้าพัง กลับหน้าแรกแล้วลองใหม่)</label>'
    +   '<div id="exBlockOpts" style="display:flex;gap:8px;margin-bottom:8px"><input id="exHome" class="in" placeholder="ชุดกลับหน้าแรก (เช่น กลับหน้าแรก)" value="กลับหน้าแรก" style="flex:1;height:36px;border-radius:8px;background:#0E1420;border:1px solid #24344B;padding:0 11px;font-size:12.5px;color:#C7D2E0"><input id="exRetries" class="in" placeholder="รอบ (3)" style="width:80px;height:36px;border-radius:8px;background:#0E1420;border:1px solid #24344B;padding:0 11px;font-family:\'IBM Plex Mono\',monospace;font-size:12.5px;color:#C7D2E0"></div>'
    +   '<button class="in" onclick="extractRangeToBlock()" style="display:flex;align-items:center;justify-content:center;gap:6px;width:100%;height:38px;border-radius:8px;background:#0F2F4A;border:1px solid #164E72;color:#7DD3FC;font-size:12.5px;font-weight:600;cursor:pointer"><i data-lucide="scissors" width="14" height="14" stroke-width="2"></i>ตัดช่วงนี้เป็นบล็อก</button>'
    + '</div>');
}
async function saveCurrentSet(){
  const v = (document.getElementById('newSetName') || {}).value || '';
  if(!v.trim()){ notReady('พิมพ์ชื่อชุดก่อน'); return; }
  if(hasPy()){ const r = await PY.save_current_as_set(v); renderManageSets(r.sets || []); }
}
async function delSet(name){ if(hasPy()){ const r = await PY.delete_script_set(name); renderManageSets(r.sets || []); } }
async function extractRangeToBlock(){
  const g=id=>(document.getElementById(id)||{}).value;
  const from=g('exFrom'), to=g('exTo'), name=(g('exName')||'').trim();
  if(!from||!to){ notReady('ใส่ช่วงขั้น เริ่ม–จบ ก่อน'); return; }
  if(!name){ notReady('ตั้งชื่อบล็อกใหม่ก่อน'); return; }
  const block=(document.getElementById('exBlock')||{}).checked;
  if(hasPy()){
    await PY.extract_range_to_block(from, to, name, block?g('exHome'):'', block?g('exRetries'):'', block);
    closeModal(); renderSteps();
  }
}

// ---- สร้างเร็ว (พรีเซ็ตพิกัด → เพิ่มเป็น step แตะ) ----
async function openQuickBuilder(){
  const r = hasPy() ? await PY.get_presets() : { presets: [] };
  const ps = r.presets || [];
  const items = ps.length ? ps.map(p => (
    '<button class="in" onclick="quickAdd(\'' + esc(p.name).replace(/'/g, "\\'") + '\')" style="display:flex;gap:10px;align-items:center;padding:10px 12px;border-radius:8px;background:#0A0F19;border:1px solid #1B2434;color:#C7D2E0;font-size:12.5px;cursor:pointer;text-align:left;width:100%">'
    + '<i data-lucide="plus" width="14" height="14" style="color:#6EE7B7;flex:none"></i>'
    + '<span style="flex:1">' + esc(p.name) + '</span>'
    + '<span style="font-family:\'IBM Plex Mono\',monospace;font-size:11px;color:#5C6B82">' + Math.round(p.x) + ',' + Math.round(p.y) + '</span></button>'
  )).join('') : '<div style="font-size:12px;color:#5C6B82">ไม่มีพรีเซ็ตใน presets.json</div>';
  openModal('สร้างเร็ว · พรีเซ็ตพิกัด', 'zap',
    '<div style="font-size:12px;color:#7C8CA3;margin-bottom:10px">คลิกพรีเซ็ตเพื่อเพิ่มเป็นขั้น “แตะ” ต่อท้ายสคริปต์ทันที</div>'
    + '<div style="display:flex;flex-direction:column;gap:6px">' + items + '</div>');
}
async function quickAdd(name){ if(hasPy()){ await PY.quick_add(name); renderSteps(); } }

// ==================================================================
//  ระบบเพิ่มเติม: เพชร / รายงานจุดที่ติด / พรีเซ็ต / รีเซ็ตเกม
// ==================================================================

// ---- ตัวลากกรอบอเนกประสงค์ (ใช้ซ้ำ: พื้นที่เพชร/ชื่อในเกม) ----
async function pickRegionGeneric(title, hint, onSave){
  const shot = await PY.screenshot_b64();
  if(!shot || !shot.ok){ openModal(title,'crop','<div style="font-size:12.5px;color:#FCA5A5">แคปจอไม่ได้ — เลือกจออย่างน้อย 1 เครื่องก่อน</div>'); return; }
  window._prOnSave = onSave;
  openModal(title + ' · ' + esc(shot.device||''), 'crop',
    '<div style="font-size:12px;color:#7C8CA3;margin-bottom:8px">' + hint + ' (จอ ' + shot.w + '×' + shot.h + ')</div>'
    + '<div id="prInfo" style="font-family:\'IBM Plex Mono\',monospace;font-size:12px;color:#6EE7B7;margin-bottom:8px">ยังไม่ได้ลากกรอบ</div>'
    + '<div style="position:relative;display:inline-block;max-width:100%"><img id="prImg" src="' + shot.img + '" data-w="' + shot.w + '" data-h="' + shot.h + '" style="max-width:100%;border-radius:10px;border:1px solid #24344B;cursor:crosshair;display:block;user-select:none">'
    + '<div id="prRect" style="position:absolute;border:2px solid #10B981;background:rgba(16,185,129,.18);display:none;pointer-events:none"></div></div>'
    + '<button class="in" onclick="prSave()" style="margin-top:12px;display:flex;align-items:center;justify-content:center;gap:7px;height:40px;border-radius:9px;background:#10B981;color:#04120C;font-size:13px;font-weight:600;cursor:pointer"><i data-lucide="save" width="15" height="15" stroke-width="2"></i>บันทึกพื้นที่นี้</button>');
  icons();
  const img = document.getElementById('prImg'), rect = document.getElementById('prRect');
  let sx, sy, drag = false; window._prReg = null;
  const rel = ev => { const rc = img.getBoundingClientRect(); return { x: ev.clientX-rc.left, y: ev.clientY-rc.top }; };
  img.addEventListener('mousedown', ev => { ev.preventDefault(); const p = rel(ev); sx=p.x; sy=p.y; drag=true;
    rect.style.display='block'; rect.style.left=sx+'px'; rect.style.top=sy+'px'; rect.style.width='0'; rect.style.height='0'; });
  window.addEventListener('mousemove', ev => { if(!drag) return; const p = rel(ev);
    const x=Math.min(sx,p.x), y=Math.min(sy,p.y), w=Math.abs(p.x-sx), h=Math.abs(p.y-sy);
    rect.style.left=x+'px'; rect.style.top=y+'px'; rect.style.width=w+'px'; rect.style.height=h+'px';
    const rc = img.getBoundingClientRect();
    const rw = img.naturalWidth || +img.dataset.w, rh = img.naturalHeight || +img.dataset.h;
    window._prReg = { x:Math.round(x/rc.width*rw), y:Math.round(y/rc.height*rh),
                      w:Math.round(w/rc.width*rw), h:Math.round(h/rc.height*rh) };
    const g = window._prReg;
    document.getElementById('prInfo').textContent = 'กรอบ: x='+g.x+' y='+g.y+' กว้าง='+g.w+' สูง='+g.h; });
  window.addEventListener('mouseup', () => { drag=false; });
}
async function prSave(){
  const g = window._prReg;
  if(!g || g.w<4 || g.h<4){ document.getElementById('prInfo').textContent='⚠ ลากกรอบก่อน'; return; }
  if(window._prOnSave) await window._prOnSave(g);
  closeModal();
}

// ---- ระบบเพชร: ตั้งพื้นที่ + เว็บ ----
async function openDiamondTools(){
  if(!needPy('ระบบเพชร')) return;
  const s = await PY.get_diamond_settings();
  const reg = s.region||{};
  openModal('ตั้งค่าระบบอ่านเพชร','gem',
    '<div style="display:flex;flex-direction:column;gap:12px">'
    + '<div style="display:flex;gap:9px;align-items:center;padding:10px 12px;border-radius:9px;background:#0A0F19;border:1px solid #1B2434">'
    +   '<span style="flex:1;font-size:12.5px">พื้นที่ตัวเลขเพชร: <span style="font-family:\'IBM Plex Mono\',monospace;color:#7DD3FC">'+(reg.w?('x='+reg.x+' y='+reg.y+' '+reg.w+'×'+reg.h):'ยังไม่ตั้ง ⚠')+'</span></span>'
    +   '<button class="in" onclick="pickDiamondRegion()" style="padding:7px 12px;border-radius:8px;background:#0F2F4A;border:1px solid #164E72;color:#7DD3FC;font-size:12px;cursor:pointer">ลากกรอบใหม่</button></div>'
    + '<div style="border-top:1px solid #1B2434;padding-top:12px;display:flex;flex-direction:column;gap:9px">'
    +   '<div style="font-size:12px;color:#90A0B7">เว็บ Save Web Game (ส่งเพชรขึ้นเว็บอัตโนมัติหลังรัน):</div>'
    +   '<div style="display:flex;gap:8px"><input id="dmWebUrl" class="in" value="'+esc(s.web_base_url||'')+'" placeholder="https://your-app.vercel.app" style="flex:1;height:36px;border-radius:8px;background:#0A0F19;border:1px solid #24344B;padding:0 11px;font-family:\'IBM Plex Mono\',monospace;font-size:12px;color:#C7D2E0">'
    +   '<button class="in" onclick="PY.save_diamond_opts(document.getElementById(\'dmWebUrl\').value,null)" style="padding:0 13px;height:36px;border-radius:8px;background:#121A28;border:1px solid #24344B;color:#C7D2E0;font-size:12px;cursor:pointer">บันทึก URL</button></div>'
    +   '<div style="display:flex;gap:8px">'
    +   '<button class="in" onclick="matchWebNow()" style="flex:1;display:flex;align-items:center;justify-content:center;gap:6px;height:38px;border-radius:9px;border:1px solid #24344B;color:#C7D2E0;font-size:12px;cursor:pointer"><i data-lucide="link" width="13" height="13"></i>จับคู่ชื่อกับเว็บ</button>'
    +   '<button class="in" onclick="pushWebNow()" style="flex:1;display:flex;align-items:center;justify-content:center;gap:6px;height:38px;border-radius:9px;background:#0F2F4A;border:1px solid #164E72;color:#7DD3FC;font-size:12px;cursor:pointer"><i data-lucide="upload-cloud" width="13" height="13"></i>ส่งเพชรขึ้นเว็บตอนนี้</button></div>'
    + '</div></div>');
}
async function pickDiamondRegion(){
  await pickRegionGeneric('ตั้งพื้นที่ตัวเลขเพชร', 'ลากกรอบคลุมเฉพาะตัวเลขจำนวนเพชร',
    async g => { await PY.save_diamond_region(g.x, g.y, g.w, g.h); openDiamondTools(); });
}
async function matchWebNow(){ const r = await PY.match_web_accounts(); if(r) notReady2('จับคู่ได้ '+(r.matched||0)+' รหัส'); }
async function pushWebNow(){ const r = await PY.push_diamonds_web(); if(r&&r.ok) notReady2('ส่งสำเร็จ '+r.sent+' · พลาด '+r.failed); }
function notReady2(msg){ if(window.onLog) window.onLog({ts:new Date().toTimeString().slice(0,8),text:msg,kind:'ok'}); }

// ---- รายงานจุดที่ติด ----
async function openErrorReports(){
  if(!needPy('รายงานจุดที่ติด')) return;
  const r = await PY.list_error_reports(30);
  const rows = (r.reports||[]).map((x,i)=>(
    '<div onclick="showErrorImage('+i+')" style="display:flex;gap:9px;align-items:center;padding:9px 11px;border-radius:8px;background:#0A0F19;border:1px solid #1B2434;cursor:pointer">'
    +'<i data-lucide="image" width="14" height="14" style="color:#F87171;flex:none"></i>'
    +'<div style="flex:1;min-width:0"><div style="font-size:12px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">'+esc(x.name||x.email||'-')+' · ขั้น '+esc(String(x.step_path!=null?x.step_path:(x.step||'')))+' '+esc(x.step_desc||'')+'</div>'
    +'<div style="font-size:10.5px;color:#7C8CA3">'+esc(x.time||'')+' · '+esc(x.device||'')+' · '+esc(x.reason||'')+'</div></div></div>'
  )).join('');
  window._errReports = r.reports||[];
  openModal('รายงานจุดที่ติด ('+(r.reports||[]).length+' ล่าสุด)','file-warning',
    '<div style="display:flex;gap:8px;margin-bottom:10px"><button class="in" onclick="PY.open_error_folder()" style="display:flex;align-items:center;gap:6px;padding:7px 12px;border-radius:8px;background:#121A28;border:1px solid #24344B;color:#C7D2E0;font-size:12px;cursor:pointer"><i data-lucide="folder-open" width="13" height="13"></i>เปิดโฟลเดอร์</button></div>'
    +'<div style="display:flex;flex-direction:column;gap:5px">'+(rows||'<div style="font-size:12px;color:#5C6B82">ยังไม่มีรายงาน — จะบันทึกอัตโนมัติเมื่อบัญชีติดปัญหาตอนรัน</div>')+'</div>'
    +'<div id="errImgBox" style="margin-top:12px"></div>');
}
async function showErrorImage(i){
  const rep = (window._errReports||[])[i];
  if(!rep || !rep.image) return;
  const r = await PY.error_image_b64(rep.image);
  const box = document.getElementById('errImgBox');
  if(box) box.innerHTML = r&&r.ok ? '<img src="'+r.img+'" style="max-width:100%;border-radius:10px;border:1px solid #24344B">'
                                  : '<div style="font-size:12px;color:#FCA5A5">เปิดภาพไม่ได้ (ไฟล์อาจถูกลบ)</div>';
}

// ---- จัดการพรีเซ็ตพิกัด ----
async function openPresetManager(){
  if(!needPy('พรีเซ็ตพิกัด')) return;
  const r = await PY.get_presets();
  renderPresetManager(r.presets||[]);
}
function renderPresetManager(ps){
  const rows = ps.length ? ps.map(p=>(
    '<div style="display:flex;gap:9px;align-items:center;padding:8px 11px;border-radius:8px;background:#0A0F19;border:1px solid #1B2434">'
    +'<i data-lucide="map-pin" width="13" height="13" style="color:#7DD3FC;flex:none"></i>'
    +'<span style="flex:1;font-size:12.5px">'+esc(p.name)+'</span>'
    +'<span style="font-family:\'IBM Plex Mono\',monospace;font-size:11px;color:#5C6B82">'+Math.round(p.x)+','+Math.round(p.y)+'</span>'
    +'<button class="in" onclick="delPresetNow(\''+esc(p.name).replace(/'/g,"\\'")+'\')" style="width:26px;height:26px;border-radius:6px;background:#2A1113;border:1px solid #7F1D1D;color:#FCA5A5;cursor:pointer;display:flex;align-items:center;justify-content:center"><i data-lucide="trash-2" width="12" height="12"></i></button></div>'
  )).join('') : '<div style="font-size:12px;color:#5C6B82">ยังไม่มีพรีเซ็ต</div>';
  openModal('จัดการพรีเซ็ตพิกัด','map-pin',
    '<div style="display:flex;flex-direction:column;gap:5px;margin-bottom:14px">'+rows+'</div>'
    +'<div style="border-top:1px solid #1B2434;padding-top:12px;display:flex;flex-direction:column;gap:8px">'
    +'<div style="font-size:12px;color:#90A0B7">เพิ่มพรีเซ็ตใหม่จากภาพจอ: ตั้งชื่อก่อน แล้วคลิกจุดบนภาพ</div>'
    +'<div style="display:flex;gap:8px"><input id="npName" class="in" placeholder="ชื่อพรีเซ็ต เช่น ปุ่มยืนยัน" style="flex:1;height:36px;border-radius:8px;background:#0A0F19;border:1px solid #24344B;padding:0 11px;font-size:12.5px;color:#C7D2E0">'
    +'<button class="in" onclick="addPresetFromShot()" style="display:flex;align-items:center;gap:6px;padding:0 13px;height:36px;border-radius:8px;background:#10B981;color:#04120C;font-size:12px;font-weight:600;cursor:pointer"><i data-lucide="crosshair" width="13" height="13" stroke-width="2"></i>เลือกจุดจากภาพจอ</button></div></div>');
}
async function delPresetNow(name){ const r = await PY.delete_preset(name); renderPresetManager(r.presets||[]); }
async function addPresetFromShot(){
  const name = ((document.getElementById('npName')||{}).value||'').trim();
  if(!name){ notReady('ตั้งชื่อพรีเซ็ตก่อน'); return; }
  const shot = await PY.screenshot_b64();
  if(!shot || !shot.ok){ notReady('แคปจอไม่ได้ — เลือกจอก่อน'); return; }
  openModal('คลิกจุดที่จะบันทึกเป็น "'+esc(name)+'"','crosshair',
    '<div style="font-size:12px;color:#7C8CA3;margin-bottom:8px">คลิกตำแหน่งบนภาพ (จอ '+shot.w+'×'+shot.h+')</div>'
    +'<div style="position:relative;display:inline-block;max-width:100%"><img id="npImg" src="'+shot.img+'" data-w="'+shot.w+'" data-h="'+shot.h+'" style="max-width:100%;border-radius:10px;border:1px solid #24344B;cursor:crosshair;display:block"></div>');
  const img = document.getElementById('npImg');
  img.addEventListener('click', async ev => {
    const rc = img.getBoundingClientRect();
    const rw = img.naturalWidth || +img.dataset.w, rh = img.naturalHeight || +img.dataset.h;
    const x = (ev.clientX-rc.left)/rc.width*rw;
    const y = (ev.clientY-rc.top)/rc.height*rh;
    const r = await PY.add_preset(name, x, y);
    renderPresetManager(r.presets||[]);
  });
}

// ---- คอนโซล log เต็ม (คลิกจากแถบล่าง) — ดูทั้งหมด + คัดลอกส่งได้ ----
const LOG_COLOR = { ok:'#6EE7B7', warn:'#FBBF24', err:'#F87171', info:'#90A0B7' };
let LOG_POLL = null;
async function openLogConsole(){
  if(!hasPy()){
    openModal('คอนโซลบันทึกการทำงาน','terminal',
      '<div style="font-size:12.5px;color:#5C6B82">(พรีวิวเบราว์เซอร์ — เปิดผ่าน .exe ถึงจะมี log จริง)</div>');
    return;
  }
  openModal('คอนโซลบันทึกการทำงาน','terminal',
    '<div style="display:flex;gap:8px;margin-bottom:10px">'
    + '<button class="in" onclick="copyAllLogs()" style="display:flex;align-items:center;gap:6px;padding:7px 13px;border-radius:8px;background:#0F2F4A;border:1px solid #164E72;color:#7DD3FC;font-size:12px;cursor:pointer"><i data-lucide="copy" width="13" height="13" stroke-width="1.75"></i>คัดลอกทั้งหมด</button>'
    + '<span id="logCount" style="font-size:11.5px;color:#5C6B82;align-self:center"></span>'
    + '<span style="flex:1"></span>'
    + '<label style="display:flex;gap:6px;align-items:center;font-size:11.5px;color:#90A0B7;cursor:pointer"><input type="checkbox" id="logFollow" checked>เลื่อนตามอัตโนมัติ</label></div>'
    + '<div id="logFull" class="sc" style="height:380px;overflow-y:auto;border-radius:9px;background:#060A12;border:1px solid #1B2434;padding:10px;font-family:\'IBM Plex Mono\',monospace;font-size:11.5px;line-height:1.75;user-select:text"></div>');
  await refreshLogConsole();
  // อัปเดตสดทุกวิ ระหว่างโมดัลเปิด (หยุดเองเมื่อปิด)
  if(LOG_POLL) clearInterval(LOG_POLL);
  LOG_POLL = setInterval(async () => {
    if(document.getElementById('modalWrap').style.display !== 'flex' || !document.getElementById('logFull')){
      clearInterval(LOG_POLL); LOG_POLL = null; return;
    }
    await refreshLogConsole();
  }, 1000);
}
async function refreshLogConsole(){
  const r = await PY.get_logs();
  const box = document.getElementById('logFull');
  if(!box) return;
  const logs = (r && r.logs) || [];
  window._allLogs = logs;
  box.innerHTML = logs.map(e =>
    '<div><span style="color:#4A5A72">[' + esc(e.ts||'') + ']</span> <span style="color:' + (LOG_COLOR[e.kind]||LOG_COLOR.info) + '">' + esc(e.text||'') + '</span></div>'
  ).join('') || '<div style="color:#5C6B82">— ยังไม่มีบันทึก —</div>';
  const cnt = document.getElementById('logCount');
  if(cnt) cnt.textContent = logs.length + ' บรรทัด';
  const follow = document.getElementById('logFollow');
  if(!follow || follow.checked) box.scrollTop = box.scrollHeight;
}
function copyAllLogs(){
  const logs = window._allLogs || [];
  const txt = logs.map(e => '[' + (e.ts||'') + '] ' + (e.text||'')).join('\n');
  try { navigator.clipboard.writeText(txt); } catch(_){}
  if(window.onLog) window.onLog({ts:new Date().toTimeString().slice(0,8),
    text:'คัดลอก log ' + logs.length + ' บรรทัดแล้ว — วางส่งได้เลย', kind:'ok'});
}

// ---- ตั้งค่ารีเซ็ตเกม (การ์ดในหน้าตั้งค่า) ----
async function loadResetCfg(){
  if(!hasPy()) return;
  const s = await PY.get_reset_settings();
  const g=id=>document.getElementById(id);
  if(g('rstEnabled')) g('rstEnabled').checked = !!s.enabled;
  if(g('rstPackage')) g('rstPackage').value = s.package||'';
  if(g('rstBootWait')) g('rstBootWait').value = s.boot_wait;
}
async function saveResetCfg(){
  if(!needPy('รีเซ็ตเกม')) return;
  const g=id=>(document.getElementById(id)||{});
  await PY.save_reset_settings(g('rstEnabled').checked, g('rstPackage').value, g('rstBootWait').value);
}

// ---- นำเข้าบัญชีแบบกลุ่ม (วางหลายบรรทัดทีเดียว) ----
function openBatchImport(){
  if(!needPy('นำเข้าแบบกลุ่ม')) return;
  openModal('นำเข้าบัญชีแบบกลุ่ม (Batch Import)', 'clipboard-paste',
    '<div style="font-size:12px;color:#7C8CA3;margin-bottom:10px;line-height:1.6">วางข้อมูลแยกแต่ละบรรทัด คั่นด้วย <code>|</code> <code>,</code> <code>;</code> หรือ TAB<br>รูปแบบ: <b>อีเมล|รหัสผ่าน</b> (ใส่ refresh_token/client_id ต่อท้ายได้ ระบบแยกให้เอง)</div>'
    + '<textarea id="biText" class="in" placeholder="player1@mail.com|pass1234&#10;player2@mail.com,pass5678" style="width:100%;height:220px;border-radius:9px;background:#0A0F19;border:1px solid #24344B;padding:11px;font-family:\'IBM Plex Mono\',monospace;font-size:12px;color:#C7D2E0;line-height:1.7;resize:vertical"></textarea>'
    + '<div style="display:flex;gap:10px;align-items:center;margin-top:10px"><span style="font-size:11.5px;color:#90A0B7">กลุ่มบัญชีปลายทาง</span><input id="biGroup" class="in" value="ทั่วไป" style="flex:1;height:36px;border-radius:8px;background:#0A0F19;border:1px solid #24344B;padding:0 11px;font-size:12.5px;color:#C7D2E0"></div>'
    + '<button class="in" onclick="doBatchImport()" style="margin-top:14px;width:100%;display:flex;align-items:center;justify-content:center;gap:7px;height:42px;border-radius:10px;background:#10B981;color:#04120C;font-size:13px;font-weight:600;cursor:pointer"><i data-lucide="upload" width="15" height="15" stroke-width="2"></i>นำเข้า</button>');
}
async function doBatchImport(){
  const text = (document.getElementById('biText')||{}).value || '';
  const group = (document.getElementById('biGroup')||{}).value || 'ทั่วไป';
  if(!text.trim()){ notReady('วางข้อมูลบัญชีก่อน'); return; }
  const r = await PY.batch_import_accounts(text, group);
  if(r){
    closeModal();
    if(typeof renderAccounts === 'function') renderAccounts();
    window.onLog && window.onLog({ts:new Date().toTimeString().slice(0,8),
      text:'นำเข้า '+r.imported+' บัญชี · ซ้ำ '+r.duplicate+' · ไม่ถูกต้อง '+r.invalid,
      kind: r.imported ? 'ok' : 'warn'});
  }
}

// ---- เลือกเฉพาะบัญชีจากรายชื่อที่วาง (เช่น คัดลอกจากหน้า "ยังไม่ฟาม" ของเว็บ Save Web Game) ----
function openSelectByPaste(){
  if(!needPy('เลือกเฉพาะจากรายชื่อ')) return;
  openModal('เลือกเฉพาะจากรายชื่อ (วางจากเว็บฟาม)', 'target',
    '<div style="font-size:12px;color:#7C8CA3;margin-bottom:10px;line-height:1.6">วางข้อมูลจากปุ่ม 📋 ในหน้า <b>"ฟามรหัส"</b> ของเว็บ Save Web Game (กด Ctrl+V ได้เลย)<br>ระบบจะจับคู่ด้วย <b>id ก่อนเสมอ</b> (แม่นสุด) แล้วค่อย fallback ไปเทียบชื่อถ้าบัญชียังไม่เคย import id — <b>ติ๊กเฉพาะที่ตรง ถอนติ๊กที่เหลือทั้งหมด</b> ให้อัตโนมัติ (พิมพ์ชื่อเปล่าๆ เองทีละบรรทัดก็ยังใช้ได้เหมือนเดิม)</div>'
    + '<textarea id="sbpText" class="in" placeholder="uuid-xxxx|thanapon_017&#10;uuid-yyyy|somchai_099&#10;... (หรือพิมพ์แค่ชื่อก็ได้)" style="width:100%;height:220px;border-radius:9px;background:#0A0F19;border:1px solid #24344B;padding:11px;font-family:\'IBM Plex Mono\',monospace;font-size:12px;color:#C7D2E0;line-height:1.7;resize:vertical"></textarea>'
    + '<button class="in" onclick="doSelectByPaste()" style="margin-top:14px;width:100%;display:flex;align-items:center;justify-content:center;gap:7px;height:42px;border-radius:10px;background:#10B981;color:#04120C;font-size:13px;font-weight:600;cursor:pointer"><i data-lucide="target" width="15" height="15" stroke-width="2"></i>ติ๊กเฉพาะที่ตรง</button>');
}
async function doSelectByPaste(){
  const text = (document.getElementById('sbpText')||{}).value || '';
  if(!text.trim()){ notReady('วางรายชื่อก่อน'); return; }
  const r = await PY.select_by_pasted_names(text);
  if(r && r.ok){
    if(typeof renderAccounts === 'function') renderAccounts();
    const unmatchedNote = (r.unmatched && r.unmatched.length)
      ? ' — หาไม่เจอ '+r.unmatched.length+' ชื่อ: '+r.unmatched.slice(0,5).join(', ')+(r.unmatched.length>5?'…':'')
      : '';
    if(!r.unmatched || !r.unmatched.length) closeModal();
    else {
      // เจอบางชื่อไม่ตรง — โชว์รายชื่อที่หาไม่เจอไว้ในโมดัลเดิม ไม่ปิดทันทีให้แก้ก่อนได้
      const box = document.getElementById('modalBody');
      if(box) box.insertAdjacentHTML('beforeend',
        '<div style="margin-top:12px;padding:10px 12px;border-radius:8px;background:#2E1010;border:1px solid #7F1D1D;font-size:12px;color:#FCA5A5">หาไม่เจอ '+r.unmatched.length+' ชื่อ (สะกดต่างจากในระบบ หรือยังไม่มีบัญชีนี้):<br>'+esc(r.unmatched.join(', '))+'</div>');
    }
    window.onLog && window.onLog({ts:new Date().toTimeString().slice(0,8),
      text:'เลือกจากรายชื่อ: ติ๊กแล้ว '+r.matched+'/'+r.total+' รหัส'+unmatchedNote,
      kind: r.unmatched && r.unmatched.length ? 'warn' : 'ok'});
  }
}
