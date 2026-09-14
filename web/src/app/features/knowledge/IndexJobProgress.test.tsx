// @vitest-environment jsdom
import {cleanup, render, screen} from '@testing-library/react';
import {afterEach, expect, test} from 'vitest';
import {IndexJobProgress, type IndexJob} from './IndexJobProgress';
afterEach(cleanup);
const task: IndexJob = {id:'job', model:'local', status:'processing', attempts:2, error:null, saved_batches:3, recovery_state:'waiting_for_worker'};
test('shows saved batches and distinguishes waiting from reclaimed processing', () => {
  const {rerender} = render(<IndexJobProgress task={task}/>);
  expect(screen.getByText(/已保存 3 批/)).toBeTruthy();
  expect(screen.getByText(/租约已到期/)).toBeTruthy();
  rerender(<IndexJobProgress task={{...task, recovery_state:'retrying'}}/>);
  expect(screen.queryByText(/租约已到期/)).toBeNull();
  expect(screen.getByText(/Worker 已重新领取/)).toBeTruthy();
  expect(screen.getByText(/不是完成百分比/)).toBeTruthy();
});
test('terminal jobs do not display stale checkpoint progress', () => {
  const {rerender} = render(<IndexJobProgress task={{...task, status:'succeeded'}}/>);
  expect(screen.queryByText(/已保存/)).toBeNull();
  expect(screen.getByText(/临时检查点已清理/)).toBeTruthy();
  rerender(<IndexJobProgress task={{...task, status:'failed', error:'index_stale'}}/>);
  expect(screen.getByText(/旧索引保留/)).toBeTruthy();
  expect(screen.getByText(/index_stale/)).toBeTruthy();
});
