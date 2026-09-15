// @vitest-environment jsdom
import {cleanup, render, screen} from '@testing-library/react';
import {afterEach, expect, test} from 'vitest';
import {SchedulerStatus, type Scheduling} from './SchedulerStatus';
afterEach(cleanup);
test('distinguishes unknown, matching and mismatched worker observations', () => {
  const value: Scheduling = {api_strategy:'fifo', observed_at:2000000000, queued:0, processing:0,
    recovery_pending:0, oldest_queued_age_seconds:null, oldest_recovery_overdue_seconds:null,
    workers:{recent:0, stale:1, mismatched:0, ttl_seconds:30, status:'unknown'}};
  const {rerender} = render(<SchedulerStatus value={value}/>);
  expect(screen.getByText(/未观测到近期 Worker 心跳/)).toBeTruthy();
  rerender(<SchedulerStatus value={{...value, workers:{recent:1, stale:0, mismatched:0, ttl_seconds:30, status:'matching'}}}/>);
  expect(screen.getByText(/近期上报的 Worker 策略与当前 API 一致/)).toBeTruthy();
  rerender(<SchedulerStatus value={{...value, workers:{recent:2, stale:0, mismatched:1, ttl_seconds:30, status:'mismatch'}}}/>);
  expect(screen.getByText(/检测到 Worker 与当前 API 调度策略不一致/)).toBeTruthy();
});
test('shows tenant scope, API strategy and null versus zero waits', () => {
  const value: Scheduling = {api_strategy:'tenant_round_robin', observed_at:2000000000,
    queued:1, processing:2, recovery_pending:1, oldest_queued_age_seconds:0, oldest_recovery_overdue_seconds:15};
  const {rerender} = render(<SchedulerStatus value={value}/>);
  expect(screen.getByText(/API 配置的调度策略：租户轮转/)).toBeTruthy();
  expect(screen.getByText(/最早排队任务已等待：0 秒/)).toBeTruthy();
  expect(screen.getByText(/其中等待重新领取 1 项/)).toBeTruthy();
  expect(screen.getByText(/尚未核验各 Worker/)).toBeTruthy();
  rerender(<SchedulerStatus value={{...value, api_strategy:'fifo', queued:0, processing:0,
    recovery_pending:0, oldest_queued_age_seconds:null, oldest_recovery_overdue_seconds:null}}/>);
  expect(screen.getByText(/API 配置的调度策略：FIFO/)).toBeTruthy();
  expect(screen.getByText(/无排队任务/)).toBeTruthy();
  expect(screen.getByText(/无过期租约/)).toBeTruthy();
});
