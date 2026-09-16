import {useEffect,useRef,useState} from 'react';
import {AdminClient} from '../../shared/client';
interface Result {export:{returned:number;truncated:boolean}}
export function IndexCallExport({client,path}:{client:AdminClient;path:string}) {
  const pending=useRef<AbortController|null>(null);
  const [busy,setBusy]=useState(false);
  const [message,setMessage]=useState('');
  useEffect(()=>{pending.current=null;setBusy(false);setMessage('');return ()=>{pending.current?.abort();};},[client,path]);
  async function download() {
    if(pending.current)return;
    const controller=new AbortController();pending.current=controller;setBusy(true);setMessage('');
    try {
      const result=await client.request<Result>(path,'GET',undefined,controller.signal);
      if(controller.signal.aborted)return;
      const url=URL.createObjectURL(new Blob([JSON.stringify(result,null,2)],{type:'application/json;charset=utf-8'}));
      const link=document.createElement('a');
      try {link.href=url;link.download='index-call-diagnostics.json';document.body.appendChild(link);link.click();}
      finally {link.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);}
      setMessage(`已生成 ${result.export.returned} 条调用记录${result.export.truncated?'；超过 1000 条，文件已标记截断，请缩小筛选范围。':'。'}`);
    } catch(error) {if(!controller.signal.aborted)setMessage((error as Error).message);}
    finally {if(!controller.signal.aborted){pending.current=null;setBusy(false);}}
  }
  return <div><button disabled={busy} onClick={()=>void download()}>{busy?'正在导出…':'导出调用诊断 JSON'}</button><p>按当前生效筛选从第一条导出，最多 1000 条；包含全任务汇总，不包含手册或模型凭据。</p>{message&&<p role="status">{message}</p>}</div>;
}
