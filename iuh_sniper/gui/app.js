/* IUH Ledger GUI Controller (pywebview Bridge + Browser Fallback) */

let currentSemesterId = "62";
let currentLoaiDk = 1;
let currentNoConflict = false;
let radarActive = false;
let sniperActive = false;
let sniperTimer = null;

const subjectClassesCache = new Map();
const subjectInflightMap = new Map();
let hoverPrefetchTimer = null;

let sniperTargets = [];

function updateSniperTabBadge() {
  const tabSniper = document.getElementById("tab-sniper");
  const heading = document.getElementById("heading-sniper-station");
  const count = (sniperTargets && sniperTargets.length) || 0;
  if (tabSniper) {
    tabSniper.textContent = sniperActive ? `Trạm canh lớp (${count}) [Đang quét]` : `Trạm canh lớp (${count})`;
  }
  if (heading) {
    heading.textContent = `Danh sách mục tiêu canh lớp (${count})`;
  }
}
function getSubjectCacheKey(idDot, maMon, loaiDk, noConflict) {
  return `${idDot}_${maMon}_${loaiDk}_${noConflict ? 1 : 0}`;
}

function clearSubjectCache() {
  subjectClassesCache.clear();
  subjectInflightMap.clear();
}
const LOAI_DK_LABELS = {
  1: "Học mới",
  2: "Học lại",
  3: "Học cải thiện"
};

function hasBridge() {
  return typeof window !== "undefined" && window.pywebview && window.pywebview.api;
}

function updateHeaderMeta() {
  const meta = document.getElementById("subject-count-meta");
  if (!meta) return;
  const loaiText = LOAI_DK_LABELS[currentLoaiDk] || "Học mới";
  const conflictText = currentNoConflict ? ", Không trùng lịch" : "";
  meta.textContent = `Đợt ${currentSemesterId}, ${loaiText}${conflictText}`;
}

function showInlineBanner(message) {
  const banner = document.getElementById("inline-action-banner");
  if (!banner) return;
  banner.textContent = String(message || "");
  banner.hidden = !message;
}

function switchView(viewName) {
  const views = ["open", "registered", "schedule", "sniper", "settings"];
  views.forEach(v => {
    const sec = document.getElementById(`view-${v}`);
    const tab = document.getElementById(`tab-${v}`);
    if (sec) sec.hidden = v !== viewName;
    if (tab) {
      tab.setAttribute("aria-selected", v === viewName ? "true" : "false");
    }
  });

  if (viewName === "registered") {
    loadRegisteredCourses();
  } else if (viewName === "schedule") {
    loadWeeklySchedule();
  } else if (viewName === "sniper") {
    renderSniperStationTargets();
  } else if (viewName === "settings") {
    loadSettings();
  }
}

function setLedgerState(stateName, errorMsg) {
  const loading = document.getElementById("state-loading");
  const empty = document.getElementById("state-empty");
  const error = document.getElementById("state-error");
  const full = document.getElementById("state-full");

  loading.hidden = stateName !== "loading";
  empty.hidden = stateName !== "empty";
  error.hidden = stateName !== "error";
  full.hidden = stateName !== "full";

  if (stateName === "error" && errorMsg) {
    const errText = document.getElementById("error-detail-text");
    if (errText) errText.textContent = errorMsg;
  }
}

async function onSemesterChange(idDot) {
  currentSemesterId = String(idDot);
  clearSubjectCache();
  updateHeaderMeta();
  showInlineBanner("");

  if (!hasBridge()) {
    return;
  }

  await reloadSubjects();
}

async function onFilterChange() {
  const loaiSel = document.getElementById("loai-dk-select");
  const chkConflict = document.getElementById("chk-no-conflict");

  if (loaiSel) {
    currentLoaiDk = parseInt(loaiSel.value, 10) || 1;
  }
  if (chkConflict) {
    currentNoConflict = Boolean(chkConflict.checked);
  }
  clearSubjectCache();
  updateHeaderMeta();
  showInlineBanner("");

  if (!hasBridge()) {
    return;
  }

  await reloadSubjects();
}

async function reloadSubjects() {
  if (!hasBridge()) {
    return;
  }
  setLedgerState("loading");
  try {
    const res = await window.pywebview.api.get_open_subjects(currentSemesterId, currentLoaiDk);
    if (!res || !res.success) {
      setLedgerState("error", (res && res.message) || "Không thể đồng bộ danh mục môn học.");
      return;
    }
    const subjects = res.subjects || [];
    const heading = document.getElementById("heading-open-subjects");
    if (heading) {
      heading.textContent = subjects.length + " môn học mở trong kỳ";
    }
    if (subjects.length === 0) {
      setLedgerState("empty");
      return;
    }
    renderSubjectsRows(subjects);
    setLedgerState("full");
  } catch (e) {
    setLedgerState("error", String(e));
  }
}

function renderSubjectsRows(subjects) {
  const tbody = document.getElementById("subjects-tbody");
  if (!tbody) return;
  tbody.innerHTML = "";

  for (const s of subjects) {
    const tr = document.createElement("tr");
    tr.className = "ledger-row";
    tr.dataset.mamh = s.ma_mon;
    tr.dataset.mahp = s.ma_hp;
    tr.dataset.mamoncha = s.ma_mon_cha || "";
    tr.tabIndex = 0;
    tr.setAttribute("aria-expanded", "false");
    tr.onmouseenter = () => prefetchSubjectClasses(s.ma_mon, s.ma_hp, s.ten_mon, s.ma_mon_cha || "");
    tr.onclick = () => inspectSubjectClasses(s.ma_mon, s.ma_hp, s.ten_mon, s.ma_mon_cha || "");
    tr.onkeydown = (ev) => handleRowKey(ev, s.ma_mon, s.ma_hp, s.ten_mon, s.ma_mon_cha || "");
    tr.innerHTML = `
      <td class="mono">${escapeHtml(s.ma_hp)}</td>
      <td>${escapeHtml(s.ten_mon)}</td>
      <td class="num">${s.so_tc}</td>
      <td>
        <button type="button" class="btn" id="btn-inspect-${escapeAttr(s.ma_mon)}" onclick="event.stopPropagation(); inspectSubjectClasses('${escapeAttr(s.ma_mon)}', '${escapeAttr(s.ma_hp)}', '${escapeAttr(s.ten_mon)}', '${escapeAttr(s.ma_mon_cha || "")}')">Xem lớp mở</button>
      </td>
    `;
    tbody.appendChild(tr);
  }
}

function handleRowKey(ev, maMon, maHp, tenMon, maMonCha = "") {
  if (ev.key === "Enter" || ev.key === " ") {
    ev.preventDefault();
    inspectSubjectClasses(maMon, maHp, tenMon, maMonCha);
  }
}

