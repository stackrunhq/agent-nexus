// @vitest-environment jsdom
import {cleanup,fireEvent,render,screen} from '@testing-library/react';
import {afterEach,beforeEach,expect,test,vi} from 'vitest';
import {AdminClient} from '../../shared/client';
import {ModelQuotaPanel} from './ModelQuotaPanel';
beforeEach(()=>{Object.defineProperty(window,'matchMedia',{writable:true,value:vi.fn(()=>({matches:false,addListener(){},removeListener(){},addEventListener(){},removeEventListener(){}}))});const original=window.getComputedStyle;vi.spyOn(window,'getComputedStyle').mockImplementation(element=>original(element));});
afterEach(()=>{cleanup();vi.restoreAllMocks();});
test('confirms zero model quota before writing',async()=>{
  const client=new AdminClient();const request=vi.spyOn(client,'request').mockResolvedValue({daily_limit:null,effective_daily_limit:1000} as never);
  render(<ModelQuotaPanel client={client} root="/tenants/t"/>);
  await screen.findByText('当前生效：每日 1000 次模型调用。');
  fireEvent.change(screen.getByLabelText('每日模型调用上限'),{target:{value:'0'}});
  fireEvent.click(screen.getByText('保存模型限额'));expect(request).toHaveBeenCalledTimes(1);
  fireEvent.click(screen.getByText('确认保存模型限额'));
  await screen.findByText('模型限额已保存；请刷新调用账本查看用量。');
  expect(request).toHaveBeenCalledWith('/tenants/t/model-quota','PUT',{daily_limit:0},expect.any(AbortSignal));
});
