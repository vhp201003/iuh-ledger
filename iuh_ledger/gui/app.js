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
    tabSniper.textContent = sniperActive ? `Trạm giám sát (${count}) [Đang quét]` : `Trạm giám sát (${count})`;
  }
  if (heading) {
    heading.textContent = `Hàng đợi mục tiêu giám sát (${count})`;
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

  const schedSec = document.getElementById("view-schedule");
  if (schedSec && !schedSec.hidden) {
    loadWeeklySchedule();
  }
  const regSec = document.getElementById("view-registered");
  if (regSec && !regSec.hidden) {
    loadRegisteredCourses();
  }

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
          <div class="drawer-inner-card">
            <div class="drawer-toolbar">
              <span>Chi tiết học phần ${escapeHtml(tenMon)} (${escapeHtml(maHp)})</span>
              <span>Chế độ xem trước</span>
            </div>
            <table class="ledger-table drawer-subtable" aria-label="Danh sách lớp học phần ${escapeAttr(tenMon)}">
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
                      <div class="schedule-line">LT: Thứ 2 (Tiết 1 - 3), Phòng B2.04</div>
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
                      <button type="button" class="btn" onclick="addTargetToQueue('${escapeAttr(currentSemesterId)}', '${escapeAttr(maMon)}', '${escapeAttr(maHp)}', '${escapeAttr(tenMon)}', 'GUID_${escapeAttr(maMon)}', 'DHLOP_${escapeAttr(maMon)}', null, ${currentLoaiDk}, '')">Thêm giám sát</button>
                      <button type="button" class="btn" onclick="previewClassOnSchedule('${escapeAttr(currentSemesterId)}', '${escapeAttr(maMon)}', '${escapeAttr(maHp)}01', '${escapeAttr(tenMon)}', 'GUID_${escapeAttr(maMon)}', 'DHLOP_${escapeAttr(maMon)}', null)">Xem thử TKB</button>
                    </div>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
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
          <div class="drawer-inner-card">
            <div class="drawer-toolbar">
              <span>Đã đồng bộ ${rows.length} nhóm lớp cho học phần ${escapeHtml(tenMon)}</span>
              <button type="button" class="btn" onclick="event.stopPropagation(); inspectSubjectClasses('${escapeAttr(maMon)}', '${escapeAttr(maHp)}', '${escapeAttr(tenMon)}', '${escapeAttr(maMonCha || "")}', true)">Làm mới sĩ số</button>
            </div>
            <table class="ledger-table drawer-subtable" aria-label="Danh sách lớp học phần ${escapeAttr(tenMon)}">
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
          </div>
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
    const sniperLabel = avail > 0 ? "Thêm giám sát" : "Tự động chờ lớp";
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
            <button type="button" class="btn" onclick="previewClassOnSchedule('${escapeAttr(currentSemesterId)}', '${escapeAttr(maMon)}', '${escapeAttr(r.ma_lhp || maHp)}', '${escapeAttr(tenMon)}', '${escapeAttr(r.guid_lhp)}', '${escapeAttr(r.ten_lop)}', ${nhomArg})">Xem thử TKB</button>
          </div>
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

function lookupClassRowMeta(maMon, guidLhp, normNhom) {
  // 1. Search in subjectClassesCache
  for (const [, res] of subjectClassesCache.entries()) {
    const rows = (res && res.rows) || [];
    const match = rows.find(r =>
      String(r.guid_lhp) === String(guidLhp) &&
      ((r.nhom_th ?? null) === normNhom || String(r.nhom_th || "") === String(normNhom || ""))
    );
    if (match) return match;
  }
  // 2. Fallback: scrape from rendered DOM row in drawer
  const btn = document.querySelector(`button[onclick*="previewClassOnSchedule"][onclick*="${guidLhp}"]`);
  const tr = btn ? btn.closest("tr") : null;
  if (tr) {
    const lines = Array.from(tr.querySelectorAll(".schedule-line")).map(el => el.textContent.trim());
    const ltLine = lines.find(l => l.startsWith("LT:")) || "";
    const thLine = lines.find(l => l.startsWith("TH:")) || "";
    const gvEl = tr.querySelector(".lecturer-name");
    return {
      guid_lhp: guidLhp,
      nhom_th: normNhom,
      lich_lt: ltLine.replace(/^LT:\s*/i, "").trim(),
      lich_th: thLine.replace(/^TH:\s*/i, "").trim(),
      giang_vien: gvEl ? gvEl.textContent.replace(/^LT:\s*/i, "").trim() : "TS Phan Trần Minh Khuê",
      schedules: []
    };
  }
  // 3. Static default schedule lines for demo GUIDs
  if (String(guidLhp) === "CqLpKkViKTvbXLsCooUfPg") {
    return {
      guid_lhp: guidLhp,
      nhom_th: normNhom,
      lich_lt: "Thứ 3 (Tiết 7 - 9), Phòng N4.6 CLC",
      lich_th: normNhom === 2 ? "Thứ 6 (Tiết 4 - 6), Phòng H7.02" : "Thứ 5 (Tiết 1 - 3), Phòng H7.01",
      giang_vien: "TS Phan Trần Minh Khuê",
      schedules: []
    };
  }
  if (String(guidLhp) === "sLeefKjYzKhtMOL0u6nFtg") {
    return {
      guid_lhp: guidLhp,
      nhom_th: null,
      lich_lt: "Thứ 4 (Tiết 1 - 3), Phòng H7.02",
      lich_th: "",
      giang_vien: "DH Lìu Cẩm Bình",
      schedules: []
    };
  }
  return {
    guid_lhp: guidLhp,
    nhom_th: normNhom,
    lich_lt: "Thứ 2 (Tiết 1 - 3), Phòng B2.04",
    lich_th: "",
    giang_vien: "PGS.TS Nguyễn Minh Tuấn",
    schedules: []
  };
}

async function addTargetToQueue(idDot, maMon, maHp, tenMon, guidLhp, tenLop, nhomTh = null, loaiDk = 1, maMonCha = "") {
  const normNhom = (nhomTh !== null && nhomTh !== undefined && String(nhomTh).trim() !== "" && String(nhomTh) !== "null")
    ? Number(nhomTh)
    : null;
  const targetKey = `${guidLhp}_${normNhom !== null ? normNhom : 0}`;
  const groupText = normNhom !== null ? `Nhóm TH ${normNhom}` : "Thuần LT";
  const loaiText = LOAI_DK_LABELS[loaiDk || currentLoaiDk] || "Học mới";
  const rowMeta = lookupClassRowMeta(maMon, guidLhp, normNhom);

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
        maMonCha || "",
        rowMeta.schedules || [],
        rowMeta.lich_lt || "",
        rowMeta.lich_th || "",
        rowMeta.giang_vien || ""
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
        registered: false,
        schedules: rowMeta.schedules || [],
        lich_lt: rowMeta.lich_lt || "",
        lich_th: rowMeta.lich_th || "",
        giang_vien: rowMeta.giang_vien || ""
      });
    }
  }

  renderSniperStationTargets();
  showInlineBanner(`Đã thêm ${tenMon} (${tenLop}, ${groupText}) vào Trạm giám sát đăng ký.`);
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
    if (btn) btn.textContent = "Dừng tự động ghi danh";
    if (badge) {
      badge.textContent = "Đang giám sát";
      badge.className = "stamp-badge";
    }
    appendTelemetryLog(`Đã kích hoạt vòng lặp giám sát tự động (Chu kỳ ${intervalMs} ms)…`);
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
    if (btn) btn.textContent = "Kích hoạt tự động ghi danh";
    if (badge) {
      badge.textContent = "Tạm dừng";
      badge.className = "stamp-badge stamp-badge--neutral";
    }
    appendTelemetryLog("Đã tạm dừng vòng lặp giám sát tự động.");
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
  label.textContent = radarActive ? "Đang duy trì phiên" : "Duy trì phiên nền";
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
      <tr class="ledger-row" tabindex="0" onclick="inspectRegisteredSchedule('${escapeAttr(c.id_lhp_dk)}', '${escapeAttr(c.guid_lhp || c.guid)}', '${escapeAttr(c.ten_mon)}', '${escapeAttr(c.lop_du_kien)}')">
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
let currentScheduleMode = "preview"; // "preview" (Official + Watchdog/Preview) or "official"
let previewSandboxTargets = []; // Multi-subject preview sandbox (replaces same ma_mon, accumulates distinct ma_mon)
let _returnContext = null; // Stores { maMon, scrollTop } when jumping from Open Subjects to Timetable

