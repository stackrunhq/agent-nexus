import {useEffect, useRef, useState} from 'react';
import {Alert, Button} from 'antd';
import {AdminClient} from '../../shared/client';
interface Call {id: string; request_id: string; model: string; capability: string; status: string; created_at: number; elapsed_ms: number | null; input_tokens: number | null; output_tokens: number | null; error: string | null}
interface ModelTotal {model:string;capability:string;calls:number;succeeded:number;failed:number;pending:number;known_input_tokens:number|null;known_output_tokens:number|null;unknown_input_calls:number;unknown_output_calls:number}
interface Summary {daily_used:number;daily_limit:number;reset_at:number;models?:ModelTotal[]}
export function ModelCallsPanel({client, root}: {client: AdminClient; root: string}) {
  const [rows, setRows] = useState<Call[]>([]);
  const [usage, setUsage] = useState<Summary>();
  const [offset, setOffset] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const pending = useRef<AbortController | null>(null);
  async function load(start: number) {
    if (pending.current) return;
    const controller = new AbortController(); pending.current = controller; setBusy(true); setError('');
    try {
      const summary = await client.request<Summary>(`${root}/model-usage`, 'GET', undefined, controller.signal);
      if (controller.signal.aborted) return;
      setUsage(summary);
      const result = await client.request<{data: Call[]}>(`${root}/model-calls?offset=${start}&limit=20`, 'GET', undefined, controller.signal);
      if (!controller.signal.aborted) {setRows(result.data); setOffset(start);}
    } catch (e) {if (!controller.signal.aborted) setError((e as Error).message);}
    finally {if (!controller.signal.aborted) {pending.current = null; setBusy(false);}}
  }
  useEffect(() => {void load(0); return () => {pending.current?.abort(); pending.current = null;};}, [client, root]);
  return <section aria-label="企业模型调用账本"><h4>企业模型调用账本</h4>
    <p>包含该企业全部应用的模型调用。未知 token 不按零计算；成功只表示模型调用成功，不代表最终业务成功。待确认记录可能已产生上游费用。</p>
    {usage && <p>今日模型调用 {usage.daily_used}/{usage.daily_limit} · 重置时间 {new Date(usage.reset_at * 1000).toLocaleString()}。按模型调用次数计量，问答或索引可能消耗多次。</p>}
    {usage?.models?.map(total => <article key={`${total.model}:${total.capability}`}><h5>今日 · {total.model} · {total.capability}</h5>
      <p>调用 {total.calls} · 成功 {total.succeeded} · 失败 {total.failed} · 待确认 {total.pending}</p>
      <p>已知输入 token：{total.known_input_tokens ?? '未知'}（{total.unknown_input_calls} 次未返回）；已知输出 token：{total.known_output_tokens ?? '未知'}（{total.unknown_output_calls} 次未返回）。已知合计不代表完整用量。</p>
    </article>)}
    {error && <Alert type="error" message={error}/>}
    <Button disabled={busy} onClick={() => void load(0)}>刷新调用记录</Button>
    {!busy && !rows.length && <p>暂无调用记录。</p>}
    {rows.map(row => <article key={row.id}><p>{new Date(row.created_at * 1000).toLocaleString()} · {row.model} · {row.capability} · {({pending:'待确认',succeeded:'成功',failed:'失败'} as Record<string,string>)[row.status] || row.status}</p>
      <p>输入 token：{row.input_tokens ?? '未知'}；输出 token：{row.output_tokens ?? '未知'}；耗时：{row.elapsed_ms === null ? '未知' : `${row.elapsed_ms} ms`}</p>
      <p>请求 ID：{row.request_id}{row.error ? ` · ${row.error}` : ''}</p></article>)}
    <Button disabled={busy || offset === 0} onClick={() => void load(offset - 20)}>上一页调用</Button>
    <Button disabled={busy || rows.length < 20 || offset >= 100000} onClick={() => void load(offset + 20)}>下一页调用</Button>
  </section>;
}