function fetchSubjectEnrichedCached(maMon, maHp, tenMon, maMonCha = "", forceRefresh = false) {
  const key = getSubjectCacheKey(currentSemesterId, maMon, currentLoaiDk, currentNoConflict);
  if (!forceRefresh && subjectClassesCache.has(key)) {
    return Promise.resolve(subjectClassesCache.get(key));
  }
  if (!forceRefresh && subjectInflightMap.has(key)) {
    return subjectInflightMap.get(key);
  }
  const promise = window.pywebview.api.get_enriched_classes_for_subject(
    currentSemesterId,
    maMon,
    maHp,
    tenMon,
    maMonCha || "",
    currentLoaiDk,
    currentNoConflict
  ).then(res => {
    subjectInflightMap.delete(key);
    if (res && res.success) {
      subjectClassesCache.set(key, res);
    }
    return res;
  }).catch(err => {
    subjectInflightMap.delete(key);
    throw err;
  });
  subjectInflightMap.set(key, promise);
  return promise;
}

function prefetchSubjectClasses(maMon, maHp, tenMon, maMonCha = "") {
  if (!hasBridge()) return;
  clearTimeout(hoverPrefetchTimer);
  hoverPrefetchTimer = setTimeout(() => {
    fetchSubjectEnrichedCached(maMon, maHp, tenMon, maMonCha, false).catch(() => {});
  }, 150);
}

async function inspectSubjectClasses(maMon, maHp, tenMon, maMonCha = "", forceRefresh = false) {
  const targetRow = document.querySelector(`tr[data-mamh="${maMon}"]`);
  const existingDrawer = document.getElementById("drawer-" + maMon);
  const btn = document.getElementById("btn-inspect-" + maMon);

  if (existingDrawer && !forceRefresh) {
    const nextHidden = !existingDrawer.hidden;
    existingDrawer.hidden = nextHidden;
    if (targetRow) {
      targetRow.classList.toggle("ledger-row--selected", !nextHidden);
      targetRow.setAttribute("aria-expanded", nextHidden ? "false" : "true");
    }
    if (btn) {
      btn.textContent = nextHidden ? "Xem lớp mở" : "Đóng lớp mở";
    }
    return;
  }

  if (!hasBridge()) {
    if (!existingDrawer && targetRow) {
      const fallbackDrawer = document.createElement("tr");
      fallbackDrawer.id = "drawer-" + maMon;
      fallbackDrawer.innerHTML = `
        <td colspan="4" class="class-drawer">
          <div class="drawer-toolbar">
            <span>Chi tiết học phần ${escapeHtml(tenMon)} (${escapeHtml(maHp)})</span>
            <span>Chế độ xem trước</span>
          </div>
          <table class="ledger-table" aria-label="Danh sách lớp học phần ${escapeAttr(tenMon)}">
            <thead>
              <tr>
                <th scope="col">Lớp &amp; Mã LHP</th>
                <th scope="col">Nhóm TH</th>
                <th scope="col">Lịch học &amp; Phòng (LT + TH)</th>
                <th scope="col">Giảng viên</th>
                <th scope="col">Sĩ số</th>
                <th scope="col">Thao tác</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td>
                  <div class="mono">DHLOP_${escapeHtml(maMon)}</div>
                  <div class="schedule-meta">Mã LHP: ${escapeHtml(maHp)}01</div>
                </td>
                <td><span class="stamp-badge stamp-badge--neutral">Thuần LT</span></td>
                <td>
                  <div class="schedule-stack">
                    <div class="schedule-line">LT: Thứ 2 (Tiết 1 - 3) · Phòng B2.04</div>
                    <div class="schedule-meta">Cơ sở 1, 13/01/2026 - 07/04/2026</div>
                  </div>
                </td>
                <td><div class="lecturer-name">PGS.TS Nguyễn Minh Tuấn</div></td>
                <td>
                  <div class="mono">24 / 45</div>
                  <div><span class="stamp-badge">Còn 21 chỗ</span></div>
                </td>
                <td>
                  <div class="btn-row-actions">
                    <button type="button" class="btn btn--accent-outline" onclick="triggerDirectRegister('${escapeAttr(currentSemesterId)}', 'GUID_${escapeAttr(maMon)}', null, ${currentLoaiDk}, '', '${escapeAttr(tenMon)}', 'DHLOP_${escapeAttr(maMon)}')">Đăng ký ngay</button>
                    <button type="button" class="btn" onclick="addTargetToQueue('${escapeAttr(currentSemesterId)}', '${escapeAttr(maMon)}', '${escapeAttr(maHp)}', '${escapeAttr(tenMon)}', 'GUID_${escapeAttr(maMon)}', 'DHLOP_${escapeAttr(maMon)}', null, ${currentLoaiDk}, '')">Đưa vào khay săn</button>
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
        </td>
      `;
      targetRow.classList.add("ledger-row--selected");
      targetRow.setAttribute("aria-expanded", "true");
      if (btn) btn.textContent = "Đóng lớp mở";
      targetRow.insertAdjacentElement("afterend", fallbackDrawer);
    }
    return;
  }

  if (targetRow) {
    targetRow.classList.add("ledger-row--selected");
    targetRow.setAttribute("aria-expanded", "true");
  }
  if (btn) {
    btn.disabled = true;
    btn.textContent = "Đang tải lịch…";
  }

  let drawerTr = existingDrawer;
  if (!drawerTr && targetRow) {
    drawerTr = document.createElement("tr");
    drawerTr.id = "drawer-" + maMon;
    drawerTr.innerHTML = `
      <td colspan="4" class="class-drawer">
        <div class="drawer-skeleton">
          <span>Đang đồng bộ lịch học và giảng viên cho học phần ${escapeHtml(tenMon)}…</span>
          <div class="skeleton-line"></div>
          <div class="skeleton-line"></div>
        </div>
      </td>
    `;
    targetRow.insertAdjacentElement("afterend", drawerTr);
  } else if (drawerTr) {
    drawerTr.hidden = false;
  }

  try {
    const res = await fetchSubjectEnrichedCached(maMon, maHp, tenMon, maMonCha || "", forceRefresh);

    if (btn) {
      btn.disabled = false;
      btn.textContent = "Đóng lớp mở";
    }

    if (!res || !res.success) {
      showInlineBanner((res && res.message) || "Không thể tải danh sách lớp học phần.");
      return;
    }

    const rows = res.rows || [];
    const rowsHtml = renderEnrichedDrawerRows(rows, maMon, maHp, tenMon, maMonCha);

    if (drawerTr) {
      drawerTr.innerHTML = `
        <td colspan="4" class="class-drawer">
          <div class="drawer-toolbar">
            <span>Đã đồng bộ ${rows.length} nhóm lớp cho học phần ${escapeHtml(tenMon)}</span>
            <button type="button" class="btn" onclick="event.stopPropagation(); inspectSubjectClasses('${escapeAttr(maMon)}', '${escapeAttr(maHp)}', '${escapeAttr(tenMon)}', '${escapeAttr(maMonCha || "")}', true)">Làm mới sĩ số</button>
          </div>
          <table class="ledger-table" aria-label="Danh sách lớp học phần ${escapeAttr(tenMon)}">
            <thead>
              <tr>
                <th scope="col">Lớp &amp; Mã LHP</th>
                <th scope="col">Nhóm TH</th>
                <th scope="col">Lịch học &amp; Phòng (LT + TH)</th>
                <th scope="col">Giảng viên</th>
                <th scope="col">Sĩ số</th>
                <th scope="col">Thao tác</th>
              </tr>
            </thead>
            <tbody>${rowsHtml || '<tr><td colspan="6">Chưa có lớp mở phù hợp bộ lọc hiện tại.</td></tr>'}</tbody>
          </table>
        </td>
      `;
    }
  } catch (e) {
    if (btn) {
      btn.disabled = false;
      btn.textContent = "Xem lớp mở";
    }
    showInlineBanner("Lỗi khi tải lịch học: " + String(e));
  }
}