function setScheduleMode(mode) {
  currentScheduleMode = mode;
  const btnOfficial = document.getElementById("btn-sched-mode-official");
  const btnPreview = document.getElementById("btn-sched-mode-preview");
  if (btnOfficial) btnOfficial.classList.toggle("active", mode === "official");
  if (btnPreview) btnPreview.classList.toggle("active", mode === "preview");
  loadWeeklySchedule();
}

function returnToSubjectDrawer() {
  switchView("open");
  if (_returnContext) {
    const targetRow = document.querySelector(`tr[data-mamh="${_returnContext.maMon}"]`);
    const drawer = document.getElementById("drawer-" + _returnContext.maMon);
    if (drawer) drawer.hidden = false;
    if (targetRow) {
      targetRow.classList.add("ledger-row--selected");
      targetRow.setAttribute("aria-expanded", "true");
    }
    setTimeout(() => {
      window.scrollTo({ top: _returnContext.scrollTop || 0, behavior: "smooth" });
    }, 40);
  }
}

function previewClassOnSchedule(idDot, maMon, maHp, tenMon, guidLhp, tenLop, nhomTh = null) {
  const normNhom = (nhomTh !== null && nhomTh !== undefined && String(nhomTh).trim() !== "" && String(nhomTh) !== "null")
    ? Number(nhomTh)
    : null;
  const targetKey = `${guidLhp}_${normNhom !== null ? normNhom : 0}`;
  const rowMeta = lookupClassRowMeta(maMon, guidLhp, normNhom);

  // Capture return context so user can jump back to the exact subject drawer in 1 click
  _returnContext = {
    maMon: String(maMon),
    scrollTop: window.scrollY || document.documentElement.scrollTop || 0
  };
  const btnReturn = document.getElementById("btn-return-to-open");
  if (btnReturn) {
    btnReturn.hidden = false;
    btnReturn.textContent = `Quay lại: ${tenMon}`;
  }

  const newEntry = {
    target_key: targetKey,
    id_dot: String(idDot || currentSemesterId),
    ma_mon: String(maMon),
    ma_hp: String(maHp),
    ten_mon: String(tenMon),
    guid_lhp: String(guidLhp),
    ten_lop: String(tenLop),
    nhom_th: normNhom,
    loai_dk: currentLoaiDk,
    ma_mon_cha: rowMeta.ma_mon_cha || "",
    schedules: rowMeta.schedules || [],
    lich_lt: rowMeta.lich_lt || "",
    lich_th: rowMeta.lich_th || "",
    giang_vien: rowMeta.giang_vien || "",
    is_temp_preview: true
  };

  // Replace-per-subject semantics (Kongming recommendation): replace existing preview of same ma_mon, accumulate across different subjects
  const existingIdx = previewSandboxTargets.findIndex(item => String(item.ma_mon) === String(maMon));
  if (existingIdx !== -1) {
    previewSandboxTargets[existingIdx] = newEntry;
  } else {
    previewSandboxTargets.push(newEntry);
  }

  currentScheduleMode = "preview";
  const btnOfficial = document.getElementById("btn-sched-mode-official");
  const btnPreview = document.getElementById("btn-sched-mode-preview");
  if (btnOfficial) btnOfficial.classList.remove("active");
  if (btnPreview) btnPreview.classList.add("active");
  switchView("schedule");
}

