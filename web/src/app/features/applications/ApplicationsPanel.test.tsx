// @vitest-environment jsdom
import {cleanup, fireEvent, render, screen, waitFor, within} from '@testing-library/react';
import {afterEach, beforeEach, expect, test, vi} from 'vitest';
import {AdminClient} from '../../shared/client';
import {ApplicationsPanel} from './ApplicationsPanel';

beforeEach(()=>{
  Object.defineProperty(window,'matchMedia',{writable:true,value:vi.fn(()=>({matches:false,addListener(){},removeListener(){},addEventListener(){},removeEventListener(){}}))});
  vi.stubGlobal('ResizeObserver',class{observe(){} unobserve(){} disconnect(){}});
  const computed=window.getComputedStyle;
  vi.spyOn(window,'getComputedStyle').mockImplementation(element=>computed(element));
});
afterEach(()=>{cleanup();vi.restoreAllMocks();vi.unstubAllGlobals();});

test('application version publication is scoped and requires confirmation',async()=>{
  const client=new AdminClient();
  let published=false;
  const request=vi.spyOn(client,'request').mockImplementation(async(path,method)=>{
    if(path.includes('/documents'))return {data:[]} as never;
    if(method==='PATCH'){published=true;return {} as never;}
    if(path.endsWith('/events'))return {data:[]} as never;
    if(path.endsWith('/versions'))return {data:[{id:'v1',version:'1.0',notes:'',status:published?'published':'draft'}]} as never;
    return {data:[{id:'a1',tenant_id:'t1',name:'ERP',slug:'erp',enabled:true}]} as never;
  });
  render(<ApplicationsPanel client={client} tenants={[{id:'t1',name:'Tenant A',enabled:true}]}/>);
  fireEvent.mouseDown(screen.getByRole('combobox',{name:'应用所属企业'}));
  fireEvent.click(screen.getByText('Tenant A'));
  fireEvent.click(await screen.findByText('管理版本'));
  fireEvent.click(await screen.findByText('管理知识库'));
  await waitFor(()=>expect(request).toHaveBeenCalledWith('/tenants/t1/applications/a1/versions/v1/documents?offset=0&limit=20','GET',undefined,expect.any(AbortSignal)));
  fireEvent.click(await screen.findByText('发布版本'));
  expect(request.mock.calls.some(([,method])=>method==='PATCH')).toBe(false);
  fireEvent.click(within(screen.getByRole('dialog')).getByRole('button',{name:/OK|确.*定/}));
  await waitFor(()=>expect(screen.queryByText('已发布')).not.toBeNull());
  expect(request).toHaveBeenCalledWith('/tenants/t1/applications/a1/versions/v1','PATCH',{status:'published'});
});
