/**
 * 精灵图鉴 Web 版 —— 前端逻辑
 * 纯原生 JS，零依赖
 */

// ── 全局状态 ──────────────────────────
const state = {
  currentMode: 'search',   // 'search' | 'type' | 'top'
  currentQuery: '',
  currentStat: 'HP',
  topN: 20,
};

// ── DOM 引用 ──────────────────────────
const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);

const searchInput = $('#searchInput');
const searchBtn = $('#searchBtn');
const totalCount = $('#totalCount');
const resultTitle = $('#resultTitle');
const resultCount = $('#resultCount');
const tableBody = $('#tableBody');
const resultTable = $('#resultTable');
const emptyState = $('#emptyState');
const loadingEl = $('#loading');
const typeTags = $('#typeTags');
const statButtons = $('#statButtons');
const detailModal = $('#detailModal');
const detailContent = $('#detailContent');
const closeBtn = $('.close');

// ── 初始化 ──────────────────────────
async function init() {
  await loadTotalCount();
  await loadStatOptions();
  await loadCommonTypes();

  // 搜索事件
  searchBtn.addEventListener('click', doSearch);
  searchInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') doSearch();
  });

  // 弹窗关闭
  closeBtn.addEventListener('click', closeModal);
  detailModal.addEventListener('click', (e) => {
    if (e.target === detailModal) closeModal();
  });
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') closeModal();
  });
}

async function loadTotalCount() {
  try {
    const res = await fetch('/api/monsters/count');
    const data = await res.json();
    totalCount.textContent = `共 ${data.count.toLocaleString()} 只精灵`;
  } catch {
    totalCount.textContent = '加载失败';
  }
}

async function loadStatOptions() {
  try {
    const res = await fetch('/api/monsters/stats');
    const data = await res.json();
    statButtons.innerHTML = data.stats.map(s =>
      `<button class="stat-btn" data-stat="${s.key}">${s.label}</button>`
    ).join('');

    // 点击事件
    statButtons.querySelectorAll('.stat-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        state.currentMode = 'top';
        state.currentStat = btn.dataset.stat;
        highlightStat();
        loadTopN(state.currentStat, state.topN);
      });
    });
  } catch (e) {
    console.error('加载属性列表失败:', e);
  }
}

async function loadCommonTypes() {
  // 赛尔号单属性（顺序与数据库 Type ID 一致）
  const types = ['草', '水', '火', '飞行', '电', '机械', '地面',
                 '普通', '冰', '超能', '战斗', '光', '暗影', '神秘',
                 '龙', '圣灵', '次元', '远古', '邪灵', '自然', '混沌'];
  typeTags.innerHTML = types.map(t =>
    `<span class="type-tag" data-type="${t}">${t}</span>`
  ).join('');

  typeTags.querySelectorAll('.type-tag').forEach(tag => {
    tag.addEventListener('click', () => {
      state.currentMode = 'type';
      state.currentQuery = tag.dataset.type;
      highlightType();
      loadByType(tag.dataset.type);
    });
  });
}

// ── 数据加载 ──────────────────────────

async function doSearch() {
  const q = searchInput.value.trim();
  if (!q) return;

  state.currentMode = 'search';
  state.currentQuery = q;
  clearHighlights();
  showLoading();

  try {
    const res = await fetch(`/api/monsters/search?q=${encodeURIComponent(q)}`);
    const data = await res.json();
    renderResults(data.results, `搜索 "${q}"`, data.count);
  } catch (e) {
    showError('搜索失败，请检查网络连接');
  }
}

async function loadByType(element) {
  showLoading();
  try {
    const res = await fetch(`/api/monsters/type?element=${encodeURIComponent(element)}`);
    const data = await res.json();
    renderResults(data.results, `${element}系精灵`, data.count);
  } catch {
    showError('筛选失败');
  }
}

async function loadTopN(stat, n) {
  showLoading();
  try {
    const res = await fetch(`/api/monsters/top?stat=${stat}&n=${n}`);
    const data = await res.json();
    renderResults(data.results, `${data.label} Top ${n}`, data.count);
  } catch {
    showError('加载失败');
  }
}

// ── 渲染 ──────────────────────────