function removePreviewFromSandbox(targetKey) {
  previewSandboxTargets = previewSandboxTargets.filter(item => item.target_key !== targetKey);
  loadWeeklySchedule();
}

function clearTemporaryPreview() {
  previewSandboxTargets = [];
  loadWeeklySchedule();
}

function parseStringScheduleSlotsForBrowser(p) {
  const out = [];
  const gv = p.giang_vien || "TS Phan Trần Minh Khuê";
  const fullLop = p.ma_hp && !String(p.ten_lop).includes(String(p.ma_hp))
    ? `${p.ten_lop} - ${p.ma_hp}`
    : String(p.ten_lop);
  const pairs = [
    { loai: "ly_thuyet", raw: p.lich_lt || "", ghi_chu: "" },
    { loai: "thuc_hanh", raw: p.lich_th || "", ghi_chu: p.nhom_th ? `Nhóm TH ${p.nhom_th}` : "Thực hành" }
  ];
  pairs.forEach(pair => {
    if (!pair.raw) return;
    String(pair.raw).split("|").forEach(seg => {
      const mDay = seg.match(/(Thứ\s*[2-7]|Chủ\s*nhật)/i);
      const mTiet = seg.match(/Tiết\s*(\d+)(?:\s*(?:->|-)\s*(\d+))?/i);
      if (!mDay || !mTiet) return;
      const dayRaw = mDay[1].toLowerCase();
      const dayCode = dayRaw.includes("chủ") ? "CN" : dayRaw.replace(/\D+/g, "");
      const st = parseInt(mTiet[1], 10);
      const en = mTiet[2] ? parseInt(mTiet[2], 10) : st;
      const ca = st <= 6 ? "sang" : (st <= 12 ? "chieu" : "toi");
      const mPhong = seg.match(/Phòng\s*([^|·,]+)/i);
      const phong = mPhong ? mPhong[1].trim() : "N4.6 CLC";
      out.push({
        day: dayCode,
        ca: ca,
        ten_mon: p.ten_mon || "Học phần dự kiến",
        ma_lhp: p.ma_hp || "",
        ten_lop: fullLop,
        tiet: `${st} - ${en}`,
        tiet_start: st,
        tiet_end: en,
        phong: phong,
        giang_vien: gv,
        ghi_chu: pair.ghi_chu,
        loai: pair.loai,
        is_preview: true,
        target_key: p.target_key
      });
    });
  });
  return out;
}

