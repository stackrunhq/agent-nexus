export interface Scheduling {
  api_strategy: 'fifo' | 'tenant_round_robin'; observed_at: number;
  queued: number; processing: number; recovery_pending: number;
  oldest_queued_age_seconds: number | null; oldest_recovery_overdue_seconds: number | null;
}
export function SchedulerStatus({value}: {value: Scheduling}) {
  return <section aria-label="企业索引调度状态">
    <p>API 配置的调度策略：{value.api_strategy === 'tenant_round_robin' ? '租户轮转' : 'FIFO'}</p>
    <p>本企业排队 {value.queued} 项 · 处理中 {value.processing} 项 · 其中等待重新领取 {value.recovery_pending} 项</p>
    <p>最早排队任务已等待：{value.oldest_queued_age_seconds === null ? '无排队任务' : `${value.oldest_queued_age_seconds} 秒`}</p>
    <p>最早过期租约已超时：{value.oldest_recovery_overdue_seconds === null ? '无过期租约' : `${value.oldest_recovery_overdue_seconds} 秒`}</p>
    <p>统计时间：{new Date(value.observed_at * 1000).toLocaleString()}。覆盖本企业全部应用和模型，按需刷新。</p>
    <p>此配置来自 API，尚未核验各 Worker 的实际配置。当前等待不是历史平均值，也不是预计完成时间。</p>
  </section>;
}
