import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { runInNewContext } from 'node:vm';

const load = (name) => readFileSync(new URL(name, import.meta.url), 'utf8');
const { createModel, fold, edgeEvidence } = runInNewContext(
  load('../assets/viewer/model.js') + '\nFlowModel;',
);
const sample = JSON.parse(load('../assets/example_workflow.json'));
const ids = (nodes) => Array.from(nodes, ({ id }) => id);

function fixture() {
  return {
    entry_node: 'toString',
    nodes: [
      { id: 'toString', title: 'Bắt đầu', summary: '', type: 'start', confidence: 'partial' },
      { id: 'x', title: 'Xuất báo cáo', summary: '', type: 'action', confidence: 'verified',
        source_refs: [{ path: 'reports/export.py', symbol: 'writeReport', start_line: 12, end_line: 15 }] },
      { id: 'y', title: 'Đọc hàng đợi', summary: '', type: 'data', confidence: 'inferred',
        source_refs: [{ path: 'reports/export.py', start_line: 12, end_line: 15 }] },
      { id: 'z', title: 'Kết thúc', summary: '', type: 'end', confidence: 'unknown' },
    ],
    edges: [
      { from: 'toString', to: 'x', kind: 'normal', label: 'Gửi yêu cầu', evidence: 'entry' },
      { from: 'toString', to: 'y', kind: 'condition', label: 'Xuất nền', evidence: 'import' },
      { from: 'x', to: 'z', kind: 'success', label: 'Đã lưu' },
      { from: 'y', to: 'z', kind: 'normal', label: 'Đã đọc' },
      { from: 'y', to: 'y', kind: 'loop', label: 'Thử lại' },
    ],
  };
}

test('search handles Vietnamese with or without accents and includes source and branch text', () => {
  const model = createModel(fixture());
  assert.equal(fold('  ĐỌC HÀNG ĐỢI  '), 'doc hang doi');
  assert.deepEqual(ids(model.search('doc hang doi')), ['y']);
  assert.deepEqual(ids(model.search('xuat WRITEreport')), ['x']);
  assert.deepEqual(ids(model.search('reports/export.py:12')), ['x', 'y']);
  assert.deepEqual(ids(model.search('thu lai')), ['y']);
  assert.deepEqual(ids(model.search('bao cao', 'unknown')), []);
  assert.deepEqual(ids(model.search('', 'unknown')), ['z']);
});

test('confidence counts keep illustrative, partial and verified distinct', () => {
  const model = createModel(sample);
  assert.equal(model.confidenceCounts.get('illustrative'), 8);
  assert.equal(model.confidenceCounts.get('verified'), 0);
  assert.equal(createModel(fixture()).confidenceCounts.get('partial'), 1);
});

test('guide returns only real outgoing edges including loops without auto-following a branch', () => {
  const model = createModel(fixture());
  assert.deepEqual(Array.from(model.outgoing.get('toString'), (e) => e.to), ['x', 'y']);
  assert.deepEqual(Array.from(model.outgoing.get('y'), (e) => e.kind), ['normal', 'loop']);
  assert.deepEqual(Array.from(model.outgoing.get('z')), []);
  const route = model.pathTo('z');
  assert.deepEqual(Array.from(route, (e) => e.to), ['x', 'z']);
  assert.equal(model.pathTo('absent'), null);
});

test('a source location is listed once with links to every step that cites it', () => {
  const model = createModel(fixture());
  assert.equal(model.sources.length, 1);
  assert.equal(model.sources[0].location, 'reports/export.py:12–15');
  assert.deepEqual(ids(model.sources[0].nodes), ['x', 'y']);
  assert.deepEqual(Array.from(model.sources[0].symbols), ['writeReport']);
});

test('import evidence is distinguished from a call, and unknown values make no claims', () => {
  assert.equal(edgeEvidence('import'), 'Nhập mô-đun');
  assert.equal(edgeEvidence('call'), 'Vị trí gọi hàm');
  assert.equal(edgeEvidence('not-a-known-kind'), 'Chưa nêu căn cứ');
});