function renderSandboxTray(previewClasses, slots) {
  const tray = document.getElementById("schedule-sandbox-tray");
  const titleEl = document.getElementById("sandbox-tray-title");
  const gridEl = document.getElementById("sandbox-tray-cards");
  if (!tray || !gridEl) return;

  if (currentScheduleMode !== "preview" || !previewClasses || previewClasses.length === 0) {
    tray.hidden = true;
    gridEl.innerHTML = "";
    return;
  }

  tray.hidden = false;
  if (titleEl) {
    titleEl.textContent = `Khay ướm thử & ghép lịch (${previewClasses.length} lớp đang ướm trên Thời khóa biểu)`;
  }

  gridEl.innerHTML = previewClasses.map(p => {
    const tKey = p.target_key || `${p.guid_lhp}_${p.nhom_th !== null && p.nhom_th !== undefined ? p.nhom_th : 0}`;
    const groupText = p.nhom_th !== null && p.nhom_th !== undefined ? `Nhóm TH ${p.nhom_th}` : "Thuần LT";
    const pSlots = (slots || []).filter(s => s.is_preview && (s.target_key === tKey || s.ten_mon === p.ten_mon));
    const conflicts = [];
    pSlots.forEach(s => {
      if (s.has_conflict && Array.isArray(s.conflict_with)) {
        s.conflict_with.forEach(cName => {
          if (!conflicts.includes(cName)) conflicts.push(cName);
        });
      }
    });
    const hasConflict = conflicts.length > 0;
    const cardClass = hasConflict ? "sandbox-card sandbox-card--conflict" : "sandbox-card";
    const statusBadge = hasConflict
      ? `<span class="stamp-badge stamp-badge--conflict">Trùng tiết: ${escapeHtml(conflicts.join(", "))}</span>`
      : `<span class="stamp-badge">Khớp lịch (0 trùng)</span>`;

    const schedSummary = [
      p.lich_lt ? `LT: ${p.lich_lt}` : "",
      p.lich_th ? `TH: ${p.lich_th}` : ""
    ].filter(Boolean).join(" | ") || `${pSlots.length} buổi/tuần trên lưới TKB`;

    const inWatchdog = sniperTargets.some(t => (t.target_key || `${t.guid_lhp}_${t.nhom_th || 0}`) === tKey);
    const nhomArg = (p.nhom_th !== null && p.nhom_th !== undefined) ? Number(p.nhom_th) : "null";

    return `
      <div class="${cardClass}">
        <div class="sandbox-card__top">
          <div>
            <div class="sandbox-card__title">${escapeHtml(p.ten_mon)}</div>
            <div class="sandbox-card__meta mono">${escapeHtml(p.ten_lop)} (${escapeHtml(groupText)})</div>
          </div>
          ${statusBadge}
        </div>
        <div class="sandbox-card__meta">${escapeHtml(schedSummary)}</div>
        <div class="btn-row-actions">
          <button type="button" class="btn btn--accent-outline" onclick="triggerDirectRegister('${escapeAttr(p.id_dot || currentSemesterId)}', '${escapeAttr(p.guid_lhp)}', ${nhomArg}, ${p.loai_dk || currentLoaiDk}, '${escapeAttr(p.ma_mon_cha || "")}', '${escapeAttr(p.ten_mon)}', '${escapeAttr(p.ten_lop)}')">Đăng ký ngay</button>
          ${inWatchdog
            ? `<span class="stamp-badge stamp-badge--neutral">Đã trong Trạm giám sát</span>`
            : `<button type="button" class="btn" onclick="addTargetToQueue('${escapeAttr(p.id_dot || currentSemesterId)}', '${escapeAttr(p.ma_mon)}', '${escapeAttr(p.ma_hp)}', '${escapeAttr(p.ten_mon)}', '${escapeAttr(p.guid_lhp)}', '${escapeAttr(p.ten_lop)}', ${nhomArg}, ${p.loai_dk || currentLoaiDk}, '${escapeAttr(p.ma_mon_cha || "")}'); loadWeeklySchedule();">Thêm giám sát</button>`
          }
          <button type="button" class="btn" onclick="removePreviewFromSandbox('${escapeAttr(tKey)}')">Bỏ ướm</button>
        </div>
      </div>
    `;
  }).join("");
}

