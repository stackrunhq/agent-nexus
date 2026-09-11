import {useEffect, useRef, useState} from 'react';
import {Alert, Button, Modal} from 'antd';
import {AdminClient} from '../../shared/client';
interface Policy {daily_limit: number | null; active_limit: number | null; effective_daily_limit: number; effective_active_limit: number}
export function QuotaPanel({client, root}: {client: AdminClient; root: string}) {
  const [policy, setPolicy] = useState<Policy>();
  const [daily, setDaily] = useState('');
  const [active, setActive] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [confirm, setConfirm] = useState(false);
  const [saved, setSaved] = useState(false);
  const pending = useRef<AbortController | null>(null);
  async function run(save = false) {
    if (pending.current) return;
    const controller = new AbortController(); pending.current = controller; setBusy(true); setError(''); setSaved(false);
    try {
      const result = await client.request<Policy>(`${root}/index-quota`, save ? 'PUT' : 'GET', save ? {
        daily_limit: daily === '' ? null : Number(daily), active_limit: active === '' ? null : Number(active),
      } : undefined, controller.signal);
      if (!controller.signal.aborted) {setPolicy(result); setDaily(result.daily_limit?.toString() ?? ''); setActive(result.active_limit?.toString() ?? ''); setConfirm(false); setSaved(save);}
    } catch (e) {if (!controller.signal.aborted) setError((e as Error).message);}
    finally {if (!controller.signal.aborted) {pending.current = null; setBusy(false);}}
  }
  useEffect(() => {void run(); return () => {pending.current?.abort(); pending.current = null;};}, [client, root]);
  return <section aria-label="企业索引限额"><h4>企业索引限额</h4>
    <p>影响该企业全部应用。留空继承默认值，0 暂停新任务；已有任务继续执行，已有用量不会清零。</p>
    {policy && <p>当前生效：每日 {policy.effective_daily_limit} 次，活跃 {policy.effective_active_limit} 项。</p>}
    {error && <Alert type="error" message={error}/>}{saved && <Alert type="success" message="企业索引限额已保存；用量展示请刷新索引状态。"/>}
    <form onSubmit={e => {e.preventDefault(); setConfirm(true);}}>
      <label>每日任务上限 <input aria-label="每日任务上限" type="number" min={0} max={100000} step={1} value={daily} disabled={busy || !policy} onChange={e => setDaily(e.target.value)}/></label>
      <label>活跃任务上限 <input aria-label="活跃任务上限" type="number" min={0} max={100} step={1} value={active} disabled={busy || !policy} onChange={e => setActive(e.target.value)}/></label>
      <Button htmlType="submit" disabled={busy || !policy}>保存企业限额</Button>
      <Button disabled={busy} onClick={() => void run()}>重新读取限额</Button>
    </form>
    <Modal open={confirm} title="确认修改企业索引限额" okText="确认保存" cancelText="取消" confirmLoading={busy} cancelButtonProps={{disabled:busy}} closable={!busy} maskClosable={!busy} onCancel={() => setConfirm(false)} onOk={() => void run(true)}>
      <p>每日：{daily === '' ? '继承默认' : daily}；活跃：{active === '' ? '继承默认' : active}。修改立即影响后续新建任务，不取消正在执行或排队的任务。</p>
      {error && <Alert type="error" message={error}/>}
    </Modal>
  </section>;
}
