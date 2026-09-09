export class AdminClient {
  private generation = 0;
  private token = '';
  private pending = new Set<AbortController>();
  connect(token: string) { this.disconnect(); this.token = token; }
  disconnect() {
    this.generation++;
    this.token = '';
    this.pending.forEach(controller => controller.abort());
    this.pending.clear();
  }
  async request<T>(path: string, method = 'GET', body?: unknown): Promise<T> {
    const generation = this.generation;
    const controller = new AbortController();
    this.pending.add(controller);
    try {
      const response = await fetch(`/api/v1/admin${path}`, {
        method, signal: controller.signal,
        headers: { Authorization: `Bearer ${this.token}`, 'Content-Type': 'application/json' },
        body: body === undefined ? undefined : JSON.stringify(body),
      });
      const data = response.status === 204 ? undefined : await response.json();
      if (generation !== this.generation) throw new DOMException('连接已结束', 'AbortError');
      if (!response.ok) throw new Error(`${data?.error?.message || '请求失败'}（${response.status}），请求 ID：${data?.request_id || '—'}`);
      return data as T;
    } finally { this.pending.delete(controller); }
  }
}
