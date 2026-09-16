import {useEffect,useState} from 'react';
import {AdminClient} from '../../shared/client';
interface Event {id:number;actor:string;request_id:string;created_at:number;readable:boolean;resource?:{job_id:string};filters?:{attempt:string|null;call_status:string|null;call_error:string|null};export?:{returned:number;limit:number;truncated:boolean}}
interface Page {data:Event[];next_cursor:number|null}
export function IndexExportAudit({client,root}:{client:AdminClient;root:string}) {
 const [open,setOpen]=useState(false),[cursor,setCursor]=useState<number>(),[revision,setRevision]=useState(0);
 const [page,setPage]=useState<Page>(),[error,setError]=useState('');
 const [jobDraft,setJobDraft]=useState(''),[actorDraft,setActorDraft]=useState('');
 const [filters,setFilters]=useState({job:'',actor:''});
 useEffect(()=>{
  if(!open)return;
  const controller=new AbortController();setPage(undefined);setError('');
  const params=new URLSearchParams({limit:'20'});
  if(cursor!==undefined)params.set('before',String(cursor));
  if(filters.job)params.set('job_id',filters.job);
  if(filters.actor)params.set('actor',filters.actor);
  void client.request<Page>(`${root}/index-export-events?${params}`,'GET',undefined,controller.signal)
   .then(value=>{if(!controller.signal.aborted)setPage(value);})
   .catch(cause=>{if(!controller.signal.aborted)setError((cause as Error).message);});
  return ()=>controller.abort();
 },[client,root,open,cursor,revision,filters]);
 return <section aria-label="版本导出审计">
  <button onClick={()=>setOpen(value=>!value)}>{open?'关闭导出审计':'查看版本导出审计'}</button>
  {open&&<><p>当前版本的全部导出生成记录，不随调用筛选变化。记录不代表文件已保存；platform_admin 为共享管理员身份。</p>
   <button onClick={()=>{setCursor(undefined);setRevision(n=>n+1);}}>刷新导出审计</button>
   <form onSubmit={event=>{event.preventDefault();setCursor(undefined);setFilters({job:jobDraft.trim(),actor:actorDraft.trim()});}}>
    <label>审计任务 ID <input aria-label="审计任务 ID" maxLength={200} value={jobDraft} onChange={event=>setJobDraft(event.target.value)}/></label>
    <label>审计操作者 <input aria-label="审计操作者" maxLength={200} value={actorDraft} onChange={event=>setActorDraft(event.target.value)}/></label>
    <button type="submit">筛选导出审计</button><button type="button" onClick={()=>{setJobDraft('');setActorDraft('');setFilters({job:'',actor:''});setCursor(undefined);}}>清除审计筛选</button>
   </form>
   <p>生效审计条件：任务 {filters.job||'不限'} · 操作者 {filters.actor||'不限'}（精确匹配）</p>
   {error?<p role="alert">{error}</p>:!page?<p>正在加载导出审计…</p>:<>
    {!page.data.length&&<p>{page.next_cursor?'本段没有匹配记录，请继续查看更早记录。':'当前条件下没有更多导出审计。'}</p>}
    {page.data.map(event=><article key={event.id}><p>操作者：{event.actor} · {new Date(event.created_at*1000).toLocaleString()} · 请求：{event.request_id}</p>
     {event.readable&&event.resource&&event.filters&&event.export?<><p>任务：{event.resource.job_id} · 服务端已生成 · {event.export.returned}/{event.export.limit} 条 · {event.export.truncated?'已截断':'未截断'}</p>
      <p>尝试：{event.filters.attempt??'不限'} · 状态：{event.filters.call_status??'不限'} · 错误码：{event.filters.call_error===null?'不限':event.filters.call_error===''?'缺失错误码':event.filters.call_error}</p></>:<p>该记录格式无法解析。</p>}
    </article>)}
   </>}
   <button disabled={!page?.next_cursor} onClick={()=>setCursor(page!.next_cursor!)}>更早的导出记录</button>
  </>}
 </section>;
}
