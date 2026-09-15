// @vitest-environment jsdom
import {cleanup, fireEvent, render, screen} from '@testing-library/react';
import {afterEach, expect, test} from 'vitest';
import {IndexJobList} from './IndexJobList';
import {type IndexJob} from './IndexJobProgress';

afterEach(cleanup);
const jobs: IndexJob[] = [
  {id:'ok', model:'local', status:'succeeded', attempts:1, error:null},
  {id:'timeout', model:'local', status:'failed', attempts:1, error:'provider_timeout'},
  {id:'unknown', model:'local', status:'failed', attempts:1, error:'future_error'},
  {id:'missing', model:'local', status:'failed', attempts:1, error:null},
];

test('filters failures by exact code, preserves unknown codes and handles refreshed empty results', () => {
  const {rerender} = render(<IndexJobList jobs={jobs}/>);
  expect(screen.getByText(/最近 20 条/)).toBeTruthy();
  fireEvent.change(screen.getByLabelText('失败原因筛选'), {target:{value:'failed'}});
  expect(screen.queryByLabelText('索引任务 ok')).toBeNull();
  expect(screen.getByLabelText('索引任务 missing')).toBeTruthy();
  fireEvent.change(screen.getByLabelText('失败原因筛选'), {target:{value:'error:provider_timeout'}});
  expect(screen.getByLabelText('索引任务 timeout')).toBeTruthy();
  expect(screen.queryByLabelText('索引任务 unknown')).toBeNull();
  expect(screen.getByText(/检查模型服务负载和超时配置/)).toBeTruthy();
  rerender(<IndexJobList jobs={[]}/>);
  expect(screen.getByText('当前筛选范围内没有任务。')).toBeTruthy();
  fireEvent.change(screen.getByLabelText('失败原因筛选'), {target:{value:'all'}});
  rerender(<IndexJobList jobs={jobs}/>);
  expect(screen.getByLabelText('索引任务 ok')).toBeTruthy();
  expect(screen.getByLabelText('索引任务 unknown').textContent).toContain('其他失败原因');
});

test('null failure codes can be selected without including successful jobs', () => {
  render(<IndexJobList jobs={jobs}/>);
  fireEvent.change(screen.getByLabelText('失败原因筛选'), {target:{value:'error:'}});
  expect(screen.getByLabelText('索引任务 missing')).toBeTruthy();
  expect(screen.queryByLabelText('索引任务 ok')).toBeNull();
  expect(screen.queryByLabelText('索引任务 timeout')).toBeNull();
});
