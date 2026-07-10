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
    ? '<div style="font-size:12px;color:#7C8CA3;margin-bottom:10px">อ่านได้ ' + rows.length + ' รายการ (บันทึกลง diamonds_export.json แล้ว)</div>'
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
  const toReal = ev => { const rc = img.getBoundingClientRect(); const rw = +img.dataset.w || img.naturalWidth, rh = +img.dataset.h || img.naturalHeight;
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
    const rw = +img.dataset.w, rh = +img.dataset.h, rc = img.getBoundingClientRect();
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

// ---- ผังงาน (Flow View) ----
async function openFlowView(){
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
    + '<div style="display:flex;gap:8px"><input id="newSetName" class="in" placeholder="ชื่อชุดคำสั่ง…" style="flex:1;height:38px;border-radius:8px;background:#0A0F19;border:1px solid #24344B;padding:0 12px;font-size:12.5px;color:#C7D2E0"><button class="in" onclick="saveCurrentSet()" style="display:flex;align-items:center;gap:6px;padding:0 14px;height:38px;border-radius:8px;background:#10B981;color:#04120C;font-size:12.5px;font-weight:600;cursor:pointer"><i data-lucide="save" width="14" height="14" stroke-width="2"></i>บันทึกเป็นชุด</button></div></div>');
}
async function saveCurrentSet(){
  const v = (document.getElementById('newSetName') || {}).value || '';
  if(!v.trim()){ notReady('พิมพ์ชื่อชุดก่อน'); return; }
  if(hasPy()){ const r = await PY.save_current_as_set(v); renderManageSets(r.sets || []); }
}
async function delSet(name){ if(hasPy()){ const r = await PY.delete_script_set(name); renderManageSets(r.sets || []); } }

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
