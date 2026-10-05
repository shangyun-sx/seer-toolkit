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
const effectPanel = $('#effectPanel');
const typeSelect = $('#typeSelect');
const checkTypeBtn = $('#checkTypeBtn');

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

async function loadTypeOptions() {
  try {
    const res = await fetch('/api/types');
    const data = await res.json();
    typeSelect.innerHTML = data.types.map(t =>
      `<option value="${t.name}">${t.name} (${t.name_en})</option>`
    ).join('');
  } catch (e) {
    console.error('加载属性下拉框失败:', e);
  }
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
              `<span class="type-tag ${cls}">${name} ${mult}x</span>`).join('')
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
      <h3>用 ${data.element} 系技能攻击</h3>
      ${renderEffectRows([
        ['🔺 克制', data.offense.strong, 'strong'],
        ['🔹 微弱', data.offense.weak, 'weak'],
        ['🚫 无效', data.offense.immune, 'immune'],
      ])}
    </div>
    <div class="effect-group">
      <h3>${data.element} 系精灵受到攻击</h3>
      ${renderEffectRows([
        ['🔺 弱点', data.defense.weaknesses, 'strong'],
        ['🔹 抗性', data.defense.resistances, 'weak'],
        ['🚫 免疫', data.defense.immunities, 'immune'],
      ])}
    </div>
  `;
}

// ── 渲染 ──────────────────────────

function renderResults(results, title, count) {
  hideLoading();
  emptyState.classList.add('hidden');
  effectPanel.classList.add('hidden');

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
      <td>${r.TypeName || r.Type || ''}</td>
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
        <h2>#${monster.ID} ${monster.DefName}</h2>
        <span class="detail-id">${monster.TypeName || monster.Type || '未知属性'}</span>
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
          <h3>属性克制 (${effect.label}系)</h3>
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
                    <span class="move-name">${m.Name || '?'}</span>
                    <span style="color:var(--text-dim);font-size:0.75rem">
                      ${m.LearningLv != null ? `Lv${m.LearningLv} ` : ''}${m.TypeName || m.Type || ''} ${m.CategoryName || m.Category || ''}
                    </span>
                  </span>
                  <span class="move-info">
                    威力:${m.Power || '-'} PP:${m.MaxPP || '-'} 命中:${m.Accuracy || '-'}
                  </span>
                </div>
                ${m.EffectText ? `<div class="move-effect">${m.EffectText}</div>` : ''}
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
