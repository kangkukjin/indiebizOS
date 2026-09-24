import assert from 'node:assert/strict';
import vm from 'node:vm';
import { test } from 'node:test';
import worker from './worker.js';

async function browser() {
  const response = await worker.fetch(new Request('https://local/'));
  assert.equal(response.status, 200);
  const html = await response.text();
  const script = html.match(/<script>([\s\S]*?)<\/script>/)[1];
  const elements = Object.fromEntries(['grid', 'status', 'refresh'].map(id => [id, {
    innerHTML: '', disabled: false,
    addEventListener() {}, querySelectorAll() { return []; },
  }]));
  const context = vm.createContext({
    document: { getElementById: id => elements[id], addEventListener() {} },
    // 시작 시 비동기 갱신을 멈추고 실제 배포 스크립트를 그대로 검사한다.
    fetch: () => new Promise(() => {}), setInterval() {},
  });
  vm.runInContext(script, context);
  return { context, elements };
}

const quote = {
  key: 'tiger200', ok: true, label: 'TIGER 200', sub: 'ETF', unit: '원',
  price: 113360, change: 1180, changePct: 1.05, prevClose: 112180,
  high: 114670, low: 112230, volume: 15602772, src: 'naver',
};

test('served browser script computes gain, loss, breakeven and missing price', async () => {
  const { context } = await browser();
  for (const [price, expected] of [
    [113360, ['72,890,480', '34,977,271', '+37,913,209원', '+108.39%']],
    [50000, ['32,150,000', '-2,827,271원', '-8.08%']],
    [54397, ['34,977,271', '>0원', '>0.00%']],
    [null, ['—원', '—%']],
    [0, ['—원', '—%']],
  ]) {
    context.input = { ...quote, price };
    const result = vm.runInContext('card(input)', context);
    for (const value of expected) assert.ok(result.includes(value), `${price}: ${value}`);
    assert.doesNotMatch(result, /NaN|Infinity|undefined/);
  }
  context.input = { ...quote, key: 'samsung' };
  assert.doesNotMatch(vm.runInContext('card(input)', context), /어머니|holding-details/);
  context.input = { ...quote, ok: false, error: '원천 오류' };
  assert.match(vm.runInContext('card(input)', context), /시세를 가져오지 못했습니다/);
  assert.doesNotMatch(vm.runInContext('card(input)', context), /72,890,480/);
});

test('refresh updates holdings and marks an HTTP failure without clearing the last quote', async () => {
  const { context, elements } = await browser();
  context.fetch = async () => ({ ok: true, json: async () => ({
    fetchedAt: 1790145000000, quotes: [quote],
  }) });
  await vm.runInContext('load()', context);
  assert.match(elements.grid.innerHTML, /72,890,480/);
  context.fetch = async () => ({ ok: true, json: async () => ({
    fetchedAt: 1790145001000, quotes: [{ ...quote, price: 50000 }],
  }) });
  await vm.runInContext('load()', context);
  assert.match(elements.grid.innerHTML, /32,150,000/);
  context.fetch = async () => ({ ok: false, status: 503 });
  await vm.runInContext('load()', context);
  assert.match(elements.status.innerHTML, /갱신 실패 — HTTP 503/);
  assert.match(elements.grid.innerHTML, /32,150,000/);
  assert.equal(elements.refresh.disabled, false);
});

test('quote API preserves negative changes and falls back when Naver fails', async t => {
  t.mock.method(globalThis, 'fetch', async () => Response.json({ datas: [{
    closePriceRaw: '50,000', compareToPreviousClosePriceRaw: '-1,000',
    fluctuationsRatioRaw: '-1.96', accumulatedTradingVolumeRaw: '123',
  }] }));
  const read = async () => (await worker.fetch(new Request('https://local/api/quotes'))).json();
  const naver = await read();
  assert.equal(naver.quotes[0].price, 50000);
  assert.equal(naver.quotes[0].prevClose, 51000);
  assert.equal(naver.quotes[0].change, -1000);

  globalThis.fetch.mock.mockImplementation(async url => {
    if (url.includes('naver.com')) return new Response('', { status: 503 });
    return Response.json({ chart: { result: [{
      meta: { regularMarketPrice: 50000, chartPreviousClose: 51000 },
      indicators: { quote: [{ high: [52000], low: [49000], volume: [123] }] },
    }] } });
  });
  const fallback = await read();
  assert.equal(fallback.quotes[0].src, 'yahoo');
  assert.equal(fallback.quotes[0].change, -1000);
  globalThis.fetch.mock.mockImplementation(async () => new Response('', { status: 503 }));
  const failed = await read();
  assert.ok(failed.quotes.every(q => q.ok === false && !('price' in q)));
});
