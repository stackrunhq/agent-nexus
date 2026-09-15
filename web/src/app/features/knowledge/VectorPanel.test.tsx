// @vitest-environment jsdom
import {cleanup, fireEvent, render, screen, waitFor} from '@testing-library/react';
import {afterEach, beforeEach, expect, test, vi} from 'vitest';
import {AdminClient, ApiError} from '../../shared/client';
import {VectorPanel} from './VectorPanel';
beforeEach(() => {
  Object.defineProperty(window, 'matchMedia', {writable:true, value:vi.fn(() => ({matches:false, addListener(){}, removeListener(){}, addEventListener(){}, removeEventListener(){}}))});
  const original = window.getComputedStyle;
  vi.spyOn(window, 'getComputedStyle').mockImplementation(element => original(element));
});
afterEach(() => {cleanup(); vi.restoreAllMocks();});
const root = '/tenants/t/applications/a/versions/v';
const models = ['local', 'cloud', 'unassigned', 'chat'].map(alias => ({alias, deployment:alias, enabled:true, capabilities:[alias === 'chat' ? 'chat' : 'embeddings']}));
test('filters grants and capabilities, confirms builds and refreshes status', async () => {
  const client = new AdminClient(); let built = false;
  const request = vi.spyOn(client, 'request').mockImplementation(async (path, method) => {
    if (path === '/models') return models as never;
    if (path === '/tenants/t/models') return {data:['local','cloud','chat']} as never;
    if (path.endsWith('/index-usage')) return {daily_limit:100,daily_used:0,active:0,active_limit:5,reset_at:86400} as never;
    if (path.includes('/index-jobs?') && method !== 'POST') return {data:[],has_more:false} as never;
    if (method === 'POST') {built = true; return {} as never;}
    if (!built) throw new ApiError('missing', 409, 'index_missing');
    return {status:'ready',dimensions:2,chunks:3} as never;
  });
  render(<VectorPanel client={client} root={root}/>);
  await screen.findByText('local · 本地');
  expect(screen.queryByText(/unassigned/)).toBeNull();
  expect(screen.getByLabelText('索引模型').textContent).not.toContain('chat');
  fireEvent.change(screen.getByLabelText('索引模型'), {target:{value:'local'}});
  await screen.findByText('尚未建立索引');
  fireEvent.click(screen.getByText('建立或重建索引'));
  expect(request.mock.calls.some(call => call[1] === 'POST')).toBe(false);
  fireEvent.click(screen.getByText('确认建立'));
  await screen.findByText('索引可用 · 3 个分片 · 2 维');
  expect(request).toHaveBeenCalledWith(`${root}/index-jobs`, 'POST', {model:'local'}, expect.any(AbortSignal));
});
test('switching model cancels pending status and hides stale results', async () => {
  const client = new AdminClient();
  const request = vi.spyOn(client, 'request').mockImplementation(async path => {
    if (path === '/models') return models as never;
    if (path === '/tenants/t/models') return {data:['local','cloud']} as never;
    return new Promise(() => {});
  });
  const view = render(<VectorPanel client={client} root={root}/>);
  await screen.findByText('local · 本地');
  fireEvent.change(screen.getByLabelText('索引模型'), {target:{value:'local'}});
  await waitFor(() => expect(request.mock.calls.some(call => call[0].endsWith('/index-usage'))).toBe(true));
  const signals = request.mock.calls.slice(2).map(call => call[3]);
  fireEvent.change(screen.getByLabelText('索引模型'), {target:{value:'cloud'}});
  expect(signals.every(signal => signal?.aborted)).toBe(true);
  view.unmount();
  expect(request.mock.calls.slice(2).every(call => call[3]?.aborted)).toBe(true);
});
