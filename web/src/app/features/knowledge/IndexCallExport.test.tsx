// @vitest-environment jsdom
import {cleanup,fireEvent,render,screen,waitFor} from '@testing-library/react';
import {afterEach,expect,test,vi} from 'vitest';
import {AdminClient} from '../../shared/client';
import {IndexCallExport} from './IndexCallExport';
afterEach(()=>{cleanup();vi.restoreAllMocks();vi.unstubAllGlobals();});
test('downloads bounded JSON and reports truncation',async()=>{
 const client=new AdminClient(); const result={export:{returned:1000,truncated:true},filters:{call_error:''}};
 const request=vi.spyOn(client,'request').mockResolvedValue(result as never);
 const create=vi.fn((_blob:Blob)=> 'blob:test'); const revoke=vi.fn();
 class DownloadURL extends URL {static createObjectURL=create;static revokeObjectURL=revoke;}
 vi.stubGlobal('URL',DownloadURL);
 const click=vi.spyOn(HTMLAnchorElement.prototype,'click').mockImplementation(()=>{});
 render(<IndexCallExport client={client} path="/task/export?call_error="/>);
 fireEvent.click(screen.getByText('导出调用诊断 JSON'));
 await screen.findByText(/文件已标记截断/);
 expect(request.mock.calls[0][0]).toBe('/task/export?call_error=');
 expect(create.mock.calls[0][0]).toBeInstanceOf(Blob);
 expect(click).toHaveBeenCalledOnce();
 await waitFor(()=>expect(revoke).toHaveBeenCalledWith('blob:test'),{timeout:2000});
});
test('unmount aborts export without starting download',()=>{
 const client=new AdminClient();const request=vi.spyOn(client,'request').mockImplementation(()=>new Promise(()=>{}));
 const view=render(<IndexCallExport client={client} path="/task/export"/>);
 fireEvent.click(screen.getByText('导出调用诊断 JSON'));
 view.unmount();expect(request.mock.calls[0][3]?.aborted).toBe(true);
});
