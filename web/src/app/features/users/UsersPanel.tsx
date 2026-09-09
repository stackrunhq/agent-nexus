import { useRef, useState } from 'react';
import { Alert, Button, Form, Input, Modal, Select, Space, Table } from 'antd';
import { AdminClient } from '../../shared/client';
import type { Tenant } from '../tenants/types';

interface User { id: string; username: string; role: string; tenant_id: string | null; enabled: boolean }
interface UserEvent { id: number; actor: string; user_id: string; action: string; created_at: number }

export function UsersPanel({client, tenants}: {client: AdminClient; tenants: Tenant[]}) {
  const [users, setUsers] = useState<User[]>([]);
  const [events, setEvents] = useState<UserEvent[]>([]);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const locked = useRef(false);
  const [role, setRole] = useState('tenant_user');
  const [form] = Form.useForm();
  const [target, setTarget] = useState<{user: User; reset: boolean}>();
  const [password, setPassword] = useState('');
  async function load() {
    const [list, audit] = await Promise.all([client.request<{data: User[]}>('/users'), client.request<{data: UserEvent[]}>('/user-events')]);
    setUsers(list.data); setEvents(audit.data);
  }
  async function run(work: () => Promise<void>) {
    if (locked.current) return;
    locked.current = true; setBusy(true); setError('');
    try {await work();} catch(e) {if ((e as Error).name !== 'AbortError') setError((e as Error).message);}
    finally {locked.current = false; setBusy(false);}
  }
  return <section><h2>个人账号与角色</h2><p>平台管理员可管理所有企业；企业成员只可调用所属企业已授权模型。账号角色和所属企业创建后暂不支持修改。</p>
    {error && <Alert type="error" message={error}/>}
    <Form form={form} layout="vertical" onFinish={values => run(async () => {
      await client.request('/users', 'POST', {...values, role, tenant_id: role === 'tenant_user' ? values.tenant_id : null});
      form.resetFields(); await load();
    })}>
      <Space wrap align="start">
        <Form.Item name="username" label="新用户名" rules={[{required: true, pattern: /^[a-z0-9][a-z0-9_.-]{2,63}$/}]}><Input disabled={busy} autoComplete="off"/></Form.Item>
        <Form.Item name="password" label="初始密码（至少 15 字符）" rules={[{required: true, min: 15, max: 256}]}><Input.Password disabled={busy} autoComplete="new-password"/></Form.Item>
        <Form.Item label="角色"><Select value={role} disabled={busy} onChange={setRole} options={[{value: 'tenant_user', label: '企业成员'}, {value: 'platform_admin', label: '平台管理员'}]}/></Form.Item>
        {role === 'tenant_user' && <Form.Item name="tenant_id" label="所属企业" rules={[{required: true}]}><Select style={{minWidth: 180}} disabled={busy} options={tenants.filter(t=>t.enabled).map(t=>({value:t.id,label:t.name}))}/></Form.Item>}
      </Space><Space><Button htmlType="submit" disabled={busy}>创建账号</Button><Button disabled={busy} onClick={()=>run(load)}>刷新账号与记录</Button></Space>
    </Form>
    <Table rowKey="id" dataSource={users} pagination={{pageSize: 10}} scroll={{x: 650}} columns={[
      {title:'用户名',dataIndex:'username'}, {title:'角色',dataIndex:'role'}, {title:'企业 ID',dataIndex:'tenant_id'},
      {title:'状态',render:(_,u)=><span>{u.enabled?'启用':'停用'}</span>},
      {title:'操作',render:(_,u)=><Space><Button disabled={busy} onClick={()=>setTarget({user:u,reset:false})}>{u.enabled?'停用账号':'启用账号'}</Button><Button disabled={busy} onClick={()=>{setPassword('');setTarget({user:u,reset:true});}}>重置密码</Button></Space>},
    ]}/>
    <details><summary>最近 100 条账号安全事件</summary><Table rowKey="id" dataSource={events} pagination={{pageSize:10}} columns={[
      {title:'事件',dataIndex:'action'},{title:'账号 ID',dataIndex:'user_id'},{title:'操作人 ID',dataIndex:'actor'},{title:'时间',dataIndex:'created_at',render:t=>new Date(t*1000).toLocaleString()},
    ]}/></details>
    {target && <Modal open title={target.reset?'重置密码':'修改账号状态'} confirmLoading={busy} okButtonProps={{disabled: target.reset && (password.length < 15 || password.length > 256)}} onCancel={()=>{setTarget(undefined);setPassword('');}} onOk={()=>run(async()=>{
      if(target.reset) await client.request(`/users/${target.user.id}/reset-password`,'POST',{password});
      else await client.request(`/users/${target.user.id}`,'PATCH',{enabled:!target.user.enabled});
      setTarget(undefined);setPassword('');await load();
    })}><p>{target.user.username}：此操作会立即撤销该账号全部会话，包括当前会话（若修改的是自己）。</p>{target.reset && <Input.Password aria-label="重置后的密码" autoComplete="new-password" value={password} onChange={e=>setPassword(e.target.value)}/>}</Modal>}
  </section>;
}
