import {useEffect, useRef, useState} from 'react';
import {Alert, Button} from 'antd';
import {AdminClient} from '../../shared/client';
import type {Chunk} from './types';
interface Answer {answer: string; status: string; citations: (Chunk & {citation_id: string; filename: string})[]}
export function AnswerPanel({client, root, model, chatModels}: {
  client: AdminClient; root: string; model: string; chatModels: {alias: string; deployment: string}[];
}) {
  const [chat, setChat] = useState('');
  const [query, setQuery] = useState('');
  const [result, setResult] = useState<Answer>();
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const pending = useRef<AbortController | null>(null);
  useEffect(() => () => pending.current?.abort(), [client, root, model]);
  return <section aria-label="引用问答"><h4>引用问答</h4>
    <p>问题发送到 embedding 模型，问题和检索原文发送到聊天模型；云端调用可能产生费用。回答须结合引用核对，引用编号校验不代表事实正确性。</p>
    {!chatModels.length && <p>请先授权一个聊天模型。</p>}
    <form onSubmit={async event => {
      event.preventDefault(); if (!chat || !query.trim() || pending.current) return;
      const controller = new AbortController(); pending.current = controller;
      setBusy(true); setResult(undefined); setError('');
      try {
        const answer = await client.request<Answer>(`${root}/answers`, 'POST', {model, chat_model:chat, query, limit:5}, controller.signal);
        if (!controller.signal.aborted) setResult(answer);
      } catch (e) {if (!controller.signal.aborted) setError((e as Error).message);}
      finally {if (!controller.signal.aborted) {pending.current = null; setBusy(false);}}
    }}>
      <label>聊天模型 <select aria-label="聊天模型" value={chat} disabled={busy} onChange={e => {setChat(e.target.value); setResult(undefined);}}>
        <option value="">请选择聊天模型</option>{chatModels.map(item => <option key={item.alias} value={item.alias}>{item.alias} · {item.deployment === 'local' ? '本地' : '云端'}</option>)}
      </select></label>
      <label>提问 <input aria-label="提问" value={query} disabled={busy} maxLength={200} required onChange={e => {setQuery(e.target.value); setResult(undefined);}}/></label>
      <Button htmlType="submit" loading={busy} disabled={!chat || !query.trim()}>生成引用回答</Button>
    </form>
    {error && <Alert type="error" message={error}/>}
    {result && <><pre className="knowledge-text">{result.answer}</pre>{result.citations.map(source => <article key={source.citation_id}>
      <h5>[{source.citation_id}] {source.filename} · 分片 {source.chunk_index + 1}</h5>
      <p>{source.source_kind === 'page' ? '页码' : source.source_kind === 'paragraph' ? '段落' : '文档'} {source.source_index} · 字符 {source.start}–{source.end}</p>
      <pre className="knowledge-text">{source.text}</pre>
    </article>)}</>}
  </section>;
}
