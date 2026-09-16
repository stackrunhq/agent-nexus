import {useEffect, useState} from 'react';
import {AdminClient} from '../../shared/client';
import {type IndexJob} from './IndexJobProgress';
import {indexFailure} from './indexFailure';
import {IndexAttemptSummary, type AttemptSummary} from './IndexAttemptSummary';
import {IndexCallExport} from './IndexCallExport';
import {IndexExportAudit} from './IndexExportAudit';
interface Call {id:string; status:string; error:string|null; elapsed_ms:number|null; input_tokens:number|null; output_tokens:number|null; association?:'exact'|'request_match';index_attempt?:number|null;index_batch_start?:number|null;index_batch_size?:number|null}
interface Detail {task:IndexJob & {request_id:string}; calls:{data:Call[];has_more:boolean};summary?:AttemptSummary}
export function IndexJobDetails({client, root, id}: {client:AdminClient;root:string;id:string}) {
  const [offset,setOffset]=useState(0);
  const [attempt,setAttempt]=useState('');
  const [callStatus,setCallStatus]=useState('');
  const [callError,setCallError]=useState<string|null>(null);
  const [errorDraft,setErrorDraft]=useState('');
  const [revision,setRevision]=useState(0);
  const [value,setValue]=useState<Detail>();
  const [error,setError]=useState('');
  const exportParams=new URLSearchParams();
  if(attempt)exportParams.set('attempt',attempt);
  if(callStatus)exportParams.set('call_status',callStatus);
  if(callError!==null)exportParams.set('call_error',callError);
  const exportPath=`${root}/index-jobs/${encodeURIComponent(id)}/export?${exportParams}`;
  useEffect(()=>{
    const controller=new AbortController(); setValue(undefined); setError('');
    const params=new URLSearchParams({offset:String(offset),limit:'20'});
    if(attempt)params.set('attempt',attempt);
    if(callStatus)params.set('call_status',callStatus);
    if(callError!==null)params.set('call_error',callError);
    void client.request<Detail>(`${root}/index-jobs/${encodeURIComponent(id)}?${params}`,'GET',undefined,controller.signal)
      .then(result=>{if(!controller.signal.aborted)setValue(result);})
      .catch(cause=>{if(!controller.signal.aborted)setError((cause as Error).message);});
    return ()=>controller.abort();
  },[client,root,id,offset,revision,attempt,callStatus,callError]);
  return <section aria-label="索引任务详情">
    <h5>任务详情与同请求调用</h5>
    <p>新索引调用按任务 ID 精确关联；未记录任务 ID 的调用按同企业、请求、模型和向量能力匹配，不等同精确任务归属。无记录不代表未发生费用，调用成功也不代表索引构建成功。</p>
    <button onClick={()=>{setOffset(0);setRevision(n=>n+1);}}>刷新任务详情</button>
    <label>调用尝试 <select aria-label="调用尝试" value={attempt} onChange={e=>{setAttempt(e.target.value);setOffset(0);}}><option value="">全部关联方式</option>{[1,2,3].map(n=><option key={n} value={String(n)}>第 {n} 次尝试（精确关联）</option>)}<option value="unknown">尝试未知（精确关联）</option></select></label>
    <label>调用状态 <select aria-label="调用状态" value={callStatus} onChange={e=>{setCallStatus(e.target.value);setOffset(0);}}><option value="">全部状态</option><option value="pending">待确认</option><option value="succeeded">成功</option><option value="failed">失败</option></select></label>
    <form onSubmit={event=>{event.preventDefault();setCallError(errorDraft.trim() || null);setCallStatus('failed');setOffset(0);}}>
      <label>调用错误码 <input aria-label="调用错误码" value={errorDraft} maxLength={200} onChange={event=>setErrorDraft(event.target.value)}/></label>
      <button type="submit">筛选调用错误码</button><button type="button" onClick={()=>{setCallError('');setErrorDraft('');setCallStatus('failed');setOffset(0);}}>仅缺失调用错误码</button>
    </form>
    <p>生效调用错误码：{callError===null?'不限':callError===''?'缺失错误码':callError}</p>
    <button onClick={()=>{setAttempt('');setCallStatus('');setCallError(null);setErrorDraft('');setOffset(0);}}>清除调用筛选</button>
    <p>明细按上述条件查询；选定尝试时仅显示精确关联记录。汇总始终覆盖全任务，不随筛选变化。</p>
    <IndexCallExport key={exportPath} client={client} path={exportPath}/>
    <IndexExportAudit key={root} client={client} root={root}/>
    {error ? <p role="alert">{error}</p> : !value ? <p>正在加载详情…</p> : <>
      <p>任务 {value.task.id} · {value.task.status} · 尝试 {value.task.attempts} 次</p><p>请求 ID：{value.task.request_id}</p>
      {value.task.status==='failed' && <p>{value.task.error} · {indexFailure(value.task.error).suggestion}</p>}
      {value.summary && <IndexAttemptSummary value={value.summary} onSelect={(number,status)=>{setAttempt(number===null?'unknown':String(number));setCallStatus(status);setCallError(null);setErrorDraft('');setOffset(0);}} onError={(number,code)=>{setAttempt(number===null?'unknown':String(number));setCallStatus('failed');setCallError(code??'');setErrorDraft(code??'');setOffset(0);}}/>}
      {!value.calls.data.length && <p>没有匹配的调用记录。</p>}
      {value.calls.data.map(call=><article key={call.id}>
        <p>调用 {call.id} · {call.status} · {call.association==='exact' ? '精确任务关联' : '请求匹配（归属未确认）'}{call.error ? ` · ${call.error}` : ''}</p>
        <p>耗时 {call.elapsed_ms ?? '未知'} ms · 输入 token {call.input_tokens ?? '未知'} · 输出 token {call.output_tokens ?? '未知'}</p>
        <p>{call.index_attempt != null && call.index_batch_start != null && call.index_batch_size != null ? `第 ${call.index_attempt} 次尝试 · 分片 ${call.index_batch_start+1}–${call.index_batch_start+call.index_batch_size}（${call.index_batch_size} 个）` : '尝试与批次位置未知'}</p>
      </article>)}
    </>}
    <button disabled={!value || offset===0} onClick={()=>setOffset(n=>n-20)}>上一页关联调用</button>
    <button disabled={!value?.calls.has_more || offset>=100000} onClick={()=>setOffset(n=>n+20)}>下一页关联调用</button>
  </section>;
}
