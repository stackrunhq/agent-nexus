import { useRef, useState } from 'react';
import { Alert, Button, Form, Input, Modal, Select, Space, Table } from 'antd';
import { AdminClient } from '../../shared/client';
import type { Tenant } from '../tenants/types';
import { KnowledgePanel } from '../knowledge/KnowledgePanel';

interface Application { id: string; tenant_id: string; slug: string; name: string; description: string; enabled: boolean }
interface Version { id: string; version: string; notes: string; status: 'draft' | 'published' | 'retired' }
interface Event { id: number; actor: string; action: string; request_id: string; created_at: number }
const labels = {draft: '草稿', published: '已发布', retired: '已退役'};

export function ApplicationsPanel({client, tenants}: {client: AdminClient; tenants: Tenant[]}) {
  const [tenant, setTenant] = useState<string>();
  const [apps, setApps] = useState<Application[]>([]);
  const [selected, setSelected] = useState<Application>();
  const [versions, setVersions] = useState<Version[]>([]);
  const [events, setEvents] = useState<Event[]>([]);
  const [documentVersion, setDocumentVersion] = useState<Version>();
  const [busy, setBusy] = useState(false);
  const lock = useRef(false);
  const [error, setError] = useState('');
  const [change, setChange] = useState<{app: Application; version?: Version}>();
  const [appForm] = Form.useForm();
  const [versionForm] = Form.useForm();
  const root = (id: string) => `/tenants/${id}/applications`;
  async function run(work: () => Promise<void>) {
    if (lock.current) return;
    lock.current = true; setBusy(true); setError('');
    try { await work(); } catch(e) {if ((e as Error).name !== 'AbortError') setError((e as Error).message);}
    finally {lock.current = false; setBusy(false);}
  }
  async function list(id: string) {
    setApps((await client.request<{data: Application[]}>(root(id))).data);
  }
  async function details(app: Application) {
    setSelected(app); setDocumentVersion(undefined); setVersions([]); setEvents([]); if(selected) versionForm.resetFields();
    const [releases, history] = await Promise.all([
      client.request<{data: Version[]}>(`${root(app.tenant_id)}/${app.id}/versions`),
      client.request<{data: Event[]}>(`${root(app.tenant_id)}/${app.id}/events`),
    ]);
    setVersions(releases.data); setEvents(history.data);
  }
  return <section><h2>应用与版本</h2><p>将使用手册归属到具体企业应用和产品版本。选择“管理知识库”上传手册、查看分片并发布文档。</p>
    {error && <Alert type="error" message={error}/>}
    <div className="toolbar"><Select aria-label="应用所属企业" placeholder="选择企业" style={{minWidth:240}} value={tenant} disabled={busy} options={tenants.map(t=>({value:t.id,label:t.name}))} onChange={id=>run(async()=>{
      setTenant(id); setSelected(undefined); setApps([]); setVersions([]); setEvents([]); if(tenant) appForm.resetFields(); if(selected) versionForm.resetFields(); await list(id);
    })}/><Button disabled={busy || !tenant} onClick={()=>run(async()=>{await list(tenant!); if(selected) await details(selected);})}>刷新应用</Button></div>
    {tenant && <><Form form={appForm} layout="inline" onFinish={values=>run(async()=>{
      await client.request(root(tenant),'POST',values); appForm.resetFields(); await list(tenant);
    })}>
      <Form.Item name="slug" label="应用标识" rules={[{required:true,pattern:/^[a-z0-9][a-z0-9_-]{0,63}$/}]}><Input disabled={busy} placeholder="例如 erp"/></Form.Item>
      <Form.Item name="name" label="应用名称" rules={[{required:true,whitespace:true,max:120}]}><Input disabled={busy}/></Form.Item>
      <Form.Item name="description" label="说明" initialValue="" rules={[{max:2000}]}><Input disabled={busy}/></Form.Item>
      <Button htmlType="submit" disabled={busy}>创建应用</Button>
    </Form><Table rowKey="id" dataSource={apps} pagination={{pageSize:10}} columns={[
      {title:'名称',dataIndex:'name'}, {title:'标识',dataIndex:'slug'}, {title:'状态',render:(_,app)=>app.enabled?'启用':'停用'},
      {title:'操作',render:(_,app)=><Space><Button disabled={busy} onClick={()=>run(()=>details(app))}>管理版本</Button><Button disabled={busy} onClick={()=>setChange({app})}>{app.enabled?'停用应用':'启用应用'}</Button></Space>},
    ]}/></>}
    {selected && <><h3>{selected.name} · 产品版本</h3><Form form={versionForm} layout="inline" onFinish={values=>run(async()=>{
      await client.request(`${root(selected.tenant_id)}/${selected.id}/versions`,'POST',values); await details(selected);
    })}>
      <Form.Item name="version" label="版本号" rules={[{required:true,pattern:/^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,63}$/}]}><Input disabled={busy} placeholder="例如 1.0.0"/></Form.Item>
      <Form.Item name="notes" label="版本说明" initialValue="" rules={[{max:4000}]}><Input disabled={busy}/></Form.Item>
      <Button htmlType="submit" disabled={busy}>创建版本草稿</Button>
    </Form><Table rowKey="id" dataSource={versions} pagination={{pageSize:10}} columns={[
      {title:'版本',dataIndex:'version'},{title:'状态',dataIndex:'status',render:(status:Version['status'])=>labels[status]}, {title:'说明',dataIndex:'notes'},
      {title:'操作',render:(_,version)=><Space><Button disabled={busy} onClick={()=>setDocumentVersion(version)}>管理知识库</Button>{version.status!=='retired' && <Button disabled={busy} onClick={()=>setChange({app:selected,version})}>{version.status==='draft'?'发布版本':'退役版本'}</Button>}</Space>},
    ]}/><details><summary>最近 100 条应用操作记录</summary><Table rowKey="id" dataSource={events} pagination={{pageSize:10}} columns={[
      {title:'事件',dataIndex:'action'},{title:'操作人',dataIndex:'actor'},{title:'请求 ID',dataIndex:'request_id'},{title:'时间',dataIndex:'created_at',render:t=>new Date(t*1000).toLocaleString()},
    ]}/></details></>}
    {selected && documentVersion && <KnowledgePanel key={`${selected.id}:${documentVersion.id}`} client={client} root={`${root(selected.tenant_id)}/${selected.id}/versions/${documentVersion.id}/documents`} title={`${selected.name} ${documentVersion.version}`} versionStatus={documentVersion.status} enabled={selected.enabled && !!tenants.find(t=>t.id===selected.tenant_id)?.enabled}/>}
    {change && <Modal open title="确认应用版本变更" confirmLoading={busy} onCancel={()=>setChange(undefined)} onOk={()=>run(async()=>{
      const base = `${root(change.app.tenant_id)}/${change.app.id}`;
      let updated = change.app;
      if(change.version) await client.request(`${base}/versions/${change.version.id}`,'PATCH',{status:change.version.status==='draft'?'published':'retired'});
      else updated = await client.request<Application>(base,'PATCH',{enabled:!change.app.enabled});
      setChange(undefined); await list(change.app.tenant_id); if(selected?.id===change.app.id) await details(updated);
    })}><p>{change.app.name} {change.version?.version}</p><p>{change.version ? '仅已发布版本对企业成员可见。退役后不可重新发布，请创建新版本。此操作不解析或发布任何知识库文件。' : '停用应用后，企业成员无法读取其版本。'}</p></Modal>}
  </section>;
}
