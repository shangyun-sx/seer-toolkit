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
  offset: 0,               // 当前页从第几条开始（只对 search / type 有意义）
  limit: 20,               // 每页条数
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
const effectPanel = $('#effectPanel');
const typeSelect = $('#typeSelect');
const checkTypeBtn = $('#checkTypeBtn');
const pager = $('#pager');
const prevPage = $('#prevPage');
const nextPage = $('#nextPage');
const pageInfo = $('#pageInfo');
const pageSize = $('#pageSize');

// ── 初始化 ──────────────────────────
async function init() {
  await loadTotalCount();
  await loadStatOptions();
  await loadCommonTypes();
  await loadTypeOptions();

  // 搜索事件
  searchBtn.addEventListener('click', doSearch);
  searchInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') doSearch();
  });

  // 属性克制
  checkTypeBtn.addEventListener('click', checkType);

  // 翻页
  prevPage.addEventListener('click', () => {
    loadPage(Math.max(0, state.offset - state.limit));
  });
  nextPage.addEventListener('click', () => {
    loadPage(state.offset + state.limit);
  });
  pageSize.addEventListener('change', () => {
    state.limit = Number(pageSize.value);
    loadPage(0);        // 每页条数变了，回到第一页
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
      `<button class="stat-btn" data-stat="${esc(s.key)}">${esc(s.label)}</button>`
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
  // 属性列表由后端提供（database/type_chart.py），避免前后端各维护一份
  let types;
  try {
    const res = await fetch('/api/types');
    types = (await res.json()).types.map(t => t.name);
  } catch (e) {
    console.error('加载属性列表失败:', e);
    return;
  }

  typeTags.innerHTML = types.map(t =>
    `<span class="type-tag" data-type="${esc(t)}">${esc(t)}</span>`
  ).join('');

  typeTags.querySelectorAll('.type-tag').forEach(tag => {
    tag.addEventListener('click', () => selectType(tag.dataset.type));
  });
}

async function loadTypeOptions() {
  try {
    const res = await fetch('/api/types');
    const data = await res.json();
    typeSelect.innerHTML = data.types.map(t =>
      `<option value="${esc(t.name)}">${esc(t.name)} (${esc(t.name_en)})</option>`
    ).join('');
  } catch (e) {
    console.error('加载属性下拉框失败:', e);
  }
}

// ── 数据加载 ──────────────────────────

/** 拼当前查询的 URL。分页只对「搜索」和「属性筛选」有意义 —— Top N 不分页。 */
function queryUrl(offset) {
  const page = `limit=${state.limit}&offset=${offset}`;

  if (state.currentMode === 'search') {
    return `/api/monsters/search?q=${encodeURIComponent(state.currentQuery)}&${page}`;
  }
  if (state.currentMode === 'type') {
    return `/api/monsters/type?element=${encodeURIComponent(state.currentQuery)}&${page}`;
  }
  return null;
}

function currentTitle() {
  if (state.currentMode === 'search') return `搜索 "${state.currentQuery}"`;
  if (state.currentMode === 'type') return `${state.currentQuery}系精灵`;
  return '';
}

/**
 * 加载当前查询里从第 offset 条开始的那一页。
 *
 * 搜索和属性筛选都走这里 —— 以前各 fetch 一次、各 render 一次，加翻页就得
 * 改两处，索性合成一个入口。
 */
async function loadPage(offset) {
  const url = queryUrl(offset);
  if (!url) return;

  showLoading();
  try {
    const res = await fetch(url);
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || '加载失败');
    state.offset = offset;      // 成功了才记页码，失败时维持原样
    renderResults(data.results, currentTitle(), data);
  } catch (e) {
    showError(e.message || '加载失败');
  }
}

function doSearch() {
  const q = searchInput.value.trim();
  if (!q) return;

  state.currentMode = 'search';
  state.currentQuery = q;
  clearHighlights();
  loadPage(0);                  // 新搜索总是从第一页开始
}

