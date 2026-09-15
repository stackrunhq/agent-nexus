// @vitest-environment jsdom
import {cleanup, render, screen} from '@testing-library/react';
import {afterEach, expect, test} from 'vitest';
import {SchedulerStatus, type Scheduling} from './SchedulerStatus';
afterEach(cleanup);
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
