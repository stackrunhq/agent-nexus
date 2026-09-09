import { useEffect, useRef, useState } from 'react';
import { Alert, Button, Form, Input, Modal, Select, Space, Table, Tag } from 'antd';
import { AdminClient } from '../../shared/client';
import type { Credential, Event, Model, Tenant } from './types';
import { UsersPanel } from '../users/UsersPanel';
import { ApplicationsPanel } from '../applications/ApplicationsPanel';

const eventNames: Record<string, string> = { created: '创建企业', enabled: '启用', disabled: '停用', key_rotated: '轮换凭据', model_granted: '授权模型', model_revoked: '撤销模型' };

export function TenantPage() {
  const client = useRef(new AdminClient()).current;
  const session = useRef(0);
  const selectedRef = useRef('');
  const [connected, setConnected] = useState(false);
  const [busy, setBusy] = useState(false);
  const lock = useRef(false);
  const [error, setError] = useState('');
  const [tenants, setTenants] = useState<Tenant[]>([]);
  const [models, setModels] = useState<Model[]>([]);
  const [selected, setSelected] = useState<Tenant>();
  const [grants, setGrants] = useState<string[]>([]);
  const [events, setEvents] = useState<Event[]>([]);
  const [alias, setAlias] = useState<string>();
  const [credential, setCredential] = useState<Credential>();
  const [confirmation, setConfirmation] = useState<{ tenant: Tenant; rotate: boolean }>();
  const [mode, setMode] = useState('');
  const [loginMode, setLoginMode] = useState('token');
  const [loginForm] = Form.useForm();
  const [createForm] = Form.useForm();

  function disconnect() {
    session.current++; client.disconnect(); selectedRef.current = '';
    setConnected(false); setTenants([]); setModels([]); setSelected(undefined);
    setGrants([]); setEvents([]); setCredential(undefined); setConfirmation(undefined);
    setError(''); setAlias(undefined); setMode(''); loginForm.resetFields(); createForm.resetFields();
    lock.current = false; setBusy(false);
  }
  useEffect(() => {
    client.onExpired = () => { disconnect(); setError('个人会话已失效，请重新登录。'); };
    return () => { client.onExpired = undefined; client.disconnect(); };
  }, [client]);
  async function run(work: () => Promise<void>) {
    if (lock.current) return;
    lock.current = true; setBusy(true); setError('');
    const current = session.current;
    try { await work(); }
    catch (e) { if (current === session.current && (e as Error).name !== 'AbortError') setError((e as Error).message); }
    finally { if (current === session.current) { lock.current = false; setBusy(false); } }
  }
  async function refresh() {
    const result = await client.request<{data: Tenant[]}>('/tenants');
    setTenants(result.data);
  }
  async function details(tenant: Tenant) {
    selectedRef.current = tenant.id;
    setSelected(tenant); setGrants([]); setEvents([]); setAlias(undefined);
    const [access, history] = await Promise.all([
      client.request<{data: string[]}>(`/tenants/${tenant.id}/models`),
      client.request<{data: Event[]}>(`/tenants/${tenant.id}/events`),
    ]);
    if (selectedRef.current === tenant.id) { setGrants(access.data); setEvents(history.data); }
  }
  return <main className="tenant-page">
    <header><div><h1>企业管理</h1><p>管理企业接入凭据与可调用的模型。</p></div><nav><a href="/admin">模型工作台</a><a href="/docs">API 文档</a></nav></header>
    <section><h2>管理员连接</h2>{!connected ? <><Select aria-label="登录方式" value={loginMode} disabled={busy} onChange={value => {setLoginMode(value); loginForm.resetFields();}} options={[{value: 'token', label: '管理员令牌（初始接入）'}, {value: 'account', label: '个人账号登录'}]} />
    <Form form={loginForm} layout="inline" onFinish={({token, username, password}) => run(async () => {
      if (loginMode === 'account') await client.login(username, password);
      else client.connect(token);
      try {
        const [settings, list, modelList] = await Promise.all([
          client.request<{auth_mode: string}>('/settings'), client.request<{data: Tenant[]}>('/tenants'), client.request<Model[]>('/models'),
        ]);
        setMode(settings.auth_mode); setTenants(list.data); setModels(modelList); setConnected(true); loginForm.resetFields();
      } catch (e) { client.disconnect(); throw e; }
    })}>
      {loginMode === 'token' ? <Form.Item name="token" label="管理员令牌" rules={[{required: true, min: 32}]}><Input.Password autoComplete="off" disabled={busy}/></Form.Item> : <>
        <Form.Item name="username" label="用户名" rules={[{required: true}]}><Input autoComplete="username" disabled={busy}/></Form.Item>
        <Form.Item name="password" label="密码" rules={[{required: true}]}><Input.Password autoComplete="current-password" disabled={busy}/></Form.Item>
      </>}
      <Button htmlType="submit" type="primary" loading={busy}>连接</Button>
    </Form></> : <Space><span>已连接 · 会话仅保存在当前页面内存中</span><Button onClick={() => { const revocation = client.logout(); disconnect(); void revocation.catch(() => setError('本地已断开，服务端退出未确认；会话将在到期后失效。')); }}>断开连接</Button></Space>}</section>
    {error && <Alert type="error" showIcon message={error} />}
    {connected && <>
      <UsersPanel client={client} tenants={tenants}/>
      <ApplicationsPanel client={client} tenants={tenants}/>
      {mode !== 'tenant' && <Alert type="warning" showIcon message="当前为 bootstrap 模式：企业凭据和授权尚未用于调用鉴权。请部署管理员启用 tenant 模式。" />}
      <section><h2>企业列表</h2><div className="toolbar"><Form form={createForm} layout="inline" onFinish={({name}) => run(async () => {
        const created = await client.request<Tenant & Credential>('/tenants', 'POST', {name: name.trim()});
        setCredential({id: created.id, api_key: created.api_key}); createForm.resetFields(); await refresh();
      })}>
        <Form.Item name="name" label="企业名称" rules={[{required: true, whitespace: true, max: 120}]}><Input maxLength={120} disabled={busy}/></Form.Item>
        <Button type="primary" htmlType="submit" disabled={busy}>创建企业</Button>
      </Form><Button disabled={busy} onClick={() => run(async () => { await refresh(); if(selected) await details(selected); })}>刷新</Button></div>
      <Table rowKey="id" dataSource={tenants} pagination={{pageSize: 10}} scroll={{x: 700}} columns={[
        {title: '企业', dataIndex: 'name'}, {title: '企业 ID', dataIndex: 'id'},
        {title: '状态', render: (_, tenant) => <Tag color={tenant.enabled ? 'green' : 'default'}>{tenant.enabled ? '启用' : '停用'}</Tag>},
        {title: '操作', render: (_, tenant) => <Space wrap>
          <Button disabled={busy} onClick={() => run(() => details(tenant))}>授权与事件</Button>
          <Button disabled={busy} onClick={() => setConfirmation({tenant, rotate: false})}>{tenant.enabled ? '停用' : '启用'}</Button>
          <Button disabled={busy} onClick={() => setConfirmation({tenant, rotate: true})}>轮换凭据</Button>
        </Space>},
      ]}/></section>
      {selected && <section><h2>{selected.name} · 模型授权</h2><div className="toolbar">
        <Select aria-label="选择模型" placeholder="选择要授权的模型" value={alias} disabled={busy} style={{minWidth: 240}} onChange={setAlias} options={models.filter(m => !grants.includes(m.alias)).map(m => ({value: m.alias, label: `${m.alias}${m.enabled ? '' : '（模型已停用）'}`}))}/>
        <Button disabled={busy || !alias} onClick={() => run(async () => { await client.request(`/tenants/${selected.id}/models/${encodeURIComponent(alias!)}`, 'PUT'); await details(selected); })}>授权模型</Button>
      </div><Table rowKey="alias" dataSource={grants.map(alias => ({alias}))} pagination={false} columns={[
        {title: '已授权模型', dataIndex: 'alias'}, {title: '操作', render: (_, row) => <Button disabled={busy} onClick={() => run(async () => { await client.request(`/tenants/${selected.id}/models/${encodeURIComponent(row.alias)}`, 'DELETE'); await details(selected); })}>撤销授权</Button>},
      ]}/><h2>最近 100 条企业事件</h2><Table rowKey="id" dataSource={events} pagination={{pageSize: 10}} columns={[
        {title: '时间', dataIndex: 'created_at'}, {title: '事件', dataIndex: 'action', render: action => eventNames[action] || action}, {title: '模型', dataIndex: 'alias'},
      ]}/></section>}
    </>}
    <Modal title={confirmation?.rotate ? '确认轮换凭据' : '确认修改企业状态'} open={!!confirmation} confirmLoading={busy} onCancel={() => setConfirmation(undefined)} onOk={() => run(async () => {
      const {tenant, rotate} = confirmation!;
      if (rotate) setCredential(await client.request<Credential>(`/tenants/${tenant.id}/rotate-key`, 'POST'));
      else await client.request(`/tenants/${tenant.id}`, 'PATCH', {enabled: !tenant.enabled});
      setConfirmation(undefined); await refresh();
      if (selected?.id === tenant.id) await details({...tenant, enabled: rotate ? tenant.enabled : !tenant.enabled});
    })}><p>{confirmation?.tenant.name}</p><p>{confirmation?.rotate ? '旧凭据将立即失效，新凭据仅显示一次。请同步更新使用该凭据的应用。' : '修改后将影响该企业凭据的调用权限。'}</p></Modal>
    {credential && <Modal title="请安全保存企业凭据" open footer={<Button type="primary" onClick={() => setCredential(undefined)}>已保存，关闭</Button>} onCancel={() => setCredential(undefined)}>
      <p>仅本次显示，关闭或断开连接后无法再次查看。不要将凭据放入浏览器端应用。</p><p>企业 ID：{credential?.id}</p><pre className="credential">{credential?.api_key}</pre>
    </Modal>}
  </main>;
}