/** 点侧边栏的属性标签 —— 按属性查精灵的入口 */
function selectType(element) {
  state.currentMode = 'type';
  state.currentQuery = element;
  highlightType();
  loadPage(0);
}

async function loadTopN(stat, n) {
  showLoading();
  try {
    const res = await fetch(`/api/monsters/top?stat=${stat}&n=${n}`);
    const data = await res.json();
    // Top N 不是分页，就是「前 N 名」，所以总数和显示数相同
    renderResults(data.results, `${data.label} Top ${n}`,
                  { total: data.count, shown: data.count });
  } catch {
    showError('加载失败');
  }
}

async function checkType() {
  const element = typeSelect.value;
  if (!element) return;

  clearHighlights();
  showLoading();
  try {
    const res = await fetch(`/api/types/effectiveness?element=${encodeURIComponent(element)}`);
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || '查询失败');
    }
    renderEffectPanel(await res.json());
  } catch (e) {
    showError(e.message || '查询失败');
  }
}

// ── 属性克制渲染 ──────────────────────────

function renderEffectRows(groups) {
  return groups.map(([label, rows, cls]) => `
    <div class="effect-row">
      <span class="effect-label">${label}</span>
      <span class="effect-tags">${
        rows && rows.length
          ? rows.map(([name, mult]) =>
              `<span class="type-tag ${cls}">${esc(name)} ${esc(mult)}x</span>`).join('')
          : '<span class="effect-none">无</span>'
      }</span>
    </div>
  `).join('');
}

function renderEffectPanel(data) {
  hideLoading();
  emptyState.classList.add('hidden');
  resultTable.classList.add('hidden');

  resultTitle.textContent = `${data.element} 系属性克制`;
  resultCount.textContent = '';

  effectPanel.classList.remove('hidden');
  effectPanel.innerHTML = `
    <div class="effect-group">
      <h3>用 ${esc(data.element)} 系技能攻击</h3>
      ${renderEffectRows([
        ['🔺 克制', data.offense.strong, 'strong'],
        ['🔹 微弱', data.offense.weak, 'weak'],
        ['🚫 无效', data.offense.immune, 'immune'],
      ])}
    </div>
    <div class="effect-group">
      <h3>${esc(data.element)} 系精灵受到攻击</h3>
      ${renderEffectRows([
        ['🔺 弱点', data.defense.weaknesses, 'strong'],
        ['🔹 抗性', data.defense.resistances, 'weak'],
        ['🚫 免疫', data.defense.immunities, 'immune'],
      ])}
    </div>
  `;
}

// ── 渲染 ──────────────────────────

