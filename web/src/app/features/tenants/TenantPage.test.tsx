// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, expect, test, vi } from 'vitest';
import { TenantPage } from './TenantPage';

beforeEach(() => {
  vi.stubGlobal('localStorage', {setItem: vi.fn()});
  vi.stubGlobal('sessionStorage', {setItem: vi.fn()});
  Object.defineProperty(window, 'matchMedia', {writable: true, value: vi.fn().mockImplementation(() => ({matches: false, addListener() {}, removeListener() {}, addEventListener() {}, removeEventListener() {}}))});
  vi.stubGlobal('ResizeObserver', class { observe() {} unobserve() {} disconnect() {} });
  const computed = window.getComputedStyle;
  vi.spyOn(window, 'getComputedStyle').mockImplementation(element => computed(element));
});

test('revoke uses empty response and rotation requires confirmation', async () => {
  let granted = true;
  const fetcher = vi.fn(async (url: string, options: RequestInit) => {
    if (url.endsWith('/settings')) return Response.json({auth_mode: 'tenant'});
    if (url.endsWith('/rotate-key')) return Response.json({id: 't-1', api_key: 'nx_rotated'});
    if (options.method === 'DELETE') { granted = false; return new Response(null, {status: 204}); }
    if (url.endsWith('/tenants/t-1/models')) return Response.json({data: granted ? ['local'] : []});
    if (url.endsWith('/events')) return Response.json({data: []});
    if (url.endsWith('/models')) return Response.json([{alias: 'local', enabled: true}]);
    return Response.json({data: [{id: 't-1', name: '示例企业', enabled: true}]});
  });
  vi.stubGlobal('fetch', fetcher);
  render(<TenantPage/>);
  fireEvent.change(screen.getByLabelText('管理员令牌'), {target: {value: 'a'.repeat(32)}});
  fireEvent.submit(screen.getByLabelText('管理员令牌').closest('form')!);
  fireEvent.click(await screen.findByText('授权与事件'));
  fireEvent.click(await screen.findByText('撤销授权'));
  await waitFor(() => expect(screen.queryByText('撤销授权')).toBeNull());
  fireEvent.click(screen.getByText('轮换凭据'));
  expect(fetcher.mock.calls.some(([url]) => url.endsWith('/rotate-key'))).toBe(false);
  const dialog = screen.getByRole('dialog');
  fireEvent.click(within(dialog).getByRole('button', {name: /OK|确.*定/}));
  await screen.findByText('nx_rotated');
});
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });

test('create shows one-time credential, disconnect clears private state', async () => {
  let created = false;
  vi.stubGlobal('fetch', vi.fn(async (url: string, options: RequestInit) => {
    if (url.endsWith('/settings')) return Response.json({auth_mode: 'tenant'});
    if (url.endsWith('/models')) return Response.json([]);
    if (options.method === 'POST') { created = true; return Response.json({id: 't-1', name: '示例企业', enabled: true, api_key: 'nx_once'}); }
    return Response.json({data: created ? [{id: 't-1', name: '示例企业', enabled: true}] : []});
  }));
  render(<TenantPage/>);
  fireEvent.change(screen.getByLabelText('管理员令牌'), {target: {value: 'a'.repeat(32)}});
  fireEvent.submit(screen.getByLabelText('管理员令牌').closest('form')!);
  await screen.findByText('断开连接');
  fireEvent.change(screen.getByLabelText('企业名称'), {target: {value: '示例企业'}});
  fireEvent.submit(screen.getByLabelText('企业名称').closest('form')!);
  await screen.findByText('nx_once');
  expect(localStorage.setItem).not.toHaveBeenCalled();
  expect(sessionStorage.setItem).not.toHaveBeenCalled();
  fireEvent.click(screen.getByText('已保存，关闭'));
  await waitFor(() => expect(document.querySelector('.credential')).toBeNull());
  fireEvent.click(screen.getByText('断开连接'));
  expect(screen.queryByText('示例企业')).toBeNull();
  expect(screen.queryByText('nx_once')).toBeNull();
});
