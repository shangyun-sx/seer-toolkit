/**
 * 前端逻辑测试 —— 用最小 DOM 桩把 web/static/app.js 加载起来，直接驱动里面
 * 那些纯逻辑函数。
 *
 * 为什么是这套方案，而不是 vitest / jest：
 *   * 项目里没有 Node 构建链。为一个 500 行的原生 JS 引入 npm 全家桶不划算
 *   * **出口只有一个**：tests/test_frontend.py 用 pytest 跑这个脚本，于是
 *     `pytest tests/` 和 CI 都自动覆盖前端，不用记第二条命令、不用改 CI 步骤
 *   * 覆盖不到的是真实交互（点击、渲染布局）—— 那需要真浏览器。这里管的是
 *     最容易悄悄坏掉的那部分：边界条件、URL 拼装、状态机
 *
 * 直接跑: node tests/frontend_dom.mjs
 */

import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const APP_JS = path.resolve(here, '..', 'web', 'static', 'app.js');

// ── DOM / 浏览器桩 ──────────────────────────
//
// querySelector 按选择器缓存 —— 这样断言里能回头读元素的状态（比如
// scrollCalls、textContent、classList）。

const els = {};
const fetched = [];
const pushed = [];

function stubEl() {
  return {
    classList: {
      _has: new Set(),
      add(c) { this._has.add(c); },
      remove(c) { this._has.delete(c); },
      toggle(c, on) { on ? this._has.add(c) : this._has.delete(c); },
      contains(c) { return this._has.has(c); },
    },
    addEventListener() {},
    querySelector() { return stubEl(); },
    querySelectorAll() { return []; },
    style: {}, dataset: {},
    textContent: '', innerHTML: '', value: '20', disabled: false,
    scrollCalls: [],
    scrollIntoView(opts) { this.scrollCalls.push(opts); },
  };
}

globalThis.document = {
  querySelector(sel) { return els[sel] || (els[sel] = stubEl()); },
  querySelectorAll() { return []; },
  addEventListener() {},
};

globalThis.window = {
  matchMedia: () => ({ matches: false }),
  location: { search: '', pathname: '/' },
  history: { pushState(_state, _title, url) { pushed.push(url); } },
  addEventListener() {},
};

globalThis.alert = () => {};

const SAMPLE = {
  ID: 1, DefName: '雷伊', Type: 5, TypeName: '电',
  HP: 71, Atk: 108, Def: 70, SpAtk: 101, SpDef: 77, Spd: 105, Total: 532,
};

// 各接口返回各自该有的形状 —— 不然 init() 里那几个侧边栏加载器会报错刷屏，
// 把真正的失败淹掉
globalThis.fetch = async (url) => {
  fetched.push(url);
  let body;
  if (url.includes('/monsters/count')) body = { count: 5343 };
  else if (url.includes('/monsters/stats')) body = { stats: [] };
  else if (url.includes('/api/types')) body = { types: [] };
  else if (url.includes('/top?')) body = { results: [SAMPLE], count: 1, label: '体力' };
  else body = { results: [SAMPLE], total: 130, shown: 20 };
  return { ok: true, json: async () => body };
};

// ── 加载 app.js ────────────────────────────
//
// app.js 是传统脚本（不是模块），用 runInThisContext 跑；末尾把要测的函数
// 挂到 globalThis 上取出来。

const source = fs.readFileSync(APP_JS, 'utf8');
vm.runInThisContext(
  source + '\n;globalThis.__exports = {'
  + 'esc, formatCount, renderPager, queryUrl, scrollToResults,'
  + 'readUrlState, syncUrl, renderResults, loadPage, loadTopN, state, $'
  + '};',
);

const app = globalThis.__exports;

// ── 断言 ────────────────────────────────────
//
// 不依赖任何测试框架：跑完打印结果，有失败就以非零码退出，
// tests/test_frontend.py 靠退出码判断。

let failures = 0;
let checks = 0;

function check(label, got, want) {
  checks += 1;
  const ok = String(got) === String(want);
  if (!ok) {
    failures += 1;
    console.log(`  FAIL  ${label}\n        got  = ${got}\n        want = ${want}`);
  } else {
    console.log(`  ok    ${label}`);
  }
}

