export class AdminClient {
  private generation = 0;
  private token = '';
  private pending = new Set<AbortController>();
  private expiryTimer?: ReturnType<typeof setTimeout>;
  onExpired?: () => void;
  connect(token: string) { this.disconnect(); this.token = token; }
  disconnect() {
    clearTimeout(this.expiryTimer);
    this.expiryTimer = undefined;
    this.generation++;
    this.token = '';
    this.pending.forEach(controller => controller.abort());
    this.pending.clear();
  }
  async login(username: string, password: string) {
    this.disconnect();
    const result = await this.request<{access_token: string; expires_in?: number; user: {role: string}}>('/auth/login', 'POST', {username, password});
    this.connect(result.access_token);
    if (result.user.role !== 'platform_admin') {
      await this.logout();
      throw new Error('该账号是企业成员，不能进入平台管理后台。');
    }
    if (result.expires_in) this.expiryTimer = setTimeout(() => {
      this.disconnect(); this.onExpired?.();
    }, result.expires_in * 1000);
  }
  async logout() {
    const token = this.token;
    this.disconnect();
    if (!token.startsWith('ns_')) return;
    const response = await fetch('/api/v1/auth/logout', {
      method: 'POST', headers: {Authorization: `Bearer ${token}`}, signal: AbortSignal.timeout(10000),
    });
    if (!response.ok && response.status !== 401) throw new Error('本地已断开，服务端退出未确认；会话将在到期后失效。');
  }
  async request<T>(path: string, method = 'GET', body?: unknown): Promise<T> {
    const generation = this.generation;
    const controller = new AbortController();
    this.pending.add(controller);
    try {
      const response = await fetch(`/api/v1${path.startsWith('/auth/') ? '' : '/admin'}${path}`, {
        method, signal: controller.signal,
        headers: { Authorization: `Bearer ${this.token}`, 'Content-Type': 'application/json' },
        body: body === undefined ? undefined : JSON.stringify(body),
      });
      const data = response.status === 204 ? undefined : await response.json();
      if (generation !== this.generation) throw new DOMException('连接已结束', 'AbortError');
      if (response.status === 401 && this.token.startsWith('ns_')) {
        this.disconnect(); this.onExpired?.();
      }
      if (!response.ok) throw new Error(`${data?.error?.message || '请求失败'}（${response.status}），请求 ID：${data?.request_id || '—'}`);
      return data as T;
    } finally { this.pending.delete(controller); }
  }
}
