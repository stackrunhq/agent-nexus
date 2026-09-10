import {useEffect, useRef, useState} from 'react';
import {Alert, Button, Form, Input} from 'antd';
import {AdminClient} from '../../shared/client';
import type {Chunk} from './types';

interface Hit extends Chunk {document_id: string; filename: string; score: number; matched_terms: string[]}
export function SearchPanel({client, root, enabled, model, hybrid}: {client: AdminClient; root: string; enabled: boolean; model?: string; hybrid?: boolean}) {
  const [results, setResults] = useState<Hit[]>([]);
  const [searched, setSearched] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const pending = useRef<AbortController | null>(null);
  useEffect(() => () => pending.current?.abort(), [root, client]);
  return <div><h4>{hybrid ? '混合检索试用' : model ? '向量检索试用' : '检索已发布手册'}</h4><p>{model ? '问题将发送到所选模型。检索排序不代表答案正确性。' : '按关键词查找原文，支持中文、英文和数字。只搜索已发布文档，不生成大模型回答。'}</p>
    {error && <Alert type="error" message={error}/>}
    <Form name={hybrid ? 'hybrid-search' : model ? 'vector-search' : 'keyword-search'} layout="inline" onFinish={async ({query}) => {
      if (pending.current || !enabled) return;
      const controller = new AbortController(); pending.current = controller;
      setBusy(true); setError(''); setResults([]); setSearched(false);
      try {
        const result = await client.request<{data: Hit[]}>(root, 'POST', {query, limit:5, ...(model ? {model} : {})}, controller.signal);
        if (!controller.signal.aborted) {setResults(result.data); setSearched(true);}
      } catch(e) {if (!controller.signal.aborted && (e as Error).name !== 'AbortError') setError((e as Error).message);}
      finally {if (!controller.signal.aborted) {pending.current = null; setBusy(false);}}
    }}>
      <Form.Item name="query" label="手册关键词" rules={[{required:true, whitespace:true, max:200}]}><Input maxLength={200} disabled={busy || !enabled} placeholder="例如：重置密码"/></Form.Item>
      <Button htmlType="submit" disabled={!enabled} loading={busy}>检索手册</Button>
    </Form>
    {!enabled && <p>请先启用企业/应用并发布产品版本，随后发布需要检索的文档。</p>}
    {searched && !results.length && <p>未找到匹配内容。请更换关键词，或确认文档已发布。</p>}
    {results.map(hit => <article key={`${hit.document_id}:${hit.chunk_index}`}><h4>{hit.filename} · 分片 {hit.chunk_index + 1}</h4><p>{hit.source_kind === 'page' ? '页码' : hit.source_kind === 'paragraph' ? '段落' : '文档'} {hit.source_index} · 字符 {hit.start}–{hit.end}</p><pre className="knowledge-text">{hit.text}</pre></article>)}
  </div>;
}
