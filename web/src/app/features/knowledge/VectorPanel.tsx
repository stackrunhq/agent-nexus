import {useEffect, useRef, useState} from 'react';
import {Alert, Button, Modal} from 'antd';
import {AdminClient, ApiError} from '../../shared/client';
import {SearchPanel} from './SearchPanel';
import {AnswerPanel} from './AnswerPanel';
import {QuotaPanel} from './QuotaPanel';
import {ModelCallsPanel} from './ModelCallsPanel';
import {IndexJobHistory} from './IndexJobHistory';
import {SchedulerStatus, type Scheduling} from './SchedulerStatus';

interface Model {alias: string; enabled: boolean; capabilities: string[]; deployment: string}
interface Index {status: 'ready' | 'stale'; dimensions: number; chunks: number}
interface Usage {daily_limit: number; daily_used: number; reset_at: number; active: number; active_limit: number; scheduling?: Scheduling}
export function VectorPanel({client, root}: {client: AdminClient; root: string}) {
  const [models, setModels] = useState<Model[]>([]);
  const [chatModels, setChatModels] = useState<Model[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState('');
  const [alias, setAlias] = useState('');
  const [editQuota, setEditQuota] = useState(false);
  const [showCalls, setShowCalls] = useState(false);
  useEffect(() => {
    const controller = new AbortController();
    void Promise.all([
      client.request<Model[]>('/models', 'GET', undefined, controller.signal),
      client.request<{data: string[]}>(`${root.split('/applications/')[0]}/models`, 'GET', undefined, controller.signal),
    ]).then(([all, grants]) => {
      if (controller.signal.aborted) return;
      setModels(all.filter(model => model.enabled && model.capabilities.includes('embeddings') && grants.data.includes(model.alias)));
      setChatModels(all.filter(model => model.enabled && model.capabilities.includes('chat') && grants.data.includes(model.alias)));
      setLoaded(true);
    }).catch(e => {if (!controller.signal.aborted) setError((e as Error).message);});
    return () => controller.abort();
  }, [client, root]);
  return <section aria-label="向量索引管理"><h4>模型选择与索引管理</h4>
    <Button onClick={() => setEditQuota(value => !value)}>{editQuota ? '关闭限额设置' : '设置企业索引限额'}</Button>
    {editQuota && <QuotaPanel client={client} root={root.split('/applications/')[0]}/>}
    <Button onClick={() => setShowCalls(value => !value)}>{showCalls ? '关闭调用账本' : '查看模型调用账本'}</Button>
    {showCalls && <ModelCallsPanel client={client} root={root.split('/applications/')[0]}/>}
    {error && <Alert type="error" message={error}/>}
    <p>仅显示本企业已授权且启用的 embedding 模型。修改授权后请关闭并重新打开面板。</p>
    {loaded && !models.length && <p>没有可用模型，请在模型配置及企业授权中启用 embedding 模型。</p>}
    <label>索引模型 <select aria-label="索引模型" value={alias} onChange={e => setAlias(e.target.value)}>
      <option value="">请选择模型</option>{models.map(model => <option key={model.alias} value={model.alias}>{model.alias} · {model.deployment === 'local' ? '本地' : '云端'}</option>)}
    </select></label>
    {alias && <ModelIndex key={alias} client={client} root={root} model={models.find(model => model.alias === alias)!} chatModels={chatModels}/>}
  </section>;
}

function ModelIndex({client, root, model, chatModels}: {client: AdminClient; root: string; model: Model; chatModels: Model[]}) {
  const [usage, setUsage] = useState<Usage>();
  const [index, setIndex] = useState<Index>();
  const [missing, setMissing] = useState(false);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [confirm, setConfirm] = useState(false);
  const [revision, setRevision] = useState(0);
  const pending = useRef<AbortController | null>(null);
  async function refresh(signal: AbortSignal) {
    const quota = await client.request<Usage>(`${root.split('/applications/')[0]}/index-usage`, 'GET', undefined, signal);
    if (!signal.aborted) setUsage(quota);
    try {
      const result = await client.request<Index>(`${root}/vector-index?model=${encodeURIComponent(model.alias)}`, 'GET', undefined, signal);
      if (!signal.aborted) setIndex(result);
    } catch (e) {
      if (signal.aborted) return;
      if (e instanceof ApiError && e.code === 'index_missing') setMissing(true);
      else throw e;
    }
  }
  async function run(build = false) {
    if (pending.current) return;
    const controller = new AbortController(); pending.current = controller;
    setBusy(true); setError(''); setIndex(undefined); setMissing(false); setRevision(value => value + 1);
    try {
      if (build) await client.request(`${root}/index-jobs`, 'POST', {model: model.alias}, controller.signal);
      if (!controller.signal.aborted) {setConfirm(false); await refresh(controller.signal); setRevision(value => value + 1);}
    } catch (e) {if (!controller.signal.aborted) setError((e as Error).message);}
    finally {if (!controller.signal.aborted) {pending.current = null; setBusy(false);}}
  }
  useEffect(() => {void run(); return () => {pending.current?.abort(); pending.current = null;};}, [client, root, model.alias]);
  return <div>
    {error && <Alert type="error" message={error}/>}
    <p aria-live="polite">{busy ? '正在处理…' : missing ? '尚未建立索引' : index ? `${index.status === 'ready' ? '索引可用' : '索引已失效，请重建'} · ${index.chunks} 个分片 · ${index.dimensions} 维` : '索引状态未确认'}</p>
    <Button disabled={busy} onClick={() => void run()}>刷新索引状态</Button>
    {usage && <p>今日索引任务 {usage.daily_used}/{usage.daily_limit} · 活跃任务 {usage.active}/{usage.active_limit} · 重置时间 {new Date(usage.reset_at * 1000).toLocaleString()}</p>}
    {usage?.scheduling && <SchedulerStatus value={usage.scheduling}/>}
    <p>任务状态按需刷新；请启动索引 Worker。相同版本/模型的活跃任务复用，额度按当前企业配置执行。</p>
    <IndexJobHistory key={`${root}:${model.alias}`} client={client} root={root} model={model.alias} revision={revision}/>
    <Button disabled={busy} onClick={() => setConfirm(true)}>建立或重建索引</Button>
    {index?.status === 'ready' && <SearchPanel key={revision} client={client} root={`${root}/vector-search`} enabled={!busy} model={model.alias}/>}
    {index?.status === 'ready' && <SearchPanel key={`hybrid:${revision}`} client={client} root={`${root}/hybrid-search`} enabled={!busy} model={model.alias} hybrid/>}
    {index?.status === 'ready' && <AnswerPanel key={`answer:${revision}`} client={client} root={root} model={model.alias} chatModels={chatModels}/>}
    <Modal open={confirm} title="确认建立或重建索引" okText="确认建立" cancelText="取消" confirmLoading={busy} cancelButtonProps={{disabled: busy}} closable={!busy} maskClosable={!busy} onCancel={() => setConfirm(false)} onOk={() => void run(true)}>
      <p>模型：{model.alias}（{model.deployment === 'local' ? '本地' : '云端'}）。将当前版本已发布手册的原文分片发送到该模型，云端调用可能产生费用。</p>
      <p>提交后台任务，当前最多支持 128 个分片。Worker 成功后替换该模型的旧索引；失败保留旧索引。关闭页面或切换模型不停止任务。</p>
      {error && <Alert type="error" message={error}/>}
    </Modal>
  </div>;
}