async function loadWeeklySchedule() {
  const days = ["2", "3", "4", "5", "6", "7", "CN"];
  const cas = ["sang", "chieu", "toi"];
  cas.forEach(c => {
    days.forEach(d => {
      const cell = document.getElementById(`sched-slot-${c}-${d}`);
      if (cell) cell.innerHTML = "";
    });
  });

  let previewClasses = [];
  if (currentScheduleMode === "preview") {
    if (sniperTargets && sniperTargets.length > 0) {
      previewClasses = sniperTargets.filter(t => String(t.id_dot || currentSemesterId) === String(currentSemesterId));
    }
    if (previewSandboxTargets && previewSandboxTargets.length > 0) {
      previewSandboxTargets.forEach(tempItem => {
        const exists = previewClasses.some(
          p => p.guid_lhp === tempItem.guid_lhp && (p.nhom_th ?? null) === (tempItem.nhom_th ?? null)
        );
        if (!exists) {
          previewClasses.push(tempItem);
        }
      });
    }
  }

  let scheduleData = null;
  if (hasBridge()) {
    try {
      const res = await window.pywebview.api.get_weekly_schedule(
        currentSemesterId,
        previewClasses.length > 0 ? previewClasses : null
      );
      if (res && res.success) {
        scheduleData = res;
      }
    } catch (e) {
      console.error("Lỗi khi tải thời khóa biểu:", e);
    }
  }

  // If no bridge (browser offline preview), build realistic schedule from sample registered + preview classes
  if (!scheduleData) {
    const sampleSlots = [
      { day: "2", ca: "sang", ten_mon: "Nghiên cứu và phân tích dữ liệu thị trường", ten_lop: "DHTMDT20B_TCTA - 429701766002", tiet: "4 - 6", tiet_start: 4, tiet_end: 6, phong: "N2.2 CLC (CS Nguyễn Văn Dung)", giang_vien: "GS MINCONG TANG, ThS Đỗ Bùi Xuân Cường", thoi_gian: "05/01/2026 - 20/04/2026", loai: "ly_thuyet", is_preview: false },
      { day: "3", ca: "sang", ten_mon: "Nguyên lý lập trình Web", ten_lop: "DHTMDT20B_TCTA - 429701766102", tiet: "1 - 3", tiet_start: 1, tiet_end: 3, phong: "N4.6 CLC (CS Nguyễn Văn Dung)", giang_vien: "ThS Nguyễn Đức Cương", thoi_gian: "13/01/2026 - 07/04/2026", loai: "ly_thuyet", is_preview: false },
      { day: "3", ca: "chieu", ten_mon: "Cơ sở dữ liệu", ten_lop: "DHTMDT20B_TCTA - 429701765902", tiet: "7 - 9", tiet_start: 7, tiet_end: 9, phong: "N4.6 CLC (CS Nguyễn Văn Dung)", giang_vien: "TS Phan Trần Minh Khuê", thoi_gian: "13/01/2026 - 07/04/2026", loai: "ly_thuyet", is_preview: false },
      { day: "4", ca: "sang", ten_mon: "Cơ sở dữ liệu", ten_lop: "DHTMDT20B_TCTA - 429701765902", tiet: "4 - 6", tiet_start: 4, tiet_end: 6, phong: "H7.02 (CS1)", giang_vien: "DH Lìu Cẩm Bình", ghi_chu: "Nhóm TH 1", thoi_gian: "14/01/2026 - 08/04/2026", loai: "thuc_hanh", is_preview: false },
      { day: "5", ca: "toi", ten_mon: "Hệ thống thông tin quản lý", ten_lop: "DHTMDT20A_TCTA - 429701760701", tiet: "13 - 15", tiet_start: 13, tiet_end: 15, phong: "N1.5 CLC (CS Nguyễn Văn Dung)", giang_vien: "ThS Trần Khánh", ghi_chu: "Nhóm TH 1", thoi_gian: "15/01/2026 - 16/04/2026", loai: "thuc_hanh", is_preview: false },
      { day: "6", ca: "chieu", ten_mon: "Nguyên lý kế toán", ten_lop: "DHTMDT20B_TCTA - 429700153403", tiet: "7 - 9", tiet_start: 7, tiet_end: 9, phong: "N4.6 CLC (CS Nguyễn Văn Dung)", giang_vien: "TS Đỗ Thị Thu Thảo", thoi_gian: "09/01/2026 - 08/05/2026", loai: "ly_thuyet", is_preview: false },
      { day: "6", ca: "chieu", ten_mon: "Kinh tế lượng", ten_lop: "DHTMDT20B_TCTA - 429700402909", tiet: "10 - 12", tiet_start: 10, tiet_end: 12, phong: "N4.6 CLC (CS Nguyễn Văn Dung)", giang_vien: "ThS Nguyễn Thị Ngọc Hoa", thoi_gian: "09/01/2026 - 24/04/2026", loai: "ly_thuyet", is_preview: false },
      { day: "6", ca: "toi", ten_mon: "Hệ thống thông tin quản lý", ten_lop: "DHTMDT20A_TCTA - 429701760701", tiet: "13 - 15", tiet_start: 13, tiet_end: 15, phong: "N1.3 CLC (CS Nguyễn Văn Dung)", giang_vien: "ThS Trần Khánh", thoi_gian: "09/01/2026 - 10/04/2026", loai: "ly_thuyet", is_preview: false },
      { day: "7", ca: "toi", ten_mon: "Nguyên lý lập trình Web", ten_lop: "DHTMDT20B_TCTA - 429701766102", tiet: "13 - 15", tiet_start: 13, tiet_end: 15, phong: "H7.01 (CS1)", giang_vien: "DH Lìu Cẩm Bình", ghi_chu: "Nhóm TH 1", thoi_gian: "17/01/2026 - 11/04/2026", loai: "thuc_hanh", is_preview: false }
    ];
    if (previewClasses.length > 0) {
      previewClasses.forEach(p => {
        const parsedPreview = parseStringScheduleSlotsForBrowser(p);
        parsedPreview.forEach(ps => sampleSlots.push(ps));
      });
      // Detect overlaps in browser fallback mode
      for (let i = 0; i < sampleSlots.length; i++) {
        const s1 = sampleSlots[i];
        s1.has_conflict = false;
        s1.conflict_with = [];
        for (let j = 0; j < sampleSlots.length; j++) {
          if (i === j || s1.day !== sampleSlots[j].day) continue;
          const s2 = sampleSlots[j];
          if (s1.ten_mon === s2.ten_mon && s1.is_preview === s2.is_preview) continue;
          if (Math.max(s1.tiet_start, s2.tiet_start) <= Math.min(s1.tiet_end, s2.tiet_end)) {
            s1.has_conflict = true;
            if (!s1.conflict_with.includes(s2.ten_mon)) s1.conflict_with.push(s2.ten_mon);
          }
        }
      }
    }
    scheduleData = {
      success: true,
      registered_count: 6,
      conflict_count: sampleSlots.filter(s => s.has_conflict).length,
      slots: sampleSlots
    };
  }

  const slots = (scheduleData.slots || []).slice().sort((a, b) => (a.tiet_start || 0) - (b.tiet_start || 0));
  let totalSlots = 0;
  let previewCount = 0;
  let conflictCount = 0;

  renderSandboxTray(previewClasses, slots);

  slots.forEach(slot => {
    const d = slot.day;
    const c = slot.ca;
    const cell = document.getElementById(`sched-slot-${c}-${d}`);
    if (!cell) return;

    totalSlots++;
    if (slot.is_preview) previewCount++;
    if (slot.has_conflict) conflictCount++;

    let loaiKey = "theory";
    if (slot.loai === "thuc_hanh" || slot.loai === "practice") loaiKey = "practice";
    else if (slot.loai === "truc_tuyen" || slot.loai === "online") loaiKey = "online";
    else if (slot.loai === "lich_thi" || slot.loai === "exam") loaiKey = "exam";
    else if (slot.loai === "tam_ngung" || slot.loai === "suspended") loaiKey = "suspended";
    const loaiClass = `sched-card--${loaiKey}`;
    const previewClass = slot.is_preview ? "sched-card--preview" : "";
    const conflictClass = slot.has_conflict ? "sched-card--conflict" : "";

    const card = document.createElement("div");
    card.className = `sched-card ${loaiClass} ${previewClass} ${conflictClass}`.trim();

    let badgesHtml = "";
    if (slot.is_preview) {
      badgesHtml += '<span class="stamp-badge" style="margin-bottom: 2px;">Dự kiến ghép</span> ';
    }
    if (slot.has_conflict) {
      const cw = (slot.conflict_with || []).join(", ");
      badgesHtml += `<span class="stamp-badge stamp-badge--conflict" style="margin-bottom: 2px;">Trùng lịch: ${escapeHtml(cw)}</span>`;
    }

    let notesHtml = slot.ghi_chu ? `<div class="sched-card__detail">Nhóm: ${escapeHtml(slot.ghi_chu)}</div>` : '';
    let lecturerHtml = slot.giang_vien ? `<div class="sched-card__detail">GV: ${escapeHtml(slot.giang_vien)}</div>` : '';

    card.innerHTML = `
      ${badgesHtml ? `<div>${badgesHtml}</div>` : ""}
      <div class="sched-card__title">${escapeHtml(slot.ten_mon)}</div>
      <div class="sched-card__code">${escapeHtml(slot.ten_lop)}</div>
      <div class="sched-card__detail">Tiết: ${escapeHtml(slot.tiet)}</div>
      <div class="sched-card__detail">Phòng: ${escapeHtml(slot.phong)}</div>
      ${lecturerHtml}
      ${notesHtml}
    `;
    cell.appendChild(card);
  });

  const conflictBanner = document.getElementById("schedule-conflict-banner");
  if (conflictBanner) {
    if (totalSlots === 0) {
      conflictBanner.hidden = false;
      conflictBanner.textContent = `Học kỳ hiện tại (Đợt ${currentSemesterId}) chưa có môn đăng ký và chưa có lớp nào trong Khay ướm thử. Hãy bấm "Xem thử TKB" hoặc "Thêm giám sát" ở danh sách lớp mở để ướm thử lịch!`;
    } else if (conflictCount > 0) {
      conflictBanner.hidden = false;
      conflictBanner.innerHTML = `Phát hiện <strong>${conflictCount} buổi học bị trùng tiết</strong> khi ghép lớp dự kiến! Bạn có thể bấm <strong>Quay lại chọn lớp</strong> để chọn nhóm TH khác hoặc bấm <strong>Bỏ ướm</strong> trên thẻ bị trùng.`;
    } else if (currentScheduleMode === "preview" && previewCount > 0) {
      conflictBanner.hidden = false;
      conflictBanner.innerHTML = `Tất cả <strong>${previewClasses.length} lớp đang ướm thử (${previewCount} buổi học)</strong> đều hoàn toàn khớp với Thời khóa biểu hiện tại (0 trùng tiết). Bạn có thể bấm <strong>Đăng ký ngay</strong> hoặc <strong>Thêm giám sát</strong> ngay trên Khay ướm thử!`;
    } else {
      conflictBanner.hidden = true;
      conflictBanner.textContent = "";
    }
  }

  const statMeta = document.getElementById("schedule-stat-meta");
  if (statMeta) {
    const regCount = scheduleData.registered_count !== undefined ? scheduleData.registered_count : 0;
    statMeta.textContent = `${regCount} môn đã ĐK, ${totalSlots} buổi/tuần${previewCount > 0 ? ` (${previewCount} buổi dự kiến)` : ""}, Đợt ${currentSemesterId}`;
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
      sessionSummary.textContent = `Tài khoản ${s.username || 'Chưa đăng nhập'}, Chu kỳ Heartbeat: ${s.heartbeat_interval_seconds || 62}s`;
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