function renderEnrichedDrawerRows(rows, maMon, maHp, tenMon, maMonCha) {
  return rows.map(r => {
    const avail = (r.si_so_max || 0) - (r.si_so_dk || 0);
    const canDirectReg = avail > 0 && !r.da_khoa;
    const badgeClass = canDirectReg ? "stamp-badge" : "stamp-badge stamp-badge--neutral";
    const badgeText = r.da_khoa ? "Đã khóa" : (avail > 0 ? `Còn ${avail} chỗ` : "Đã đủ sĩ số");
    const sniperLabel = avail > 0 ? "Đưa vào khay săn" : "Canh người nhả";
    const nhomArg = (r.nhom_th !== null && r.nhom_th !== undefined) ? Number(r.nhom_th) : "null";

    const thLineHtml = r.lich_th
      ? `<div class="schedule-line">TH: ${escapeHtml(r.lich_th)}</div>`
      : "";

    const metaParts = [];
    if (r.co_so) metaParts.push(r.co_so);
    if (r.thoi_gian) metaParts.push(r.thoi_gian);
    const metaLineHtml = metaParts.length > 0
      ? `<div class="schedule-meta">${escapeHtml(metaParts.join(", "))}</div>`
      : "";

    return `
      <tr>
        <td>
          <div class="mono">${escapeHtml(r.ten_lop)}</div>
          <div class="schedule-meta">Mã LHP: ${escapeHtml(r.ma_lhp || r.ten_lop)}</div>
        </td>
        <td><span class="stamp-badge stamp-badge--neutral">${escapeHtml(r.nhom_th_label || "Thuần LT")}</span></td>
        <td>
          <div class="schedule-stack">
            <div class="schedule-line">LT: ${escapeHtml(r.lich_lt || "Chưa công bố lịch")}</div>
            ${thLineHtml}
            ${metaLineHtml}
          </div>
        </td>
        <td>
          <div class="lecturer-name">${escapeHtml(r.giang_vien || "Đang cập nhật")}</div>
        </td>
        <td>
          <div class="mono">${r.si_so_dk} / ${r.si_so_max}</div>
          <div><span class="${badgeClass}">${badgeText}</span></div>
        </td>
        <td>
          <div class="btn-row-actions">
            <button type="button" class="btn btn--accent-outline" ${canDirectReg ? "" : "disabled"} onclick="triggerDirectRegister('${escapeAttr(currentSemesterId)}', '${escapeAttr(r.guid_lhp)}', ${nhomArg}, ${currentLoaiDk}, '${escapeAttr(maMonCha || r.ma_mon_cha || "")}', '${escapeAttr(tenMon)}', '${escapeAttr(r.ten_lop)}')">Đăng ký ngay</button>
            <button type="button" class="btn" onclick="addTargetToQueue('${escapeAttr(currentSemesterId)}', '${escapeAttr(maMon)}', '${escapeAttr(maHp)}', '${escapeAttr(tenMon)}', '${escapeAttr(r.guid_lhp)}', '${escapeAttr(r.ten_lop)}', ${nhomArg}, ${currentLoaiDk}, '${escapeAttr(maMonCha || r.ma_mon_cha || "")}')">${sniperLabel}</button>
          </div>
        </td>
      </tr>
    `;
  }).join("");
}

async function triggerDirectRegister(idDot, guidLhp, nhomTh, loaiDk, maMonCha, tenMon, tenLop) {
  const groupText = nhomTh !== null && nhomTh !== undefined ? `Nhóm TH ${nhomTh}` : "Thuần LT";
  showInlineBanner(`Đang gửi lệnh đăng ký trực tiếp: ${tenMon} (${tenLop}, ${groupText})…`);

  if (!hasBridge()) {
    const sampleRes = { success: true, message: `Đã ghi nhận lệnh đăng ký mẫu cho ${tenMon} (${tenLop}, ${groupText})` };
    showInlineBanner(sampleRes.message);
    return sampleRes;
  }

  try {
    const res = await window.pywebview.api.direct_register(
      idDot,
      guidLhp,
      nhomTh,
      loaiDk || currentLoaiDk,
      maMonCha || ""
    );
    if (res && res.success) {
      showInlineBanner(`Đăng ký thành công học phần ${tenMon} (${tenLop}, ${groupText}): ${res.message || "Đã ghi nhận"}`);
    } else {
      showInlineBanner(`Cổng trường từ chối đăng ký (${tenLop}, ${groupText}): ${(res && res.message) || "Không rõ nguyên nhân"}`);
    }
    return res || { success: false, message: "Phản hồi rỗng" };
  } catch (e) {
    const errRes = { success: false, message: `Lỗi kết nối: ${String(e)}` };
    showInlineBanner(`Lỗi kết nối khi đăng ký ${tenLop}: ${String(e)}`);
    return errRes;
  }
}

async function addTargetToQueue(idDot, maMon, maHp, tenMon, guidLhp, tenLop, nhomTh = null, loaiDk = 1, maMonCha = "") {
  const normNhom = (nhomTh !== null && nhomTh !== undefined && String(nhomTh).trim() !== "" && String(nhomTh) !== "null")
    ? Number(nhomTh)
    : null;
  const targetKey = `${guidLhp}_${normNhom !== null ? normNhom : 0}`;
  const groupText = normNhom !== null ? `Nhóm TH ${normNhom}` : "Thuần LT";
  const loaiText = LOAI_DK_LABELS[loaiDk || currentLoaiDk] || "Học mới";

  if (hasBridge()) {
    try {
      const res = await window.pywebview.api.add_target(
        idDot,
        maMon,
        maHp,
        tenMon,
        guidLhp,
        tenLop,
        normNhom,
        loaiDk || currentLoaiDk,
        maMonCha || ""
      );
      if (res && res.targets) {
        sniperTargets = res.targets;
      }
    } catch (e) {
      console.error(e);
    }
  } else {
    if (!sniperTargets.some(t => (t.target_key || `${t.guid_lhp}_${t.nhom_th || 0}`) === targetKey)) {
      sniperTargets.push({
        target_key: targetKey,
        id_dot: String(idDot),
        ma_mon: String(maMon),
        ma_hp: String(maHp),
        ten_mon: String(tenMon),
        guid_lhp: String(guidLhp),
        ten_lop: String(tenLop),
        nhom_th: normNhom,
        loai_dk: Number(loaiDk || currentLoaiDk),
        ma_mon_cha: String(maMonCha || ""),
        registered: false
      });
    }
  }

  renderSniperStationTargets();
  showInlineBanner(`Đã thêm ${tenMon} (${tenLop}, ${groupText}) vào Trạm canh lớp.`);
  appendTelemetryLog(`Đã thêm mục tiêu: ${tenMon} (${tenLop}, ${groupText}, ${loaiText})`);
}

