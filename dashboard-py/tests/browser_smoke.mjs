// 浏览器侧冒烟：用 CDP 驱动真实 Chrome 验证「目标输入框 -> 卡片达成率 -> localStorage」。
//
// 为什么不放进 pytest：这段逻辑只有真实浏览器才能验（dcc.Input 的提交时机、React 受控
// 输入、localStorage 交互都不是服务端能覆盖的）。
//
// 用法（先在另一个终端启动看板）：
//   cd dashboard-py && ./.venv/Scripts/python.exe app.py --data-dir ../数据底表V1 --port 8051
//   rm -rf /tmp/cdp-profile
//   "<chrome>" --headless=new --disable-gpu --no-sandbox \
//     --remote-debugging-port=9222 --user-data-dir=/tmp/cdp-profile --no-first-run about:blank &
//   node tests/browser_smoke.mjs
//
// 踩过的坑：type="number" 的输入框不支持 setSelectionRange，全选必须走 Ctrl+A 键盘事件；
// 用 element.value = x + dispatchEvent 这种合成事件 React 不认，必须用 Input.insertText。
const PORT = 9222;
const URL = process.env.DASHBOARD_URL || 'http://127.0.0.1:8051/';
const CARD_METRICS = ['All Leads', 'All SQLs'];

async function pageTarget() {
  for (let i = 0; i < 40; i += 1) {
    try {
      const list = await (await fetch(`http://127.0.0.1:${PORT}/json/list`)).json();
      const page = list.find((t) => t.type === 'page' && t.webSocketDebuggerUrl);
      if (page) return page;
    } catch (e) { /* 等 chrome 起来 */ }
    await new Promise((r) => setTimeout(r, 500));
  }
  throw new Error(`no debuggable page on ${PORT}`);
}

const page = await pageTarget();
const ws = new WebSocket(page.webSocketDebuggerUrl);
let seq = 0;
const pending = new Map();
ws.addEventListener('message', (ev) => {
  const msg = JSON.parse(ev.data);
  if (msg.id && pending.has(msg.id)) { pending.get(msg.id)(msg); pending.delete(msg.id); }
});
await new Promise((res) => ws.addEventListener('open', res));

const send = (method, params = {}) => {
  seq += 1;
  const id = seq;
  return new Promise((res) => { pending.set(id, res); ws.send(JSON.stringify({ id, method, params })); });
};

const evaluate = async (expression) => {
  const r = await send('Runtime.evaluate', { expression, awaitPromise: true, returnByValue: true });
  if (r.result?.exceptionDetails) throw new Error(JSON.stringify(r.result.exceptionDetails).slice(0, 400));
  return r.result?.result?.value;
};

const readCards = () => `(() => {
  const out = [];
  for (const el of document.querySelectorAll('.kpi-card')) {
    const title = el.querySelector('.kpi-title')?.textContent?.trim();
    const progress = el.querySelector('.kpi-target')?.textContent?.trim();
    if (progress) out.push(title + ' | ' + el.querySelector('.kpi-value')?.textContent?.trim() + ' | ' + progress);
  }
  return out;
})()`;

const readInputs = () => `(() => {
  // dcc.Input 的 className 在外层 div 上，真正的输入框是 .dash-input-element
  const out = {};
  for (const el of document.querySelectorAll('.target-input .dash-input-element')) out[el.id] = el.value;
  return out;
})()`;

const waitForDashboard = (targetId, expected) => evaluate(`new Promise((res) => {
  const t0 = Date.now();
  const timer = setInterval(() => {
    const el = ${targetId ? `document.getElementById(${JSON.stringify(targetId)})` : 'null'};
    const ok = ${targetId ? `el && String(el.value) === ${JSON.stringify(String(expected))}` : 'true'};
    const filled = (document.querySelector('.kpi-target')?.textContent || '').trim();
    if ((ok && filled) || Date.now() - t0 > 30000) { clearInterval(timer); setTimeout(() => res(true), 1500); }
  }, 200);
})`);

// 真实键盘事件：聚焦 -> Ctrl+A 全选 -> 输入 -> 回车（type=number 不支持 setSelectionRange）
const type = async (id, value, commitKey = 'Enter') => {
  await evaluate(`document.getElementById(${JSON.stringify(id)}).focus()`);
  for (const type of ['keyDown', 'keyUp']) {
    await send('Input.dispatchKeyEvent', { type, key: 'a', code: 'KeyA', windowsVirtualKeyCode: 65, nativeVirtualKeyCode: 65, modifiers: 2 });
  }
  await send('Input.insertText', { text: value });
  const commit = commitKey === 'Tab'
    ? { key: 'Tab', code: 'Tab', windowsVirtualKeyCode: 9 }
    : { key: 'Enter', code: 'Enter', windowsVirtualKeyCode: 13 };
  for (const type of ['keyDown', 'keyUp']) {
    await send('Input.dispatchKeyEvent', { type, nativeVirtualKeyCode: commit.windowsVirtualKeyCode, ...commit });
  }
  await new Promise((r) => setTimeout(r, 2500));
};

const show = async (label) => {
  console.log(`\n== ${label} ==`);
  for (const row of await evaluate(readCards())) console.log('  ', row);
  console.log('   输入框:', await evaluate(readInputs()));
  console.log('   localStorage:', await evaluate('localStorage.getItem("target-store")'));
};

const check = (label, condition) => console.log(`   ${condition ? 'PASS' : 'FAIL'} ${label}`);

// 先清掉 localStorage，保证「首次加载」这一段从确定状态开始（复用同一个 Chrome 实例时
// 上一轮的目标值会留在这里，会让断言看起来像失败）。
await send('Page.navigate', { url: URL });
await waitForDashboard(null, null);
await evaluate('localStorage.removeItem("target-store")');
await send('Page.navigate', { url: URL });
await waitForDashboard(null, null);
await show('首次加载（无 localStorage，应使用默认目标）');
const inputCount = await evaluate(`document.querySelectorAll('.target-input .dash-input-element').length`);
check('5 个目标输入框都已渲染', inputCount === 5);
const firstCards = await evaluate(readCards());
check('默认目标已算出达成率', firstCards.some((r) => r.includes('18% of target')));
check('未填目标的 SQLs 显示 No target set', firstCards.some((r) => r.startsWith('All SQLs') && r.includes('No target set')));

await type('target-leads', '500');
await type('target-sqls', '900');
await show('Leads=500（超目标，回车提交）、SQLs=900（回车提交）');
const typedCards = await evaluate(readCards());
const stored = JSON.parse(await evaluate('localStorage.getItem("target-store")') || '{}');
check('回车提交后 Leads 显示 ahead', typedCards.some((r) => r.startsWith('All Leads') && r.includes('ahead')));
check('空输入框也能用回车提交', typedCards.some((r) => r.startsWith('All SQLs') && r.includes('16% of target')));
check('目标已写入 localStorage', stored.leads === 500 && stored.sqls === 900);

await type('target-revenue', '100000', 'Tab');
const tabCards = await evaluate(readCards());
check('失焦同样能提交', tabCards.some((r) => r.startsWith('All Revenue') && r.includes('123% of target')));

await send('Page.navigate', { url: URL });
await waitForDashboard('target-leads', 500);
await show('重新加载后（应保留 500 / 900 / 100000）');
const restored = await evaluate(readInputs());
check('输入框被 localStorage 回填', String(restored['target-leads']) === '500' && String(restored['target-sqls']) === '900');

ws.close();
process.exit(0);
