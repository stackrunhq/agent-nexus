import {useEffect, useRef, useState} from 'react';
import {Alert, Button, Modal} from 'antd';
import {AdminClient} from '../../shared/client';
export function ModelQuotaPanel({client, root}: {client:AdminClient;root:string}) {
  const [value, setValue] = useState('');
  const [effective, setEffective] = useState<number>();
  const [busy, setBusy] = useState(false);
  const [confirm, setConfirm] = useState(false);
  const [error, setError] = useState('');
  const [saved, setSaved] = useState(false);
  const pending = useRef<AbortController | null>(null);
  async function run(save=false) {
    if (pending.current) return;
    const controller = new AbortController(); pending.current=controller; setBusy(true);setError('');setSaved(false);
    try {
      const result = await client.request<{daily_limit:number|null;effective_daily_limit:number}>(`${root}/model-quota`,save?'PUT':'GET',save?{daily_limit:value===''?null:Number(value)}:undefined,controller.signal);
      if (!controller.signal.aborted) {setValue(result.daily_limit?.toString() ?? '');setEffective(result.effective_daily_limit);setConfirm(false);setSaved(save);}
    } catch(e) {if (!controller.signal.aborted) setError((e as Error).message);}
    finally {if (!controller.signal.aborted) {pending.current=null;setBusy(false);}}
  }
  useEffect(() => {void run();return () => {pending.current?.abort();pending.current=null;};},[client,root]);
  return <section aria-label="企业模型调用限额"><h4>企业每日模型调用限额</h4>
    <p>留空继承默认值，0 暂停新调用。覆盖该企业所有模型和应用，不取消已开始调用、不清空用量。一次问答或索引可能消耗多次调用。</p>
    {effective!==undefined && <p>当前生效：每日 {effective} 次模型调用。</p>}
    {error && <Alert type="error" message={error}/>}{saved && <Alert type="success" message="模型限额已保存；请刷新调用账本查看用量。"/>}
    <form onSubmit={e=>{e.preventDefault();setConfirm(true);}}>
      <label>每日模型调用上限 <input aria-label="每日模型调用上限" type="number" min={0} max={1000000} step={1} value={value} disabled={busy||effective===undefined} onChange={e=>setValue(e.target.value)}/></label>
      <Button htmlType="submit" disabled={busy||effective===undefined}>保存模型限额</Button>
      <Button disabled={busy} onClick={()=>void run()}>重新读取模型限额</Button>
    </form>
    <Modal open={confirm} title="确认企业模型调用限额" okText="确认保存模型限额" cancelText="取消" confirmLoading={busy} closable={!busy} maskClosable={!busy} cancelButtonProps={{disabled:busy}} onCancel={()=>setConfirm(false)} onOk={()=>void run(true)}>
      <p>每日模型调用：{value===''?'继承默认':value}。影响该企业所有模型调用入口。</p>{error&&<Alert type="error" message={error}/>}
    </Modal>
  </section>;
}
