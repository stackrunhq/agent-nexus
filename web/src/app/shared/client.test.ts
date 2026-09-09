import { afterEach, expect, test, vi } from 'vitest';
import { AdminClient } from './client';

afterEach(() => {vi.unstubAllGlobals(); vi.useRealTimers();});

test('personal session deadline clears access and notifies the page', async () => {
  vi.useFakeTimers();
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(Response.json({access_token:'ns_short',expires_in:1,user:{role:'platform_admin'}})));
  const client = new AdminClient();
  client.onExpired = vi.fn();
  await client.login('alice','long-password');
  vi.advanceTimersByTime(1000);
  expect(client.onExpired).toHaveBeenCalledOnce();
});

test('personal login uses auth endpoint and logout revokes session before clearing access', async () => {
  const fetcher = vi.fn().mockResolvedValueOnce(Response.json({access_token:'ns_personal',user:{role:'platform_admin'}})).mockResolvedValueOnce(new Response(null,{status:204})).mockResolvedValueOnce(Response.json({data:[]}));
  vi.stubGlobal('fetch', fetcher);
  const client = new AdminClient();
  await client.login('alice','long-password');
  expect(fetcher.mock.calls[0][0]).toBe('/api/v1/auth/login');
  await client.logout();
  expect(fetcher.mock.calls[1][0]).toBe('/api/v1/auth/logout');
  expect(fetcher.mock.calls[1][1].headers.Authorization).toBe('Bearer ns_personal');
  await client.request('/users');
  expect(fetcher.mock.calls[2][1].headers.Authorization).toBe('Bearer ');
});

test('tenant members cannot enter the platform UI and their new session is revoked', async () => {
  const fetcher = vi.fn().mockResolvedValueOnce(Response.json({access_token:'ns_member',user:{role:'tenant_user'}})).mockResolvedValueOnce(new Response(null,{status:204}));
  vi.stubGlobal('fetch',fetcher);
  const client = new AdminClient();
  await expect(client.login('member','long-password')).rejects.toThrow('企业成员');
  expect(fetcher.mock.calls[1][0]).toBe('/api/v1/auth/logout');
});

test('grant/revoke 204 responses need no JSON body', async () => {
  const fetcher = vi.fn().mockResolvedValue(new Response(null, {status: 204}));
  vi.stubGlobal('fetch', fetcher);
  const client = new AdminClient(); client.connect('test-token');
  await expect(client.request('/tenants/id/models/test', 'PUT')).resolves.toBeUndefined();
  expect(fetcher.mock.calls[0][1].headers.Authorization).toBe('Bearer test-token');
});

test('late response after disconnect cannot restore private data', async () => {
  let resolve!: (r: Response) => void;
  vi.stubGlobal('fetch', vi.fn(() => new Promise<Response>(r => { resolve = r; })));
  const client = new AdminClient(); client.connect('test-token');
  const result = client.request('/tenants');
  client.disconnect();
  resolve(Response.json({data: [{api_key: 'secret'}]}));
  await expect(result).rejects.toMatchObject({name: 'AbortError'});
});

test('errors carry request ID without echoing arbitrary response fields', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(Response.json({error: {message: 'Denied'}, request_id: 'r-1', api_key: 'secret'}, {status: 403})));
  const client = new AdminClient(); client.connect('test-token');
  await expect(client.request('/tenants')).rejects.toThrow('Denied（403），请求 ID：r-1');
});
