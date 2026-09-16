import {useEffect, useState} from 'react';
import {AdminClient} from '../../shared/client';
import {type IndexJob} from './IndexJobProgress';
import {indexFailure} from './indexFailure';
interface Call {id:string; status:string; error:string|null; elapsed_ms:number|null; input_tokens:number|null; output_tokens:number|null; association?:'exact'|'request_match'}
interface Detail {task:IndexJob & {request_id:string}; calls:{data:Call[];has_more:boolean}}
export function IndexJobDetails({client, root, id}: {client:AdminClient;root:string;id:string}) {
  const [offset,setOffset]=useState(0);
  const [revision,setRevision]=useState(0);
  const [value,setValue]=useState<Detail>();
  const [error,setError]=useState('');
  useEffect(()=>{
    const controller=new AbortController(); setValue(undefined); setError('');
    void client.request<Detail>(`${root}/index-jobs/${encodeURIComponent(id)}?offset=${offset}&limit=20`,'GET',undefined,controller.signal)
      .then(result=>{if(!controller.signal.aborted)setValue(result);})
      .catch(cause=>{if(!controller.signal.aborted)setError((cause as Error).message);});
    return ()=>controller.abort();
  },[client,root,id,offset,revision]);
  return <section aria-label="索引任务详情">
    <h5>任务详情与同请求调用</h5>
    <p>新索引调用按任务 ID 精确关联；未记录任务 ID 的调用按同企业、请求、模型和向量能力匹配，不等同精确任务归属。无记录不代表未发生费用，调用成功也不代表索引构建成功。</p>
    <button onClick={()=>{setOffset(0);setRevision(n=>n+1);}}>刷新任务详情</button>
    {error ? <p role="alert">{error}</p> : !value ? <p>正在加载详情…</p> : <>
      <p>任务 {value.task.id} · {value.task.status} · 尝试 {value.task.attempts} 次</p><p>请求 ID：{value.task.request_id}</p>
      {value.task.status==='failed' && <p>{value.task.error} · {indexFailure(value.task.error).suggestion}</p>}
      {!value.calls.data.length && <p>没有匹配的调用记录。</p>}
      {value.calls.data.map(call=><article key={call.id}>
        <p>调用 {call.id} · {call.status} · {call.association==='exact' ? '精确任务关联' : '请求匹配（归属未确认）'}{call.error ? ` · ${call.error}` : ''}</p>
        <p>耗时 {call.elapsed_ms ?? '未知'} ms · 输入 token {call.input_tokens ?? '未知'} · 输出 token {call.output_tokens ?? '未知'}</p>
      </article>)}
    </>}
    <button disabled={!value || offset===0} onClick={()=>setOffset(n=>n-20)}>上一页关联调用</button>
    <button disabled={!value?.calls.has_more || offset>=100000} onClick={()=>setOffset(n=>n+20)}>下一页关联调用</button>
  </section>;
}