// 把值插进 innerHTML / 属性之前先转义。
// 精灵名、技能名、技能描述都来自数据库文本 —— 实际数据里几乎不会出现
// & < > "，但拼 innerHTML 不做转义是错的模式；真出现时的表现是「页面白
// 一块」，很难往数据上想。顺带也修掉名字里带 & 时的显示错乱。
function esc(value) {
  if (value === null || value === undefined) return '';
  return String(value)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

// meta 形如 {total, shown}。total 才是真实总数，shown 是这一页的条数 ——
// 以前只传 len(结果)，于是搜索被 LIMIT 20 截断后界面还写着「共 20 条」。
function formatCount(meta) {
  const total = meta.total ?? meta.count ?? 0;
  const shown = meta.shown ?? total;
  return shown < total ? `显示 ${shown} / 共 ${total} 条` : `共 ${total} 条`;
}

/**
 * 翻页条。只在「搜索 / 属性筛选」且结果多于一页时出现 ——
 * 能力排行是 Top N，本来就不分页，别给它一个点了没反应的翻页条。
 */
function renderPager(meta) {
  const total = meta.total ?? 0;

  if (state.currentMode === 'top' || total <= state.limit) {
    pager.classList.add('hidden');
    return;
  }

  const page = Math.floor(state.offset / state.limit) + 1;
  const pages = Math.ceil(total / state.limit);
  const shown = meta.shown ?? 0;

  pager.classList.remove('hidden');
  pageInfo.textContent = `第 ${page} / ${pages} 页`;
  prevPage.disabled = state.offset <= 0;
  // 这一页之后没有剩余行了就到头了（用 shown 而不是 limit，最后一页可能不满）
  nextPage.disabled = state.offset + shown >= total;
}

function renderResults(results, title, meta) {
  hideLoading();
  emptyState.classList.add('hidden');
  effectPanel.classList.add('hidden');

  if (!results || results.length === 0) {
    resultTitle.textContent = title;
    resultCount.textContent = '无结果';
    resultTable.classList.add('hidden');
    pager.classList.add('hidden');
    emptyState.classList.remove('hidden');
    emptyState.querySelector('p').textContent = '没有找到匹配的精灵';
    return;
  }

  resultTitle.textContent = title;
  resultCount.textContent = formatCount(meta);
  resultTable.classList.remove('hidden');
  renderPager(meta);

  tableBody.innerHTML = results.map(r => `
    <tr onclick="showDetail(${r.ID})" title="点击查看详情">
      <td class="monster-id">#${r.ID}</td>
      <td class="monster-name">${esc(r.DefName)}</td>
      <td>${esc(r.TypeName || r.Type)}</td>
      <td>${r.HP ?? '-'}</td>
      <td>${r.Atk ?? '-'}</td>
      <td>${r.Def ?? '-'}</td>
      <td>${r.SpAtk ?? '-'}</td>
      <td>${r.SpDef ?? '-'}</td>
      <td>${r.Spd ?? '-'}</td>
      <td>${r.Total ?? '-'}</td>
    </tr>
  `).join('');
}

// ── 弹窗 ──────────────────────────

async function showDetail(id) {
  try {
    const [monRes, moveRes, effRes] = await Promise.all([
      fetch(`/api/monsters/${id}`),
      fetch(`/api/monsters/${id}/moves?effects=true`),
      fetch(`/api/monsters/${id}/effectiveness`),
    ]);

    if (!monRes.ok) throw new Error('未找到');

    const monster = await monRes.json();
    const moveData = await moveRes.json();
    const effect = effRes.ok ? await effRes.json() : null;

    detailContent.innerHTML = `
      <div class="detail-header">
        <h2>#${monster.ID} ${esc(monster.DefName)}</h2>
        <span class="detail-id">${esc(monster.TypeName || monster.Type) || '未知属性'}</span>
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
      ${effect ? `
        <div class="detail-section">
          <h3>属性克制 (${esc(effect.label)}系)</h3>
          ${renderEffectRows([
            ['🔺 弱点', effect.weaknesses, 'strong'],
            ['🔹 抗性', effect.resistances, 'weak'],
            ['🚫 免疫', effect.immunities, 'immune'],
          ])}
        </div>
      ` : ''}
      ${moveData.moves && moveData.moves.length > 0 ? `
        <div class="detail-section">
          <h3>技能列表 (${moveData.count})</h3>
          <ul class="move-list">
            ${moveData.moves.map(m => `
              <li>
                <div class="move-row">
                  <span>
                    <span class="move-name">${esc(m.Name) || '?'}</span>
                    <span style="color:var(--text-dim);font-size:0.75rem">
                      ${m.LearningLv != null ? `Lv${m.LearningLv} ` : ''}${esc(m.TypeName || m.Type)} ${esc(m.CategoryName || m.Category)}
                    </span>
                  </span>
                  <span class="move-info">
                    威力:${m.Power || '-'} PP:${m.MaxPP || '-'} 命中:${m.Accuracy || '-'}
                  </span>
                </div>
                ${m.EffectText ? `<div class="move-effect">${esc(m.EffectText)}</div>` : ''}
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
  effectPanel.classList.add('hidden');
}

function hideLoading() {
  loadingEl.classList.add('hidden');
}

function showError(msg) {
  hideLoading();
  effectPanel.classList.add('hidden');
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
