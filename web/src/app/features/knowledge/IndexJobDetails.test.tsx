// @vitest-environment jsdom
import {cleanup,fireEvent,render,screen,waitFor} from '@testing-library/react';
import {afterEach,expect,test,vi} from 'vitest';
import {AdminClient} from '../../shared/client';
import {IndexJobDetails} from './IndexJobDetails';
afterEach(()=>{cleanup();vi.restoreAllMocks();});
test('shows unknown usage and pages correlated calls',async()=>{
 const client=new AdminClient();
 const request=vi.spyOn(client,'request').mockResolvedValue({task:{id:'job',status:'failed',attempts:1,error:'provider_timeout',request_id:'req'},calls:{data:[{id:'call',status:'pending',error:null,elapsed_ms:null,input_tokens:null,output_tokens:0,association:'exact',index_attempt:2,index_batch_start:16,index_batch_size:3},{id:'old',status:'succeeded',error:null,elapsed_ms:1,input_tokens:0,output_tokens:0,association:'request_match'}],has_more:true}} as never);
 render(<IndexJobDetails client={client} root="/v" id="job"/>);
 await screen.findByText('请求 ID：req');
 expect(screen.getByText(/不等同精确任务归属/)).toBeTruthy();
 expect(screen.getByText(/输入 token 未知/)).toBeTruthy();
 expect(screen.getByText(/精确任务关联/)).toBeTruthy();
 expect(screen.getByText(/请求匹配（归属未确认）/)).toBeTruthy();
 expect(screen.getByText('第 2 次尝试 · 分片 17–19（3 个）')).toBeTruthy();
 expect(screen.getByText('尝试与批次位置未知')).toBeTruthy();
 fireEvent.click(screen.getByText('下一页关联调用'));
 await waitFor(()=>expect(request.mock.calls.at(-1)?.[0]).toContain('offset=20'));
 fireEvent.change(screen.getByLabelText('调用尝试'),{target:{value:'2'}});
 await waitFor(()=>expect(request.mock.calls.at(-1)?.[0]).toContain('offset=0&limit=20&attempt=2'));
 fireEvent.change(screen.getByLabelText('调用状态'),{target:{value:'failed'}});
 await waitFor(()=>expect(request.mock.calls.at(-1)?.[0]).toContain('call_status=failed'));
 fireEvent.click(screen.getByText('清除调用筛选'));
 await waitFor(()=>expect(request.mock.calls.at(-1)?.[0]).not.toContain('attempt='));
 expect(request.mock.calls.at(-1)?.[0]).not.toContain('call_status=');
});
test('unmount cancels detail request',()=>{
 const client=new AdminClient();
 const request=vi.spyOn(client,'request').mockImplementation(()=>new Promise(()=>{}));
 const view=render(<IndexJobDetails client={client} root="/v" id="job"/>);
 view.unmount();expect(request.mock.calls[0][3]?.aborted).toBe(true);
});
