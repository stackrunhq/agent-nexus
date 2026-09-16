// @vitest-environment jsdom
import {cleanup,fireEvent,render,screen,waitFor} from '@testing-library/react';
import {afterEach,expect,test,vi} from 'vitest';
import {AdminClient} from '../../shared/client';
import {IndexExportAudit} from './IndexExportAudit';
afterEach(()=>{cleanup();vi.restoreAllMocks();});
test('loads on demand, preserves empty error and pages by event cursor',async()=>{
 const client=new AdminClient();const request=vi.spyOn(client,'request').mockResolvedValueOnce({data:[{id:9,actor:'platform_admin',request_id:'req',created_at:1,readable:true,resource:{job_id:'job'},filters:{attempt:null,call_status:null,call_error:''},export:{returned:1000,limit:1000,truncated:true}}],next_cursor:9} as never).mockResolvedValueOnce({data:[{id:8,actor:'admin',request_id:'old',created_at:1,readable:false}],next_cursor:null} as never);
 render(<IndexExportAudit client={client} root="/version"/>);
 expect(request).not.toHaveBeenCalled();
 fireEvent.click(screen.getByText('查看版本导出审计'));
 await screen.findByText(/缺失错误码/);expect(screen.getByText(/已截断/)).toBeTruthy();
 fireEvent.click(screen.getByText('更早的导出记录'));
 await screen.findByText('该记录格式无法解析。');
 expect(request.mock.calls[1][0]).toContain('before=9');
 fireEvent.click(screen.getByText('刷新导出审计'));
 await waitFor(()=>expect(request.mock.calls[2][0]).toBe('/version/index-export-events?limit=20'));
});
test('closing cancels pending audit request',()=>{
 const client=new AdminClient();const request=vi.spyOn(client,'request').mockImplementation(()=>new Promise(()=>{}));
 render(<IndexExportAudit client={client} root="/version"/>);
 fireEvent.click(screen.getByText('查看版本导出审计'));
 fireEvent.click(screen.getByText('关闭导出审计'));
 expect(request.mock.calls[0][3]?.aborted).toBe(true);
});