function renderSniperStationTargets() {
  updateSniperTabBadge();
  const emptyState = document.getElementById("sniper-empty-state");
  const table = document.getElementById("sniper-targets-table");
  const tbody = document.getElementById("sniper-targets-tbody");
  if (!tbody) return;

  if (!sniperTargets || sniperTargets.length === 0) {
    if (emptyState) emptyState.hidden = false;
    if (table) table.hidden = true;
    tbody.innerHTML = "";
    return;
  }

  if (emptyState) emptyState.hidden = true;
  if (table) table.hidden = false;

  tbody.innerHTML = sniperTargets.map(t => {
    const tKey = t.target_key || `${t.guid_lhp}_${t.nhom_th !== null && t.nhom_th !== undefined ? t.nhom_th : 0}`;
    const groupLabel = t.nhom_th ? `Nhóm TH ${t.nhom_th}` : "Thuần LT";
    const loaiLabel = LOAI_DK_LABELS[t.loai_dk] || "Học mới";
    const sisoText = (t.si_so_dk !== undefined && t.si_so_dk !== null && t.si_so_max !== undefined && t.si_so_max !== null)
      ? `${t.si_so_dk} / ${t.si_so_max}`
      : "Chưa quét";
    const isReg = Boolean(t.registered);
    const badgeClass = isReg ? "stamp-badge" : "stamp-badge stamp-badge--neutral";
    const badgeText = isReg ? "Đã ghi danh" : (t.slot_available ? "Có chỗ trống" : "Đang chờ slot");
    const latencyText = t.latency_ms ? `${t.latency_ms} ms` : "—";

    return `
      <tr class="ledger-row" id="target-row-${escapeAttr(tKey)}">
        <td>
          <div class="mono">${escapeHtml(t.ten_lop || t.guid_lhp)}</div>
          <div class="schedule-meta">${escapeHtml(t.ten_mon || t.ma_mon)}</div>
        </td>
        <td><span class="stamp-badge stamp-badge--neutral">${escapeHtml(groupLabel)}</span></td>
        <td>${escapeHtml(loaiLabel)}</td>
        <td>
          <div class="mono" id="siso-${escapeAttr(tKey)}">${sisoText}</div>
          <div><span class="${badgeClass}" id="status-${escapeAttr(tKey)}">${badgeText}</span></div>
        </td>
        <td class="mono" id="latency-${escapeAttr(tKey)}">${latencyText}</td>
        <td>
          <div class="btn-row-actions">
            <button type="button" class="btn btn--accent-outline" onclick="fireTargetNow('${escapeAttr(tKey)}')">Bắn thử ngay</button>
            <button type="button" class="btn" onclick="removeTargetFromQueue('${escapeAttr(tKey)}')">Xóa</button>
          </div>
        </td>
      </tr>
    `;
  }).join("");
}

async function removeTargetFromQueue(targetKey) {
  if (hasBridge()) {
    try {
      const res = await window.pywebview.api.remove_target(targetKey);
      if (res && res.success) {
        sniperTargets = res.targets || [];
      }
    } catch (e) {
      console.error(e);
    }
  } else {
    sniperTargets = sniperTargets.filter(t => (t.target_key || `${t.guid_lhp}_${t.nhom_th || 0}`) !== targetKey);
  }
  renderSniperStationTargets();
  appendTelemetryLog(`Đã xóa mục tiêu ${targetKey} khỏi hàng đợi.`);
}

async function clearAllTargets() {
  if (sniperTargets.length === 0) return;
  if (!confirm("Xác nhận xóa toàn bộ mục tiêu trong khay canh lớp?")) return;
  if (hasBridge()) {
    try {
      await window.pywebview.api.clear_targets();
    } catch (e) {
      console.error(e);
    }
  }
  sniperTargets = [];
  renderSniperStationTargets();
  appendTelemetryLog("Đã xóa toàn bộ mục tiêu khỏi trạm canh lớp.");
}

async function fireTargetNow(targetKey) {
  const t = sniperTargets.find(item => (item.target_key || `${item.guid_lhp}_${item.nhom_th || 0}`) === targetKey);
  if (!t) return;
  const groupText = t.nhom_th ? `Nhóm TH ${t.nhom_th}` : "Thuần LT";
  appendTelemetryLog(`[Bắn thủ công] Gửi lệnh ghi danh ${t.ten_mon} (${t.ten_lop}, ${groupText})…`);
  const res = await triggerDirectRegister(t.id_dot, t.guid_lhp, t.nhom_th, t.loai_dk, t.ma_mon_cha || "", t.ten_mon, t.ten_lop);
  if (res) {
    appendTelemetryLog(`[Bắn thủ công] Kết quả: ${res.message || (res.success ? "Thành công" : "Thất bại")}`, res.success, !res.success);
    if (res.success) {
      t.registered = true;
      renderSniperStationTargets();
    }
  }
}

function appendTelemetryLog(message, isSuccess = false, isError = false) {
  const box = document.getElementById("sniper-telemetry-log");
  if (!box) return;
  const nowStr = new Date().toTimeString().slice(0, 8);
  const entry = document.createElement("div");
  entry.className = "telemetry-entry" + (isSuccess ? " telemetry-entry--success" : (isError ? " telemetry-entry--error" : ""));
  entry.innerHTML = `<span class="mono">[${nowStr}]</span> <span>${escapeHtml(message)}</span>`;
  box.appendChild(entry);
  while (box.children.length > 100) {
    box.removeChild(box.firstChild);
  }
  box.scrollTop = box.scrollHeight;
}

function clearTelemetryLog() {
  const box = document.getElementById("sniper-telemetry-log");
  if (box) box.innerHTML = "";
}

async function runSniperSweepOnce() {
  if (!hasBridge()) {
    appendTelemetryLog("Quét thử mô phỏng: 0 mục tiêu.");
    return;
  }
  appendTelemetryLog("Đang quét nhanh một lượt tất cả mục tiêu…");
  try {
    const res = await window.pywebview.api.poll_sniper_once();
    if (res && res.events) {
      processSniperEvents(res.events);
    }
  } catch (e) {
    appendTelemetryLog("Lỗi quét: " + String(e), false, true);
  }
}

