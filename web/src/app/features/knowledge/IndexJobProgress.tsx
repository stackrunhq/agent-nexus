export interface IndexJob {
  id: string; model: string; status: string; attempts: number; error: string | null;
  saved_batches?: number;
  recovery_state?: 'inactive' | 'running' | 'retrying' | 'waiting_for_worker';
}

export function IndexJobProgress({task}: {task: IndexJob}) {
  const status = ({queued:'排队中', processing:'构建中', succeeded:'构建成功', failed:'构建失败'} as Record<string,string>)[task.status] || task.status;
  return <div aria-label={`索引任务 ${task.id}`}>
    <p>任务 {task.id}：{status} · 已尝试 {task.attempts} 次{task.error ? ` · ${task.error}` : ''}</p>
    {task.status === 'processing' && <>
      <p>已保存 {task.saved_batches ?? 0} 批检查点（每批最多 16 个分片）。</p>
      {task.recovery_state === 'waiting_for_worker' && <p>租约已到期，等待 Worker 重新领取；达到尝试上限后将终止。</p>}
      {task.recovery_state === 'retrying' && <p>Worker 已重新领取，正在处理；检查点校验通过后可复用，内容或模型变化时重新构建。</p>}
      <p>检查点数量不是完成百分比；索引仍需最终校验和保存。</p>
    </>}
    {task.status === 'succeeded' && <p>索引已提交，临时检查点已清理。</p>}
    {task.status === 'failed' && <p>任务已终止；可重新提交，旧索引保留。</p>}
  </div>;
}
