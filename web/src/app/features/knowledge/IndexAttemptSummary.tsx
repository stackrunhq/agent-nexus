export interface AttemptSummary {
  scope:string;unconfirmed_request_calls:number;
  attempts:Array<{attempt:number|null;calls:number;succeeded:number;failed:number;pending:number;known_input_tokens:number|null;known_output_tokens:number|null;known_elapsed_ms:number|null;unknown_input_tokens_calls:number;unknown_output_tokens_calls:number;unknown_elapsed_ms_calls:number}>;
}
export function IndexAttemptSummary({value,onSelect}:{value:AttemptSummary;onSelect?:(attempt:number|null,status:string)=>void}) {
  return <section aria-label="按尝试汇总调用"><h5>按尝试汇总调用</h5>
    <p>覆盖本任务全部精确关联调用，不受分页影响。已知用量不是完整费用；累计调用耗时不是任务总时长。</p>
    <p>另有 {value.unconfirmed_request_calls} 次未确认归属的请求匹配，未计入以下汇总。</p>
    {!value.attempts.length && <p>暂无精确关联调用，不能据此认定未调用模型或未产生费用。</p>}
    {value.attempts.map(row=><article key={row.attempt ?? 'unknown'}>
      <h6>{row.attempt === null ? '尝试次数未知' : `第 ${row.attempt} 次尝试`}</h6>
      {onSelect && <><button onClick={()=>onSelect(row.attempt,'')}>查看本次调用</button><button disabled={!row.failed} onClick={()=>onSelect(row.attempt,'failed')}>查看本次失败调用</button></>}
      <p>调用 {row.calls} · 成功 {row.succeeded} · 失败 {row.failed} · 待确认 {row.pending}</p>
      <p>已知输入 token：{row.known_input_tokens ?? '未知'}（{row.unknown_input_tokens_calls} 次未返回）；已知输出 token：{row.known_output_tokens ?? '未知'}（{row.unknown_output_tokens_calls} 次未返回）</p>
      <p>已知累计调用耗时：{row.known_elapsed_ms === null ? '未知' : `${row.known_elapsed_ms} ms`}（{row.unknown_elapsed_ms_calls} 次未知）</p>
    </article>)}
  </section>;
}
