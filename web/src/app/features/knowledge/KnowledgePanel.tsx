import {useEffect, useRef, useState} from 'react';
import {Alert, Button, Modal, Space, Table, Tag} from 'antd';
import {AdminClient} from '../../shared/client';
import {errorLabels, statusLabels} from './types';
import type {Chunk, KnowledgeDocument} from './types';
import {SearchPanel} from './SearchPanel';
import {VectorPanel} from './VectorPanel';

const pageSize = 20;
interface Props {
  client: AdminClient;
  root: string;
  title: string;
  versionStatus: 'draft' | 'published' | 'retired';
  enabled: boolean;
}

// Parent keys this component by version: changing scope unmounts all private state.
export function KnowledgePanel({client, root, title, versionStatus, enabled}: Props) {
  const [documents, setDocuments] = useState<KnowledgeDocument[]>([]);
  const [vectors, setVectors] = useState(false);
  const [offset, setOffset] = useState(0);
  const [file, setFile] = useState<File>();
  const input = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const lock = useRef(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [selected, setSelected] = useState<KnowledgeDocument>();
  const [chunks, setChunks] = useState<Chunk[]>([]);
  const [chunkOffset, setChunkOffset] = useState(0);
  const [change, setChange] = useState<KnowledgeDocument>();
  const lifetime = useRef<AbortController | null>(null);

  async function load(start: number, signal: AbortSignal) {
    const result = await client.request<{data: KnowledgeDocument[]}>(`${root}?offset=${start}&limit=${pageSize}`, 'GET', undefined, signal);
    if (!signal.aborted) {setDocuments(result.data); setOffset(start);}
  }
  async function run(work: (signal: AbortSignal) => Promise<void>) {
    const signal = lifetime.current?.signal;
    if (lock.current || !signal || signal.aborted) return;
    lock.current = true; setBusy(true); setError(''); setNotice('');
    try {await work(signal);}
    catch (e) {if (!signal.aborted && (e as Error).name !== 'AbortError') setError((e as Error).message);}
    finally {if (!signal.aborted) {lock.current = false; setBusy(false);}}
  }
  useEffect(() => {
    const controller = new AbortController();
    lifetime.current = controller; lock.current = false;
    void run(signal => load(0, signal));
    return () => controller.abort();
  }, [client, root]);

  async function preview(document: KnowledgeDocument, start: number, signal: AbortSignal) {
    const result = await client.request<{data: Chunk[]}>(`${root}/${document.id}/chunks?offset=${start}&limit=${pageSize}`, 'GET', undefined, signal);
    if (!signal.aborted) {setSelected(document); setChunks(result.data); setChunkOffset(start);}
  }
  const uploadAllowed = enabled && versionStatus === 'draft';
  return <section aria-label="知识库管理"><h3>{title} · 知识库</h3>
    <Button disabled={!enabled || versionStatus !== 'published'} onClick={() => setVectors(value => !value)}>{vectors ? '关闭向量管理' : '向量索引与检索'}</Button>
    {vectors && enabled && versionStatus === 'published' && <VectorPanel key={`${root}:${documents.map(doc => `${doc.id}:${doc.published}`).join(',')}`} client={client} root={root.replace(/\/documents$/, '')}/>}
    <SearchPanel key={`${enabled}:${documents.map(doc => `${doc.id}:${doc.published}`).join(',')}`} client={client} root={root.replace(/\/documents$/, '/search')} enabled={enabled && versionStatus === 'published'}/>
    <p>上传 PDF、DOCX、Markdown 或 TXT，单文件不超过 10 MiB。扫描件暂不支持 OCR。解析完成后，需先发布产品版本，再单独发布文档。</p>
    {!uploadAllowed && <Alert type="info" message="仅启用企业和应用的草稿版本允许上传新文件；修订手册请创建新版本。"/>}
    {error && <Alert type="error" showIcon message={error}/>}
    {notice && <Alert type="success" message={notice}/>}
    <div className="toolbar">
      <label>选择手册 <input ref={input} aria-label="选择手册" type="file" accept=".pdf,.docx,.md,.txt" disabled={busy || !uploadAllowed} onChange={event => {
        const value = event.target.files?.[0]; setFile(undefined); setError(''); setNotice('');
        if (!value) return;
        if (!/\.(pdf|docx|md|txt)$/i.test(value.name) || value.size === 0 || value.size > 10 * 1024 * 1024) {
          setError('请选择非空 PDF、DOCX、Markdown 或 TXT 文件，大小不超过 10 MiB。'); event.target.value = ''; return;
        }
        if (value.name.length > 240 || /[\u0000-\u001f/\\:]/.test(value.name)) {
          setError('文件名不能包含路径或控制字符，且不得超过 240 个字符。'); event.target.value = ''; return;
        }
        setFile(value);
      }}/></label>
      <Button type="primary" disabled={busy || !file || !uploadAllowed} onClick={() => void run(async signal => {
        const uploaded = await client.upload<KnowledgeDocument>(root, file!, signal);
        if (signal.aborted) return;
        setFile(undefined); if (input.current) input.current.value = '';
        setNotice(`${uploaded.filename}：${statusLabels[uploaded.status]}。重复上传会返回已有文档。`);
        await load(0, signal);
      })}>上传手册</Button>
      <Button disabled={busy} onClick={() => void run(signal => load(offset, signal))}>刷新处理状态</Button>
      <span aria-live="polite">{busy ? '正在请求…' : '状态按需刷新；等待处理时请确认 Worker 已启动。'}</span>
    </div>
    <Table<KnowledgeDocument> rowKey="id" dataSource={documents} loading={busy} pagination={false} scroll={{x: 700}} columns={[
      {title: '文件', dataIndex: 'filename'},
      {title: '处理状态', render: (_, doc) => <Tag>{statusLabels[doc.status]}</Tag>},
      {title: '发布状态', render: (_, doc) => doc.published ? '已发布' : '未发布'},
      {title: '解析提示', render: (_, doc) => <>{doc.error && <p>{errorLabels[doc.error] || doc.error}</p>}{doc.warnings.length > 0 && <details><summary>{doc.warnings.length} 条解析提示</summary>{doc.warnings.map(warning => <p key={warning}>{warning.startsWith('page_without_text:') ? `第 ${warning.split(':')[1]} 页未提取文本，请检查原文件。` : warning}</p>)}</details>}</>},
      {title: '操作', render: (_, doc) => <Space wrap>
        <Button disabled={busy || doc.status !== 'ready'} onClick={() => void run(signal => preview(doc, 0, signal))}>查看分片</Button>
        {doc.status === 'failed' && <Button disabled={busy || !enabled || versionStatus === 'retired'} onClick={() => void run(async signal => {
          await client.request(`${root}/${doc.id}/retry`, 'POST', undefined, signal); if (!signal.aborted) await load(offset, signal);
        })}>重试解析</Button>}
        <Button disabled={busy || (!doc.published && (!enabled || versionStatus !== 'published' || doc.status !== 'ready'))} onClick={() => setChange(doc)}>{doc.published ? '撤回文档' : '发布文档'}</Button>
      </Space>},
    ]}/>
    <Space><Button disabled={busy || offset === 0} onClick={() => void run(signal => load(offset - pageSize, signal))}>上一页文档</Button><span>第 {offset / pageSize + 1} 页</span><Button disabled={busy || documents.length < pageSize} onClick={() => void run(signal => load(offset + pageSize, signal))}>下一页文档</Button></Space>
    {selected && <Modal open title={`${selected.filename} · 来源分片`} width={850} footer={null} onCancel={() => {if (!busy) {setSelected(undefined); setChunks([]);}}} closable={!busy} maskClosable={!busy}>
      {error && <Alert type="error" message={error}/>}
      <p>以下为提取原文；页码/段落从 1 开始，字符范围右端不包含。请检查无文本页及内容完整性。</p>
      {chunks.map(chunk => <article key={chunk.chunk_index}><h4>分片 {chunk.chunk_index + 1} · {chunk.source_kind === 'page' ? '页码' : chunk.source_kind === 'paragraph' ? '段落' : '文档'} {chunk.source_index} · 字符 {chunk.start}–{chunk.end}</h4><pre className="knowledge-text">{chunk.text}</pre></article>)}
      {!chunks.length && <p>本页没有分片。</p>}
      <Space><Button disabled={busy || chunkOffset === 0} onClick={() => void run(signal => preview(selected, chunkOffset - pageSize, signal))}>上一页分片</Button><span>第 {chunkOffset / pageSize + 1} 页</span><Button disabled={busy || chunks.length < pageSize} onClick={() => void run(signal => preview(selected, chunkOffset + pageSize, signal))}>下一页分片</Button></Space>
    </Modal>}
    {change && <Modal open title={change.published ? '确认撤回文档' : '确认发布文档'} okText="确认" cancelText="取消" confirmLoading={busy} cancelButtonProps={{disabled: busy}} closable={!busy} maskClosable={!busy} onCancel={() => setChange(undefined)} onOk={() => void run(async signal => {
      await client.request(`${root}/${change.id}`, 'PATCH', {published: !change.published}, signal);
      if (!signal.aborted) {setChange(undefined); await load(offset, signal);}
    })}>{error && <Alert type="error" message={error}/>}<p>{change.filename}</p><p>{change.published ? '撤回后，企业用户将无法读取此文档。' : '发布后，本企业用户可读取此文档。请先预览分片并确认解析提示。'}</p></Modal>}
  </section>;
}