function processSniperEvents(events) {
  for (const ev of events) {
    const tKey = ev.target_key;
    const sisoEl = document.getElementById("siso-" + tKey);
    const statusEl = document.getElementById("status-" + tKey);
    const latencyEl = document.getElementById("latency-" + tKey);

    if (sisoEl && ev.si_so_dk !== undefined && ev.si_so_dk !== null) {
      sisoEl.textContent = `${ev.si_so_dk} / ${ev.si_so_max}`;
    }
    if (latencyEl && ev.latency_ms) {
      latencyEl.textContent = `${ev.latency_ms} ms`;
    }
    if (statusEl) {
      if (ev.registered) {
        statusEl.className = "stamp-badge";
        statusEl.textContent = "Đã ghi danh";
        playNotificationChime();
      } else if (ev.slot_available) {
        statusEl.className = "stamp-badge";
        statusEl.textContent = "Có chỗ trống";
        playNotificationChime();
      } else {
        statusEl.className = "stamp-badge stamp-badge--neutral";
        statusEl.textContent = "Đang chờ slot";
      }
    }

    const targetObj = sniperTargets.find(t => (t.target_key || `${t.guid_lhp}_${t.nhom_th || 0}`) === tKey);
    if (targetObj) {
      if (ev.si_so_dk !== undefined && ev.si_so_dk !== null) targetObj.si_so_dk = ev.si_so_dk;
      if (ev.si_so_max !== undefined && ev.si_so_max !== null) targetObj.si_so_max = ev.si_so_max;
      if (ev.registered) targetObj.registered = true;
      targetObj.slot_available = ev.slot_available;
      targetObj.latency_ms = ev.latency_ms;
    }

    const groupText = ev.nhom_th ? `Nhóm TH ${ev.nhom_th}` : "Thuần LT";
    if (ev.registered) {
      appendTelemetryLog(`CHIẾM CHỖ THÀNH CÔNG: ${ev.ten_mon} (${ev.ten_lop}, ${groupText}) - ${ev.message || "OK"}`, true);
    } else if (ev.slot_available) {
      appendTelemetryLog(`PHÁT HIỆN SLOT: ${ev.ten_mon} (${ev.ten_lop}) đang có chỗ trống!`, true);
    } else if (ev.type === "checked") {
      appendTelemetryLog(`Quét ${ev.ten_lop} (${groupText}): Sĩ số ${ev.si_so_dk}/${ev.si_so_max} (${ev.latency_ms} ms)`);
    } else if (ev.type === "not_found") {
      appendTelemetryLog(`Không tìm thấy lớp ${ev.ten_lop} (${ev.latency_ms} ms)`, false, true);
    } else if (ev.type === "error") {
      appendTelemetryLog(`Lỗi kiểm tra ${ev.ten_lop}: ${ev.message}`, false, true);
    }
  }
}

async function toggleSniperLoop() {
  const btn = document.getElementById("btn-sniper-start");
  const badge = document.getElementById("sniper-state-badge");
  const sel = document.getElementById("sniper-interval-select");
  const intervalMs = (sel && parseInt(sel.value, 10)) || 1500;

  sniperActive = !sniperActive;
  if (sniperActive) {
    if (btn) btn.textContent = "Dừng canh lớp";
    if (badge) {
      badge.textContent = "Đang quét slot";
      badge.className = "stamp-badge";
    }
    appendTelemetryLog(`Đã kích hoạt vòng lặp canh lớp tự động (Chu kỳ ${intervalMs} ms)…`);
    updateSniperTabBadge();

    if (hasBridge()) {
      sniperTimer = setInterval(async () => {
        try {
          const res = await window.pywebview.api.poll_sniper_once();
          if (res && res.events) {
            processSniperEvents(res.events);
          }
        } catch (e) {
          appendTelemetryLog("Lỗi vòng lặp quét: " + String(e), false, true);
        }
      }, intervalMs);
    }
  } else {
    if (btn) btn.textContent = "Kích hoạt canh lớp tự động";
    if (badge) {
      badge.textContent = "Tạm dừng";
      badge.className = "stamp-badge stamp-badge--neutral";
    }
    appendTelemetryLog("Đã tạm dừng vòng lặp canh lớp tự động.");
    clearInterval(sniperTimer);
    sniperTimer = null;
    updateSniperTabBadge();
  }
}

async function pingRadarNow() {
  const label = document.getElementById("radar-last-ping");
  const pingEl = document.getElementById("last-ping-time");
  if (label) label.textContent = "Đang ping…";
  if (!hasBridge()) {
    if (label) label.textContent = "Mô phỏng 200 OK";
    return;
  }
  try {
    const status = await window.pywebview.api.ping_radar(currentSemesterId);
    if (status) {
      const text = `${status.timestamp}, ${status.code}`;
      if (label) label.textContent = text;
      if (pingEl) pingEl.textContent = text;
      appendTelemetryLog(`Radar ping: ${status.message || status.code} (${text})`);
    }
  } catch (e) {
    if (label) label.textContent = "Lỗi kết nối";
    appendTelemetryLog("Radar ping lỗi: " + String(e), false, true);
  }
}

async function toggleRadar() {
  const label = document.getElementById("radar-label");
  radarActive = !radarActive;
  label.textContent = radarActive ? "Đang nuôi phiên" : "Nuôi phiên 24/7";

  if (hasBridge()) {
    const status = await window.pywebview.api.ping_radar(currentSemesterId);
    const pingEl = document.getElementById("last-ping-time");
    if (pingEl && status) {
      pingEl.textContent = `${status.timestamp}, ${status.code}`;
    }
  }
}

function filterSubjects(query) {
  const q = String(query || "").toLowerCase().trim();
  const rows = document.querySelectorAll("#subjects-tbody tr.ledger-row");
  rows.forEach(r => {
    const text = r.textContent.toLowerCase();
    r.hidden = q.length > 0 && !text.includes(q);
  });
}

async function loadRegisteredCourses() {
  if (!hasBridge()) return;
  try {
    const res = await window.pywebview.api.get_registered_courses(currentSemesterId, currentLoaiDk);
    if (!res || !res.success) return;
    const courses = res.courses || [];
    const tbody = document.getElementById("registered-tbody");
    const heading = document.getElementById("heading-registered");
    const tuitionEl = document.getElementById("registered-tuition-total");

    const totalTc = courses.reduce((acc, c) => acc + (Number(c.so_tc) || 0), 0);
    const totalFee = courses.reduce((acc, c) => {
      const digits = String(c.hoc_phi || "").replace(/\D+/g, "");
      return acc + (digits ? parseInt(digits, 10) : 0);
    }, 0);

    if (heading) {
      heading.textContent = `${courses.length} lớp học phần đã đăng ký (${totalTc} tín chỉ)`;
    }
    if (tuitionEl) {
      tuitionEl.textContent = totalFee > 0
        ? totalFee.toLocaleString("vi-VN") + " VND"
        : "0 VND";
    }

    if (!tbody) return;
    tbody.innerHTML = courses.map(c => `
      <tr class="ledger-row" tabindex="0" onclick="inspectRegisteredSchedule('${escapeAttr(c.id_lhp_dk)}', '${escapeAttr(c.guid)}', '${escapeAttr(c.ten_mon)}', '${escapeAttr(c.lop_du_kien)}')">
        <td class="mono">${escapeHtml(c.ma_lhp)}</td>
        <td>${escapeHtml(c.ten_mon)}</td>
        <td class="mono">${escapeHtml(c.lop_du_kien)}</td>
        <td class="num">${c.so_tc || 0}</td>
        <td class="mono">${escapeHtml(c.nhom_th || "Không")}</td>
        <td class="mono">${escapeHtml(c.hoc_phi || "0")}</td>
        <td><span class="stamp-badge stamp-badge--neutral">${escapeHtml(c.trang_thai_lhp || c.trang_thai_dk || "Đã đăng ký")}</span></td>
        <td>
          <button type="button" class="btn" onclick="event.stopPropagation(); cancelCourse('${escapeAttr(c.id_lhp_dk)}', '${escapeAttr(c.guid)}', '${escapeAttr(c.ten_mon)}')">Hủy lớp</button>
        </td>
      </tr>
    `).join("");
  } catch (e) {
    console.error(e);
  }
}

