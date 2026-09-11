// @vitest-environment jsdom
import {cleanup, fireEvent, render, screen} from '@testing-library/react';
import {afterEach, beforeEach, expect, test, vi} from 'vitest';
import {AdminClient} from '../../shared/client';
import {QuotaPanel} from './QuotaPanel';
beforeEach(() => {
  Object.defineProperty(window, 'matchMedia', {writable:true, value:vi.fn(() => ({matches:false, addListener(){}, removeListener(){}, addEventListener(){}, removeEventListener(){}}))});
  const original = window.getComputedStyle;
  vi.spyOn(window, 'getComputedStyle').mockImplementation(element => original(element));
});
afterEach(() => {cleanup(); vi.restoreAllMocks();});
test('confirms zero limit and preserves null inheritance', async () => {
  const client = new AdminClient();
  const request = vi.spyOn(client, 'request').mockResolvedValue({daily_limit:null,active_limit:null,effective_daily_limit:100,effective_active_limit:5} as never);
  render(<QuotaPanel client={client} root="/tenants/t"/>);
  await screen.findByText('当前生效：每日 100 次，活跃 5 项。');
  fireEvent.change(screen.getByLabelText('每日任务上限'), {target:{value:'0'}});
  fireEvent.click(screen.getByText('保存企业限额'));
  expect(request).toHaveBeenCalledTimes(1);
  fireEvent.click(screen.getByText('确认保存'));
  await screen.findByText('企业索引限额已保存；用量展示请刷新索引状态。');
  expect(request).toHaveBeenCalledWith('/tenants/t/index-quota','PUT',{daily_limit:0,active_limit:null},expect.any(AbortSignal));
});
