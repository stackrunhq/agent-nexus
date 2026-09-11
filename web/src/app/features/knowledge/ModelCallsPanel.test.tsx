// @vitest-environment jsdom
import {cleanup, render, screen} from '@testing-library/react';
import {afterEach, expect, test, vi} from 'vitest';
import {AdminClient} from '../../shared/client';
import {ModelCallsPanel} from './ModelCallsPanel';
afterEach(() => {cleanup(); vi.restoreAllMocks();});
test('renders unknown usage without treating it as zero and cancels pending reads', async () => {
  const client = new AdminClient();
  const request = vi.spyOn(client, 'request').mockImplementation(async path => path.endsWith('/model-usage') ? {daily_used:1,daily_limit:1000,reset_at:86400} as never : {data:[{id:'c',request_id:'r',model:'local',capability:'chat',status:'pending',created_at:1,elapsed_ms:null,input_tokens:null,output_tokens:null,error:null}]} as never);
  const view = render(<ModelCallsPanel client={client} root="/tenants/t"/>);
  await screen.findByText(/输入 token：未知/);
  expect(request).toHaveBeenCalledWith('/tenants/t/model-calls?offset=0&limit=20', 'GET', undefined, expect.any(AbortSignal));
  view.unmount();
  request.mockImplementation(() => new Promise(() => {}));
  const pending = render(<ModelCallsPanel client={client} root="/tenants/b"/>);
  pending.unmount();
  expect(request.mock.calls[2][3]?.aborted).toBe(true);
});
