// @vitest-environment jsdom
import {cleanup, fireEvent, render, screen, waitFor, within} from '@testing-library/react';
import {afterEach, beforeEach, expect, test, vi} from 'vitest';
import {AdminClient} from '../../shared/client';
import {KnowledgePanel} from './KnowledgePanel';

beforeEach(() => {
  Object.defineProperty(window, 'matchMedia', {writable: true, value: vi.fn(() => ({matches: false, addListener(){}, removeListener(){}, addEventListener(){}, removeEventListener(){}}))});
  vi.stubGlobal('ResizeObserver', class {observe(){} unobserve(){} disconnect(){}});
  const computed = window.getComputedStyle;
  vi.spyOn(window, 'getComputedStyle').mockImplementation(element => computed(element));
});
afterEach(() => {cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals();});
const root = '/tenants/t1/applications/a1/versions/v1/documents';
const doc = {id: 'd1', filename: 'manual.txt', status: 'ready', published: false, warnings: [], error: null};

test('validates files, uploads to the selected scope, and refreshes queued state', async () => {
  const client = new AdminClient();
  let uploaded = false;
  vi.spyOn(client, 'request').mockImplementation(async () => ({data: uploaded ? [{...doc, status:'queued'}] : []}) as never);
  const send = vi.spyOn(client, 'upload').mockImplementation(async () => {uploaded = true; return {...doc, status:'queued'} as never;});
  render(<KnowledgePanel client={client} root={root} title="ERP 1" versionStatus="draft" enabled/>);
  await waitFor(() => expect((screen.getByLabelText('选择手册') as HTMLInputElement).disabled).toBe(false));
  fireEvent.change(screen.getByLabelText('选择手册'), {target:{files:[new File(['x'], 'bad.exe')]}});
  expect((screen.getByRole('button', {name:'上传手册'}) as HTMLButtonElement).disabled).toBe(true);
  const file = new File(['manual'], 'manual.txt');
  fireEvent.change(screen.getByLabelText('选择手册'), {target:{files:[file]}});
  fireEvent.click(screen.getByRole('button', {name:'上传手册'}));
  await screen.findByText('等待处理');
  expect(send).toHaveBeenCalledWith(root, file, expect.any(AbortSignal));
  expect((screen.getByRole('button', {name:'上传手册'}) as HTMLButtonElement).disabled).toBe(true);
});

test('renders source text safely and confirms publication before PATCH', async () => {
  const client = new AdminClient();
  let published = false;
  const request = vi.spyOn(client, 'request').mockImplementation(async (path, method) => {
    if (method === 'PATCH') {published = true; return {} as never;}
    if (path.includes('/chunks?')) return {data:[{chunk_index:0, text:'<img src=x onerror=alert(1)>', source_kind:'page', source_index:2, start:0, end:30}]} as never;
    return {data:[{...doc, published, warnings:['page_without_text:3']}]} as never;
  });
  const view = render(<KnowledgePanel client={client} root={root} title="ERP 1" versionStatus="published" enabled/>);
  fireEvent.click(await screen.findByRole('button', {name:'查看分片'}));
  await screen.findByText('<img src=x onerror=alert(1)>');
  expect(document.querySelector('.knowledge-text img')).toBeNull();
  expect(screen.getByText(/页码 2/)).toBeTruthy();
  fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', {name:'Close'}));
  fireEvent.click(screen.getByRole('button', {name:'发布文档'}));
  expect(request.mock.calls.some(([, method]) => method === 'PATCH')).toBe(false);
  fireEvent.click(within(screen.getByRole('dialog', {name:'确认发布文档'})).getByRole('button', {name:/确.*认/}));
  await screen.findByRole('button', {name:'撤回文档'});
  expect(request).toHaveBeenCalledWith(root + '/d1', 'PATCH', {published:true}, expect.any(AbortSignal));
  view.unmount();
  expect(document.querySelector('.knowledge-text')).toBeNull();
});

test('failed documents can retry and server pagination uses offsets', async () => {
  const client = new AdminClient();
  const request = vi.spyOn(client, 'request').mockImplementation(async (path, method) => {
    if (method === 'POST') return {} as never;
    return {data:path.includes('offset=20') ? [] : Array.from({length:20}, (_, i) => ({...doc, id:'d'+i, filename:'manual'+i+'.txt', status:i===0?'failed':'ready', error:i===0?'parser_timeout':null}))} as never;
  });
  render(<KnowledgePanel client={client} root={root} title="ERP 1" versionStatus="draft" enabled/>);
  fireEvent.click(await screen.findByRole('button', {name:'重试解析'}));
  await waitFor(() => expect(request).toHaveBeenCalledWith(root + '/d0/retry', 'POST', undefined, expect.any(AbortSignal)));
  await waitFor(() => expect((screen.getByRole('button', {name:'下一页文档'}) as HTMLButtonElement).disabled).toBe(false));
  fireEvent.click(screen.getByRole('button', {name:'下一页文档'}));
  await waitFor(() => expect(request).toHaveBeenCalledWith(root + '?offset=20&limit=20', 'GET', undefined, expect.any(AbortSignal)));
});

test('unmount aborts in-flight requests and retired versions prohibit upload', async () => {
  const client = new AdminClient();
  let signal: AbortSignal | undefined;
  vi.spyOn(client, 'request').mockImplementation((_path, _method, _body, supplied) => {signal = supplied; return new Promise(() => {});});
  const view = render(<KnowledgePanel client={client} root={root} title="ERP 1" versionStatus="retired" enabled/>);
  expect((screen.getByLabelText('选择手册') as HTMLInputElement).disabled).toBe(true);
  view.unmount();
  expect(signal?.aborted).toBe(true);
});
