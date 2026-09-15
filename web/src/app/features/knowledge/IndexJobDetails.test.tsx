// @vitest-environment jsdom
import {cleanup,fireEvent,render,screen,waitFor} from '@testing-library/react';
import {afterEach,expect,test,vi} from 'vitest';
import {AdminClient} from '../../shared/client';
import {IndexJobDetails} from './IndexJobDetails';
afterEach(()=>{cleanup();vi.restoreAllMocks();});
test('shows unknown usage and pages correlated calls',async()=>{
 const client=new AdminClient();
 const request=vi.spyOn(client,'request').mockResolvedValue({task:{id:'job',status:'failed',attempts:1,error:'provider_timeout',request_id:'req'},calls:{data:[{id:'call',status:'pending',error:null,elapsed_ms:null,input_tokens:null,output_tokens:0}],has_more:true}} as never);
 render(<IndexJobDetails client={client} root="/v" id="job"/>);
 await screen.findByText('请求 ID：req');
 expect(screen.getByText(/不等同精确任务归属/)).toBeTruthy();
 expect(screen.getByText(/输入 token 未知/)).toBeTruthy();
 fireEvent.click(screen.getByText('下一页关联调用'));
 await waitFor(()=>expect(request.mock.calls.at(-1)?.[0]).toContain('offset=20'));
});
test('unmount cancels detail request',()=>{
 const client=new AdminClient();
 const request=vi.spyOn(client,'request').mockImplementation(()=>new Promise(()=>{}));
 const view=render(<IndexJobDetails client={client} root="/v" id="job"/>);
 view.unmount();expect(request.mock.calls[0][3]?.aborted).toBe(true);
});