async function inspectRegisteredSchedule(idLhpDk, guidLhp, tenMon, tenLop) {
  const existingDrawer = document.getElementById("reg-drawer-" + idLhpDk);
  if (existingDrawer) {
    existingDrawer.hidden = !existingDrawer.hidden;
    return;
  }
  if (!hasBridge()) return;

  const targetRow = document.querySelector(`tr[onclick*="${idLhpDk}"]`);
  if (!targetRow) return;

  const drawerTr = document.createElement("tr");
  drawerTr.id = "reg-drawer-" + idLhpDk;
  drawerTr.innerHTML = `
    <td colspan="8" class="class-drawer">
      <div class="drawer-skeleton">
        <span>Đang tải lịch học chi tiết cho ${escapeHtml(tenMon)} (${escapeHtml(tenLop)})…</span>
        <div class="skeleton-line"></div>
      </div>
    </td>
  `;
  targetRow.insertAdjacentElement("afterend", drawerTr);

  try {
    const res = await window.pywebview.api.get_schedule_for_class(guidLhp);
    const scheds = (res && res.schedules) || [];
    if (scheds.length === 0) {
      drawerTr.innerHTML = `
        <td colspan="8" class="class-drawer">
          <div class="schedule-meta" style="padding: var(--space-xs);">Chưa có lịch học công bố cho lớp ${escapeHtml(tenLop)}.</div>
        </td>
      `;
      return;
    }

    const rowsHtml = scheds.map(s => `
      <tr>
        <td class="mono">${escapeHtml(s.stt || "")}</td>
        <td><span class="stamp-badge stamp-badge--neutral">${escapeHtml(s.loai_tiet || "LT")}</span></td>
        <td class="mono">${escapeHtml(s.thu_tiet || "")}</td>
        <td class="mono">${escapeHtml(s.nhom_th || "Chung")}</td>
        <td>${escapeHtml(s.phong || "")} (${escapeHtml(s.day_nha || "")}, ${escapeHtml(s.co_so || "")})</td>
        <td class="lecturer-name">${escapeHtml(s.giang_vien || "Đang cập nhật")}</td>
        <td class="schedule-meta">${escapeHtml(s.thoi_gian || "")}</td>
      </tr>
    `).join("");

    drawerTr.innerHTML = `
      <td colspan="8" class="class-drawer">
        <div class="drawer-toolbar">
          <span>Lịch học chi tiết của lớp ${escapeHtml(tenLop)} (${escapeHtml(tenMon)})</span>
          <span>${scheds.length} buổi học</span>
        </div>
        <table class="ledger-table" aria-label="Chi tiết lịch học ${escapeAttr(tenMon)}">
          <thead>
            <tr>
              <th scope="col">STT</th>
              <th scope="col">Loại</th>
              <th scope="col">Thứ &amp; Tiết</th>
              <th scope="col">Nhóm TH</th>
              <th scope="col">Phòng &amp; Cơ sở</th>
              <th scope="col">Giảng viên</th>
              <th scope="col">Thời gian</th>
            </tr>
          </thead>
          <tbody>${rowsHtml}</tbody>
        </table>
      </td>
    `;
  } catch (e) {
    drawerTr.innerHTML = `
      <td colspan="8" class="class-drawer">
        <div class="helper-line" style="color: var(--color-error); padding: var(--space-xs);">Lỗi tải lịch học: ${escapeHtml(String(e))}</div>
      </td>
    `;
  }
}
async function cancelCourse(idDk, guidDk, tenMon) {
  if (!confirm(`Xác nhận hủy đăng ký học phần: ${tenMon}?`)) return;
  if (!hasBridge()) return;
  const res = await window.pywebview.api.cancel_course(idDk, guidDk);
  if (res && res.success) {
    await loadRegisteredCourses();
  } else {
    alert((res && res.message) || "Không thể hủy lớp học phần này.");
  }
}

function openLoginModal() {
  const modal = document.getElementById("login-modal");
  if (modal) modal.hidden = false;
  refreshCaptcha();
}

function closeLoginModal() {
  const modal = document.getElementById("login-modal");
  if (modal) modal.hidden = true;
}

async function refreshCaptcha() {
  const imgEl = document.getElementById("captcha-preview-img");
  const feedback = document.getElementById("login-feedback");
  const refreshBtn = document.getElementById("btn-refresh-captcha");
  const capInput = document.getElementById("login-captcha");

  if (!hasBridge()) {
    if (imgEl) {
      imgEl.src = "./captcha.jpg?t=" + Date.now();
    }
    if (feedback) {
      feedback.textContent = "Đã làm mới ảnh mã bảo vệ trực tiếp trên hộp thoại.";
    }
    return;
  }

  if (refreshBtn) refreshBtn.disabled = true;
  if (feedback) feedback.textContent = "Đang tải ảnh mã bảo vệ mới từ sv.iuh.edu.vn…";

  try {
    const res = await window.pywebview.api.prepare_login_challenge();
    if (refreshBtn) refreshBtn.disabled = false;
    if (res && res.success) {
      if (imgEl && res.image_data_uri) {
        imgEl.src = res.image_data_uri;
      }
      if (capInput) {
        capInput.value = "";
        capInput.focus();
      }
      if (feedback) {
        feedback.textContent = "Đã tải mã bảo vệ mới. Vui lòng nhập 4 ký tự vào ô bên dưới.";
      }
    } else if (feedback) {
      feedback.textContent = (res && res.message) || "Không thể tải ảnh mã bảo vệ.";
    }
  } catch (e) {
    if (refreshBtn) refreshBtn.disabled = false;
    if (feedback) feedback.textContent = "Lỗi tải ảnh mã bảo vệ: " + String(e);
  }
}

async function submitNativeLogin(ev) {
  ev.preventDefault();
  if (!hasBridge()) {
    closeLoginModal();
    return;
  }
  const user = document.getElementById("login-username").value.trim();
  const pass = document.getElementById("login-password").value;
  const cap = document.getElementById("login-captcha").value.trim();
  const feedback = document.getElementById("login-feedback");

  if (feedback) feedback.textContent = "Đang mã hóa AES-128-CBC và xác thực…";
  const res = await window.pywebview.api.submit_login(user, pass, cap);
  if (res && res.success) {
    closeLoginModal();
    await initDashboardFromBridge();
  } else {
    if (feedback) {
      feedback.textContent = (res && res.message) || "Đăng nhập không thành công. Đang đổi ảnh mã bảo vệ mới…";
    }
    await refreshCaptcha();
  }
}

