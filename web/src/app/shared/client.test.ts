import { afterEach, expect, test, vi } from 'vitest';
import { AdminClient } from './client';

afterEach(() => vi.unstubAllGlobals());

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
