// @vitest-environment jsdom
import {cleanup, fireEvent, render, screen, waitFor} from '@testing-library/react';
import {afterEach, expect, test, vi} from 'vitest';
import {AdminClient} from '../../shared/client';
import {IndexJobHistory} from './IndexJobHistory';
afterEach(() => {cleanup(); vi.restoreAllMocks();});

test('queries server pages and resets offset when filters change', async () => {
  const client = new AdminClient();
  const request = vi.spyOn(client, 'request').mockResolvedValue({data:[],has_more:true} as never);
  render(<IndexJobHistory client={client} root="/v" model="local & cloud" revision={0}/>);
  await screen.findByText('没有符合条件的任务。');
  fireEvent.click(screen.getByText('下一页'));
  await waitFor(() => expect(request.mock.calls.at(-1)?.[0]).toContain('offset=20'));
  fireEvent.change(screen.getByLabelText('任务状态'), {target:{value:'failed'}});
  await waitFor(() => expect(request.mock.calls.at(-1)?.[0]).toContain('offset=0'));
  fireEvent.change(screen.getByLabelText('失败错误码'), {target:{value:'provider_timeout'}});
  fireEvent.click(screen.getByText('按错误码查询'));
  await waitFor(() => expect(request.mock.calls.at(-1)?.[0]).toContain('error=provider_timeout'));
  expect(request.mock.calls.at(-1)?.[0]).toContain('model=local+%26+cloud');
  fireEvent.click(screen.getByText('缺失错误码'));
  await waitFor(() => expect(request.mock.calls.at(-1)?.[0]).toMatch(/error=$/));
});

test('cancels stale requests and exposes request failure without old rows', async () => {
  const client = new AdminClient();
  const request = vi.spyOn(client, 'request').mockImplementation(() => new Promise(() => {}));
  const view = render(<IndexJobHistory client={client} root="/v" model="a" revision={0}/>);
  const signal = request.mock.calls[0][3];
  request.mockRejectedValue(new Error('连接失败'));
  fireEvent.click(screen.getByText('刷新任务历史'));
  expect(signal?.aborted).toBe(true);
  expect(await screen.findByRole('alert')).toHaveProperty('textContent','连接失败');
  view.unmount();
  expect(request.mock.calls.at(-1)?.[3]?.aborted).toBe(true);
});