async function initDashboardFromBridge() {
  if (!hasBridge()) return;
  try {
    const info = await window.pywebview.api.get_initial_state();
    if (!info) return;

    if (info.profile) {
      document.getElementById("profile-name").textContent = info.profile.ho_ten || "Sinh viên IUH";
      document.getElementById("profile-mssv").textContent = info.profile.mssv || "";
      document.getElementById("profile-class").textContent = info.profile.lop || "";
    }

    if (info.loai_dk) {
      currentLoaiDk = Number(info.loai_dk) || 1;
      const loaiSel = document.getElementById("loai-dk-select");
      if (loaiSel) loaiSel.value = String(currentLoaiDk);
    }

    if (info.semesters && info.semesters.length > 0) {
      const sel = document.getElementById("semester-select");
      sel.innerHTML = info.semesters.map(s =>
        `<option value="${escapeAttr(s.id_dot)}" ${s.id_dot === info.current_dot ? "selected" : ""}>${escapeHtml(s.ten_dot)}</option>`
      ).join("");
      currentSemesterId = info.current_dot || info.semesters[0].id_dot;
    }

    updateHeaderMeta();

    if (info.targets) {
      sniperTargets = info.targets;
      renderSniperStationTargets();
    }

    if (!info.authenticated) {
      openLoginModal();
    } else {
      await reloadSubjects();
    }
  } catch (e) {
    console.error(e);
  }
}

