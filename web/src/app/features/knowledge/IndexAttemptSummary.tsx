import {indexFailure} from './indexFailure';
export interface AttemptSummary {
  failure_reasons?:Array<{attempt:number|null;error:string|null;calls:number}>;
  scope:string;unconfirmed_request_calls:number;
  attempts:Array<{attempt:number|null;calls:number;succeeded:number;failed:number;pending:number;known_input_tokens:number|null;known_output_tokens:number|null;known_elapsed_ms:number|null;unknown_input_tokens_calls:number;unknown_output_tokens_calls:number;unknown_elapsed_ms_calls:number}>;
}
export function IndexAttemptSummary({value,onSelect,onError}:{value:AttemptSummary;onSelect?:(attempt:number|null,status:string)=>void;onError?:(attempt:number|null,error:string|null)=>void}) {
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
    {value.failure_reasons && <section aria-label="调用失败原因统计"><h6>调用失败原因（全任务精确关联）</h6>
      {!value.failure_reasons.length && <p>暂无精确关联的失败调用。</p>}
      {value.failure_reasons.map(row=><article key={JSON.stringify([row.attempt,row.error])}>
        <p>{row.attempt===null?'尝试未知':`第 ${row.attempt} 次尝试`} · {row.error ?? '缺失错误码'} · {row.calls} 次</p>
        <p>{indexFailure(row.error).reason}：{indexFailure(row.error).suggestion}</p>
        {onError && <button onClick={()=>onError(row.attempt,row.error)}>查看此类失败</button>}
      </article>)}
    </section>}
  </section>;
}