function section(title) {
  console.log(`\n${title}`);
}

// ── 转义 ────────────────────────────────────

section('esc()：插 innerHTML 之前转义');
check('<b>x</b> 的尖括号被转掉', app.esc('<b>x</b>'), '&lt;b&gt;x&lt;/b&gt;');
check('& 被转掉', app.esc('a & b'), 'a &amp; b');
check('双引号被转掉', app.esc('say "hi"'), 'say &quot;hi&quot;');
check('单引号被转掉', app.esc("it's"), 'it&#39;s');
check('null -> 空串', app.esc(null), '');
check('undefined -> 空串', app.esc(undefined), '');
check('数字原样', app.esc(42), '42');
check('正常中文原样', app.esc('雷伊'), '雷伊');

// ── 计数文案 ────────────────────────────────

section('formatCount()：总数和当前页要分清');
check('没截断时不提「显示」', app.formatCount({ total: 10, shown: 10 }), '共 10 条');
check('被截断时两边都给', app.formatCount({ total: 130, shown: 20 }), '显示 20 / 共 130 条');

// ── 分页 ────────────────────────────────────

section('renderPager()：页码计算与显隐');
const pager = app.$('#pager');
const pageInfo = app.$('#pageInfo');
const prevPage = app.$('#prevPage');
const nextPage = app.$('#nextPage');

app.state.currentMode = 'search';
app.state.limit = 20;

app.state.offset = 0;
app.renderPager({ total: 130, shown: 20 });
check('第 1 页页码', pageInfo.textContent, '第 1 / 7 页');
check('第 1 页：上一页禁用', prevPage.disabled, true);
check('第 1 页：下一页可用', nextPage.disabled, false);
check('多于一页：翻页条显示', pager.classList.contains('hidden'), false);

app.state.offset = 120;
app.renderPager({ total: 130, shown: 10 });        // 最后一页不满
check('末页页码', pageInfo.textContent, '第 7 / 7 页');
check('末页：下一页禁用', nextPage.disabled, true);

app.state.offset = 0;
app.renderPager({ total: 10, shown: 10 });         // 一页装得下
check('只有一页：翻页条隐藏', pager.classList.contains('hidden'), true);

app.state.currentMode = 'top';
app.renderPager({ total: 999, shown: 20 });
check('Top N 不显示翻页条', pager.classList.contains('hidden'), true);

// ── URL 拼装 ────────────────────────────────

section('queryUrl()：搜索 / 属性都带分页参数');
app.state.limit = 20;
app.state.currentMode = 'search';
app.state.currentQuery = '雷伊';
check('搜索', app.queryUrl(40),
      `/api/monsters/search?q=${encodeURIComponent('雷伊')}&limit=20&offset=40`);

app.state.currentMode = 'type';
app.state.currentQuery = '火';
check('属性筛选', app.queryUrl(100),
      `/api/monsters/type?element=${encodeURIComponent('火')}&limit=20&offset=100`);

app.state.currentMode = 'top';
check('Top N 不分页', app.queryUrl(0), 'null');

// ── 滚动策略 ────────────────────────────────

section('scrollToResults()：平滑 / 减少动效 / 无结果也滚');
const bar = app.$('#resultBar');

globalThis.window.matchMedia = () => ({ matches: false });
bar.scrollCalls.length = 0;
app.scrollToResults();
check('默认平滑', bar.scrollCalls[0].behavior, 'smooth');
check('对齐到顶部', bar.scrollCalls[0].block, 'start');

globalThis.window.matchMedia = () => ({ matches: true });
bar.scrollCalls.length = 0;
app.scrollToResults();
check('系统开了减少动效 -> 瞬时', bar.scrollCalls[0].behavior, 'auto');

globalThis.window.matchMedia = () => ({ matches: false });
bar.scrollCalls.length = 0;
app.scrollToResults({ smooth: false });
check('显式 smooth:false', bar.scrollCalls[0].behavior, 'auto');

