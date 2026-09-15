import {useEffect, useState} from 'react';
import {AdminClient} from '../../shared/client';
import {IndexJobProgress, type IndexJob} from './IndexJobProgress';

export function IndexJobHistory({client, root, model, revision}: {client: AdminClient; root: string; model: string; revision: number}) {
  const [query, setQuery] = useState({offset:0, status:'', error:'', missing:false});
  const [draft, setDraft] = useState('');
  const [page, setPage] = useState<{data: IndexJob[]; has_more: boolean}>();
  const [error, setError] = useState('');
  const [refresh, setRefresh] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    setPage(undefined); setError('');
    const params = new URLSearchParams({model, offset:String(query.offset), limit:'20'});
    if (query.status) params.set('status', query.status);
    if (query.error || query.missing) params.set('error', query.error);
    void client.request<{data: IndexJob[]; has_more: boolean}>(`${root}/index-jobs?${params}`, 'GET', undefined, controller.signal)
      .then(result => {if (!controller.signal.aborted) setPage(result);})
      .catch(cause => {if (!controller.signal.aborted) setError((cause as Error).message);});
    return () => controller.abort();
  }, [client, root, model, revision, query, refresh]);
  return <section aria-label="索引任务历史">
    <label>任务状态 <select aria-label="任务状态" value={query.status} onChange={event => setQuery({offset:0,status:event.target.value,error:'',missing:false})}>
      <option value="">全部状态</option><option value="queued">排队中</option><option value="processing">构建中</option><option value="succeeded">构建成功</option><option value="failed">构建失败</option>
    </select></label>
    <form onSubmit={event => {event.preventDefault(); setQuery({offset:0,status:'failed',error:draft.trim(),missing:false});}}>
      <label>失败错误码 <input aria-label="失败错误码" value={draft} maxLength={200} onChange={event => setDraft(event.target.value)}/></label>
      <button type="submit">按错误码查询</button>
      <button type="button" onClick={() => {setDraft(''); setQuery({offset:0,status:'failed',error:'',missing:true});}}>缺失错误码</button>
      <button type="button" onClick={() => {setDraft(''); setQuery({offset:0,status:'',error:'',missing:false});}}>清除筛选</button>
    </form>
    <p>当前模型 {model} 的服务端历史查询 · 第 {query.offset / 20 + 1} 页，每页最多 20 条。任务变化时翻页结果可能移动，可返回首页刷新。</p>
    <p>生效错误码：{query.missing ? '缺失错误码' : query.error || '不限'}</p>
    <button onClick={() => {setQuery(value => ({...value,offset:0})); setRefresh(value => value + 1);}}>刷新任务历史</button>
    {error ? <p role="alert">{error}</p> : !page ? <p>正在加载任务历史…</p> : <>
      {!page.data.length && <p>没有符合条件的任务。</p>}
      {page.data.map(task => <IndexJobProgress key={task.id} task={task}/>)}
    </>}
    <button disabled={!page || query.offset === 0} onClick={() => setQuery(value => ({...value,offset:value.offset - 20}))}>上一页</button>
    <button disabled={!page?.has_more || query.offset >= 1000000} onClick={() => setQuery(value => ({...value,offset:value.offset + 20}))}>下一页</button>
  </section>;
}
