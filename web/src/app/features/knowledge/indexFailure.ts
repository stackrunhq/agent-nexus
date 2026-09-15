/** Public error codes only; never interpret provider exception bodies as advice. */
const advice: Record<string, [string, string]> = {
  model_daily_quota_exceeded: ['模型日额度耗尽', '查看企业模型调用额度，等待 UTC 次日重置或由管理员调整额度后重新提交。'],
  provider_rate_limited: ['模型服务限流', '降低并发并查看模型服务限流规则，等待恢复后重新提交。'],
  credential_missing: ['模型凭据未配置', '请管理员在 Worker 运行环境中配置模型所引用的凭据变量并重启；不要在页面提交密钥。'],
  endpoint_not_allowed: ['模型地址未获准', '请管理员核对模型地址与部署允许访问的主机配置。'],
  unsupported_capability: ['模型不支持向量', '选择已启用 embeddings 能力且已授权的模型。'],
  embedding_dimensions_changed: ['向量维度发生变化', '检查模型服务是否切换模型或维度，保持各批次配置一致后重新提交。'],
  invalid_provider_response: ['模型响应格式无效', '检查服务接口协议和模型适配配置，使用模型试调用验证响应。'],
  provider_response_too_large: ['模型响应过大', '检查模型返回内容和向量维度，响应上限为 8 MiB。'],
  index_build_timeout: ['索引构建超时', '构建超过 120 秒；检查模型性能和分片数量，调整后重新提交。'],
  provider_timeout: ['模型请求超时', '检查模型服务负载和超时配置，恢复后重新提交。'],
  provider_unreachable: ['模型服务不可达', '检查 Worker 到模型地址的网络、端口及服务状态。'],
  provider_error: ['模型服务拒绝请求', '检查模型服务日志、凭据和请求限制，修复配置后重新提交。'],
  model_not_allowed: ['模型未授权', '在企业模型授权中授予该 embedding 模型后重新提交。'],
  model_not_found: ['模型不可用', '检查模型别名是否存在且已启用，必要时选择其他模型。'],
  index_stale: ['构建期间内容或模型变化', '等待手册发布和模型配置稳定后重新提交。'],
  index_capacity: ['索引容量不符合限制', '检查已发布内容是否为 1–128 个分片，索引数据是否超过 16 MiB；调整内容后重新提交。'],
  invalid_index_vector: ['向量数据无效', '检查 embedding 模型的维度、返回数量及数值是否有效。'],
  index_checkpoint_invalid: ['检查点无效', '确认内容和模型配置稳定后重新提交；再次失败时联系管理员检查存储。'],
  worker_interrupted: ['Worker 多次中断', '检查 Worker 重启记录、数据库连接及资源限制，稳定后重新提交。'],
  index_worker_failed: ['Worker 执行失败', '联系管理员结合任务编号检查 Worker 日志及数据库连接，定位原因后重新提交。'],
};

export function indexFailure(code: string | null) {
  const entry = code && Object.prototype.hasOwnProperty.call(advice, code) ? advice[code] : undefined;
  const [reason, suggestion] = entry ?? ['其他失败原因', '联系管理员结合任务编号和错误码排查，确认原因后重新提交。'];
  return {reason, suggestion};
}