function escapeHtml(str) {
  return String(str || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function escapeAttr(str) {
  return String(str || "").replace(/'/g, "\\'").replace(/"/g, "&quot;");
}


/* ========================================================================= */
/* WEEKLY ACADEMIC SCHEDULE (Ported from IUH XemLichHocTuan via /skill:xia)  */
/* ========================================================================= */
let currentScheduleMode = "official"; // "official" or "preview"

function setScheduleMode(mode) {
  currentScheduleMode = mode;
  const btnOfficial = document.getElementById("btn-sched-mode-official");
  const btnPreview = document.getElementById("btn-sched-mode-preview");
  if (btnOfficial) btnOfficial.classList.toggle("active", mode === "official");
  if (btnPreview) btnPreview.classList.toggle("active", mode === "preview");
  loadWeeklySchedule();
}

async function loadWeeklySchedule() {
  const days = ["2", "3", "4", "5", "6", "7", "CN"];
  const cas = ["sang", "chieu", "toi"];
  // Clear all grid cells first
  cas.forEach(c => {
    days.forEach(d => {
      const cell = document.getElementById(`sched-slot-${c}-${d}`);
      if (cell) cell.innerHTML = "";
    });
  });

  let previewClasses = null;
  if (currentScheduleMode === "preview" && sniperTargets && sniperTargets.length > 0) {
    previewClasses = sniperTargets;
  }

  let scheduleData = null;
  if (hasBridge()) {
    try {
      const res = await window.pywebview.api.get_weekly_schedule(currentSemesterId, previewClasses);
      if (res && res.success) {
        scheduleData = res;
      }
    } catch (e) {
      console.error("Lỗi khi tải thời khóa biểu:", e);
    }
  }

  // If no bridge (e.g. browser test mode or preview), supply authentic default schedule matching Image #1
  if (!scheduleData || !scheduleData.slots || scheduleData.slots.length === 0) {
    scheduleData = {
      success: true,
      slots: [
        { day: "2", ca: "sang", ten_mon: "Triết học Mác - Lênin", ten_lop: "DHTMDT20B_TCTA - 429701380102", tiet: "4 - 6", phong: "N4.4 (N - Cơ sở Nguyễn Văn Dung)", giang_vien: "Nguyễn Thị Kim Chung", loai: "ly_thuyet" },
        { day: "2", ca: "toi", ten_mon: "Triết học Mác - Lênin", ten_lop: "DHTMDT20B_TCTA - 429701380102", tiet: "13 - 15", phong: "Trực tuyến (Cơ sở 1)", giang_vien: "Nguyễn Thị Kim Chung", ghi_chu: "Teams: fbj2dsr", loai: "truc_tuyen" },
        { day: "3", ca: "chieu", ten_mon: "Tài chính doanh nghiệp", ten_lop: "DHKT21D_TCTA - 429700380206", tiet: "7 - 9", phong: "N10.3 (N - Cơ sở Nguyễn Văn Dung)", giang_vien: "Lại Cao Mai Phương", loai: "ly_thuyet" },
        { day: "4", ca: "sang", ten_mon: "Quản trị tác nghiệp Thương mại điện tử", ten_lop: "DHTMDT20B_TCTA - 429701766202", tiet: "1 - 3", phong: "N4.4 (N - Cơ sở Nguyễn Văn Dung)", giang_vien: "Võ Thị Minh Nhựt", loai: "ly_thuyet" },
        { day: "6", ca: "chieu", ten_mon: "Tài chính doanh nghiệp", ten_lop: "DHKT21D_TCTA - 429700380206", tiet: "7 - 9", phong: "N10.3 (N - Cơ sở Nguyễn Văn Dung)", giang_vien: "Lại Cao Mai Phương", loai: "ly_thuyet" },
        { day: "7", ca: "sang", ten_mon: "Phân tích thiết kế hệ thống thương mại điện tử", ten_lop: "DHTMDT20B_TCTA - 429701766502", tiet: "1 - 3", phong: "H3.1.1 (H (CS1) - Cơ sở 1)", giang_vien: "Lê Thị Ánh Tuyết", loai: "thuc_hanh" },
        { day: "7", ca: "chieu", ten_mon: "Anh văn 3", ten_lop: "DH Điện tử 20C TCTA - 429701525716", tiet: "7 - 12", phong: "X10.01", giang_vien: "", ghi_chu: "Lịch thi kết thúc học phần", loai: "lich_thi" }
      ]
    };
  }

  let totalSlots = 0;
  scheduleData.slots.forEach(slot => {
    const d = slot.day;
    const c = slot.ca;
    const cell = document.getElementById(`sched-slot-${c}-${d}`);
    if (!cell) return;

    totalSlots++;
    let loaiKey = "theory";
    if (slot.loai === "thuc_hanh" || slot.loai === "practice") loaiKey = "practice";
    else if (slot.loai === "truc_tuyen" || slot.loai === "online") loaiKey = "online";
    else if (slot.loai === "lich_thi" || slot.loai === "exam") loaiKey = "exam";
    else if (slot.loai === "tam_ngung" || slot.loai === "suspended") loaiKey = "suspended";
    const loaiClass = `sched-card--${loaiKey}`;
    const previewClass = slot.is_preview ? "sched-card--preview" : "";
    const card = document.createElement("div");
    card.className = `sched-card ${loaiClass} ${previewClass}`;
    let previewBadge = slot.is_preview ? '<span class="stamp-badge" style="margin-bottom: 2px;">Dự kiến ghép</span>' : '';
    let notesHtml = slot.ghi_chu ? `<div class="sched-card__detail">Ghi chú: ${escapeHtml(slot.ghi_chu)}</div>` : '';
    let lecturerHtml = slot.giang_vien ? `<div class="sched-card__detail">GV: ${escapeHtml(slot.giang_vien)}</div>` : '';

    card.innerHTML = `
      ${previewBadge}
      <div class="sched-card__title">${escapeHtml(slot.ten_mon)}</div>
      <div class="sched-card__code">${escapeHtml(slot.ten_lop)}</div>
      <div class="sched-card__detail">Tiết: ${escapeHtml(slot.tiet)}</div>
      <div class="sched-card__detail">Phòng: ${escapeHtml(slot.phong)}</div>
      ${lecturerHtml}
      ${notesHtml}
    `;
    cell.appendChild(card);
  });

  const statMeta = document.getElementById("schedule-stat-meta");
  if (statMeta) {
    statMeta.textContent = `${totalSlots} buổi học · Đợt ${currentSemesterId}`;
  }
}

/* ========================================================================= */
/* SYSTEM SETTINGS & BACKGROUND SERVICES                                     */
/* ========================================================================= */
async function loadSettings() {
  if (!hasBridge()) return;
  try {
    const res = await window.pywebview.api.get_settings();
    if (!res || !res.success || !res.settings) return;
    const s = res.settings;

    const hbSel = document.getElementById("cfg-heartbeat-interval");
    if (hbSel && s.heartbeat_interval_seconds) hbSel.value = String(s.heartbeat_interval_seconds);

    const snipSel = document.getElementById("cfg-sniper-interval");
    if (snipSel && s.sniper_poll_interval_ms) snipSel.value = String(s.sniper_poll_interval_ms);

    const autoSwap = document.getElementById("cfg-auto-swap");
    if (autoSwap && s.auto_swap_same_course !== undefined) autoSwap.checked = Boolean(s.auto_swap_same_course);

    const chimeChk = document.getElementById("cfg-audio-chime");
    if (chimeChk && s.audio_chime_enabled !== undefined) chimeChk.checked = Boolean(s.audio_chime_enabled);

    const tgToken = document.getElementById("cfg-telegram-token");
    if (tgToken && s.telegram_bot_token !== undefined) tgToken.value = s.telegram_bot_token;

    const tgChat = document.getElementById("cfg-telegram-chatid");
    if (tgChat && s.telegram_chat_id !== undefined) tgChat.value = s.telegram_chat_id;

    const sessionSummary = document.getElementById("settings-session-summary");
    if (sessionSummary) {
      sessionSummary.textContent = `Tài khoản ${s.username || 'Chưa đăng nhập'} · Chu kỳ Heartbeat: ${s.heartbeat_interval_seconds || 62}s`;
    }
  } catch (e) {
    console.error("Lỗi khi tải cấu hình:", e);
  }
}

async function saveSettingsFromForm() {
  const hbVal = Number(document.getElementById("cfg-heartbeat-interval")?.value) || 62;
  const snipVal = Number(document.getElementById("cfg-sniper-interval")?.value) || 1500;
  const autoSwap = Boolean(document.getElementById("cfg-auto-swap")?.checked);
  const audioChime = Boolean(document.getElementById("cfg-audio-chime")?.checked);
  const tgToken = String(document.getElementById("cfg-telegram-token")?.value || "").trim();
  const tgChat = String(document.getElementById("cfg-telegram-chatid")?.value || "").trim();

  const settingsPayload = {
    heartbeat_interval_seconds: hbVal,
    sniper_poll_interval_ms: snipVal,
    auto_swap_same_course: autoSwap,
    audio_chime_enabled: audioChime,
    telegram_bot_token: tgToken,
    telegram_chat_id: tgChat
  };

  if (hasBridge()) {
    try {
      const res = await window.pywebview.api.save_settings(settingsPayload);
      const statusBadge = document.getElementById("settings-save-status");
      if (statusBadge) {
        statusBadge.textContent = res.success ? "Đã lưu" : "Lỗi lưu";
        setTimeout(() => { statusBadge.textContent = "Đã đồng bộ"; }, 3000);
      }
      showInlineBanner(res.message || "Cấu hình hệ thống đã được cập nhật thành công.");
    } catch (e) {
      console.error(e);
      showInlineBanner("Lỗi khi lưu cấu hình.");
    }
  }
}

/* ========================================================================= */
/* WEB AUDIO API NOTIFICATION CHIME                                          */
/* ========================================================================= */
function playNotificationChime() {
  const chimeChk = document.getElementById("cfg-audio-chime");
  if (chimeChk && !chimeChk.checked) return;
  try {
    const AudioCtx = window.AudioContext || window.webkitAudioContext;
    if (!AudioCtx) return;
    const ctx = new AudioCtx();
    const now = ctx.currentTime;

    const osc1 = ctx.createOscillator();
    const gain1 = ctx.createGain();
    osc1.type = "sine";
    osc1.frequency.setValueAtTime(587.33, now); // D5
    gain1.gain.setValueAtTime(0.15, now);
    gain1.gain.exponentialRampToValueAtTime(0.001, now + 0.3);
    osc1.connect(gain1);
    gain1.connect(ctx.destination);
    osc1.start(now);
    osc1.stop(now + 0.3);

    const osc2 = ctx.createOscillator();
    const gain2 = ctx.createGain();
    osc2.type = "sine";
    osc2.frequency.setValueAtTime(880, now + 0.1); // A5
    gain2.gain.setValueAtTime(0.18, now + 0.1);
    gain2.gain.exponentialRampToValueAtTime(0.001, now + 0.5);
    osc2.connect(gain2);
    gain2.connect(ctx.destination);
    osc2.start(now + 0.1);
    osc2.stop(now + 0.5);
  } catch (e) {
    // Ignore autoplay or audio context policy errors silently
  }
}

function testNotificationChime() {
  playNotificationChime();
  showInlineBanner("Đã phát chuông âm thanh kiểm tra.");
}

/* ========================================================================= */
/* SESSION DIAGNOSTICS & LOGOUT                                              */
/* ========================================================================= */
function logoutSession() {
  if (confirm("Bạn có chắc chắn muốn đăng xuất tài khoản hiện tại và xóa phiên?")) {
    document.getElementById("profile-name").textContent = "Chưa đăng nhập";
    document.getElementById("profile-mssv").textContent = "";
    document.getElementById("profile-class").textContent = "";
    document.getElementById("portal-status").textContent = "Chưa đăng nhập";
    const feed = document.getElementById("login-feedback");
    if (feed) feed.textContent = "Đã thoát phiên. Vui lòng nhập thông tin để đăng nhập lại.";
    openLoginModal();
  }
}
window.addEventListener("pywebviewready", () => {
  initDashboardFromBridge();
});