// 0 条结果也要滚 —— 那句「无结果」在结果栏上，不滚用户看不到
bar.scrollCalls.length = 0;
app.renderResults([], '搜索 "zzz"', { total: 0, shown: 0 });
check('0 条结果：仍然滚过去', bar.scrollCalls.length, 1);

bar.scrollCalls.length = 0;
app.renderResults([SAMPLE], '搜索 "雷"', { total: 1, shown: 1 });
check('有结果：滚一次', bar.scrollCalls.length, 1);

// ── 地址栏：读 ──────────────────────────────

section('readUrlState()：从地址栏解析状态');
function withSearch(search, fn) {
  globalThis.window.location.search = search;
  return fn();
}

check('?q= -> 搜索',
      withSearch(`?q=${encodeURIComponent('雷伊')}`, () => app.readUrlState()).mode, 'search');
check('?type= -> 属性',
      withSearch(`?type=${encodeURIComponent('火')}`, () => app.readUrlState()).mode, 'type');
check('?stat= -> 排行',
      withSearch('?stat=HP', () => app.readUrlState()).mode, 'top');

const paged = withSearch('?q=x&limit=50&page=3', () => app.readUrlState());
check('limit 读对', paged.limit, 50);
check('offset 由 page 和 limit 推出', paged.offset, 100);

check('?q= 空值不当成一次搜索',
      withSearch('?q=', () => app.readUrlState()), 'null');
check('干净地址 -> null',
      withSearch('', () => app.readUrlState()), 'null');

// ── 地址栏：写 ──────────────────────────────

section('syncUrl()：拼地址栏 + 不重复入栈');
function pushFor(mutate, currentSearch) {
  mutate(app.state);
  globalThis.window.location.search = currentSearch ?? '';
  pushed.length = 0;
  app.syncUrl();
  return pushed[0];
}

check('搜索第 1 页（page 和 limit 都省略）',
      pushFor((s) => { s.currentMode = 'search'; s.currentQuery = '雷伊'; s.offset = 0; s.limit = 20; }),
      `/?q=${encodeURIComponent('雷伊')}`);

check('翻到第 2 页',
      pushFor((s) => { s.currentMode = 'type'; s.currentQuery = '火'; s.offset = 20; s.limit = 20; }),
      `/?type=${encodeURIComponent('火')}&page=2`);

check('非默认每页条数要写出来',
      pushFor((s) => { s.offset = 0; s.limit = 50; }),
      `/?type=${encodeURIComponent('火')}&limit=50`);

check('排行模式（不带 page）',
      pushFor((s) => { s.currentMode = 'top'; s.currentStat = 'HP'; s.topN = 20; }),
      '/?stat=HP&n=20');

check('地址没变就不入栈（点两下同一个标签）',
      pushFor((s) => { s.currentMode = 'type'; s.currentQuery = '火'; s.offset = 0; s.limit = 20; },
              `?type=${encodeURIComponent('火')}`),
      'undefined');

// ── 导航 vs 恢复 ────────────────────────────

section('loadPage()：用户导航才滚 + 才写历史');
async function loadPageWith(navigate) {
  app.state.currentMode = 'type';
  app.state.currentQuery = '火';
  app.state.limit = 20;
  // 上一节把 location 留在了 ?type=火 —— 不清掉的话 syncUrl 的「地址没变就
  // 不入栈」守卫会生效，于是这里永远测不到 push
  globalThis.window.location.search = '';
  bar.scrollCalls.length = 0;
  pushed.length = 0;
  await app.loadPage(0, navigate === undefined ? {} : { navigate });
}

await loadPageWith(false);                           // 恢复
check('navigate:false -> 不滚', bar.scrollCalls.length, 0);
check('navigate:false -> 不写历史', pushed.length, 0);

await loadPageWith(undefined);                       // 用户导航（默认）
check('默认 -> 滚一次', bar.scrollCalls.length, 1);
check('默认 -> 写历史一次', pushed.length, 1);

// ── 汇总 ────────────────────────────────────

console.log(`\n${checks - failures}/${checks} 通过`);
process.exit(failures ? 1 : 0);