function renderResults(results, title, count) {
  hideLoading();
  emptyState.classList.add('hidden');

  if (!results || results.length === 0) {
    resultTitle.textContent = title;
    resultCount.textContent = '无结果';
    resultTable.classList.add('hidden');
    emptyState.classList.remove('hidden');
    emptyState.querySelector('p').textContent = '没有找到匹配的精灵';
    return;
  }

  resultTitle.textContent = title;
  resultCount.textContent = `共 ${count} 条`;
  resultTable.classList.remove('hidden');

  tableBody.innerHTML = results.map(r => `
    <tr onclick="showDetail(${r.ID})" title="点击查看详情">
      <td class="monster-id">#${r.ID}</td>
      <td class="monster-name">${r.DefName || ''}</td>
      <td>${r.Type || ''}</td>
      <td>${r.HP ?? '-'}</td>
      <td>${r.Atk ?? '-'}</td>
      <td>${r.Def ?? '-'}</td>
      <td>${r.SpAtk ?? '-'}</td>
      <td>${r.SpDef ?? '-'}</td>
      <td>${r.Spd ?? '-'}</td>
    </tr>
  `).join('');
}

// ── 弹窗 ──────────────────────────

async function showDetail(id) {
  try {
    const [monRes, moveRes] = await Promise.all([
      fetch(`/api/monsters/${id}`),
      fetch(`/api/monsters/${id}/moves`),
    ]);

    if (!monRes.ok) throw new Error('未找到');

    const monster = await monRes.json();
    const moveData = await moveRes.json();

    detailContent.innerHTML = `
      <div class="detail-header">
        <h2>#${monster.ID} ${monster.DefName}</h2>
        <span class="detail-id">${monster.Type || '未知属性'}</span>
      </div>
      <div class="detail-stats">
        <div class="stat-item">
          <div class="stat-label">体力</div>
          <div class="stat-value">${monster.HP || '-'}</div>
        </div>
        <div class="stat-item">
          <div class="stat-label">攻击</div>
          <div class="stat-value">${monster.Atk || '-'}</div>
        </div>
        <div class="stat-item">
          <div class="stat-label">防御</div>
          <div class="stat-value">${monster.Def || '-'}</div>
        </div>
        <div class="stat-item">
          <div class="stat-label">特攻</div>
          <div class="stat-value">${monster.SpAtk || '-'}</div>
        </div>
        <div class="stat-item">
          <div class="stat-label">特防</div>
          <div class="stat-value">${monster.SpDef || '-'}</div>
        </div>
        <div class="stat-item">
          <div class="stat-label">速度</div>
          <div class="stat-value">${monster.Spd || '-'}</div>
        </div>
      </div>
      ${moveData.moves && moveData.moves.length > 0 ? `
        <div class="detail-section">
          <h3>技能列表 (${moveData.count})</h3>
          <ul class="move-list">
            ${moveData.moves.map(m => `
              <li>
                <span>
                  <span class="move-name">${m.Name || '?'}</span>
                  <span style="color:var(--text-dim);font-size:0.75rem"> ${m.Type || ''} ${m.Category || ''}</span>
                </span>
                <span class="move-info">
                  威力:${m.Power || '-'} PP:${m.MaxPP || '-'} 命中:${m.Accuracy || '-'}
                </span>
              </li>
            `).join('')}
          </ul>
        </div>
      ` : '<p style="color:var(--text-dim)">暂无技能数据</p>'}
    `;

    detailModal.classList.remove('hidden');
  } catch {
    alert('加载详情失败');
  }
}

function closeModal() {
  detailModal.classList.add('hidden');
}

// ── UI 辅助 ──────────────────────────

function showLoading() {
  loadingEl.classList.remove('hidden');
  resultTable.classList.add('hidden');
  emptyState.classList.add('hidden');
}

function hideLoading() {
  loadingEl.classList.add('hidden');
}

function showError(msg) {
  hideLoading();
  emptyState.classList.remove('hidden');
  emptyState.querySelector('p').textContent = msg;
}

function highlightStat() {
  statButtons.querySelectorAll('.stat-btn').forEach(b => {
    b.classList.toggle('active', b.dataset.stat === state.currentStat);
  });
  typeTags.querySelectorAll('.type-tag').forEach(t => t.classList.remove('active'));
}

function highlightType() {
  typeTags.querySelectorAll('.type-tag').forEach(t => {
    t.classList.toggle('active', t.dataset.type === state.currentQuery);
  });
  statButtons.querySelectorAll('.stat-btn').forEach(b => b.classList.remove('active'));
}

function clearHighlights() {
  typeTags.querySelectorAll('.type-tag').forEach(t => t.classList.remove('active'));
  statButtons.querySelectorAll('.stat-btn').forEach(b => b.classList.remove('active'));
}

// ── 启动 ──────────────────────────
init();
