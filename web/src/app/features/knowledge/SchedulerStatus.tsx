export interface Scheduling {
  api_strategy: 'fifo' | 'tenant_round_robin'; observed_at: number;
  queued: number; processing: number; recovery_pending: number;
  oldest_queued_age_seconds: number | null; oldest_recovery_overdue_seconds: number | null;
  workers?: {recent: number; stale: number; mismatched: number; ttl_seconds: number; status: 'unknown' | 'mismatch' | 'matching'};
}
export function SchedulerStatus({value}: {value: Scheduling}) {
  return <section aria-label="企业索引调度状态">
    <p>API 配置的调度策略：{value.api_strategy === 'tenant_round_robin' ? '租户轮转' : 'FIFO'}</p>
    <p>本企业排队 {value.queued} 项 · 处理中 {value.processing} 项 · 其中等待重新领取 {value.recovery_pending} 项</p>
    <p>最早排队任务已等待：{value.oldest_queued_age_seconds === null ? '无排队任务' : `${value.oldest_queued_age_seconds} 秒`}</p>
    <p>最早过期租约已超时：{value.oldest_recovery_overdue_seconds === null ? '无过期租约' : `${value.oldest_recovery_overdue_seconds} 秒`}</p>
    <p>统计时间：{new Date(value.observed_at * 1000).toLocaleString()}。覆盖本企业全部应用和模型，按需刷新。</p>
    {value.workers ? <>
      <p>共享索引 Worker：近期心跳 {value.workers.recent} 个 · 过期观测 {value.workers.stale} 个 · 策略不一致 {value.workers.mismatched} 个</p>
      <p>{value.workers.status === 'unknown' ? '未观测到近期 Worker 心跳，请检查进程与数据库连接。' : value.workers.status === 'mismatch' ? '检测到 Worker 与当前 API 调度策略不一致，请统一配置后重启。' : '近期上报的 Worker 策略与当前 API 一致。'}</p>
      <p>心跳有效期 {value.workers.ttl_seconds} 秒，覆盖共享数据库中的索引 Worker；不保证所有进程均已接入，也不代表任务一定能成功。</p>
    </> : <p>此配置来自 API，尚未核验各 Worker 的实际配置。</p>}
    <p>当前等待不是历史平均值，也不是预计完成时间。</p>
  </section>;
}
