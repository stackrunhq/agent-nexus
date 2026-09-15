import {useState} from 'react';
import {IndexJobProgress, type IndexJob} from './IndexJobProgress';
import {indexFailure} from './indexFailure';

export function IndexJobList({jobs}: {jobs: IndexJob[]}) {
  const [filter, setFilter] = useState('all');
  const failures = [...new Set(jobs.filter(job => job.status === 'failed').map(job => job.error ?? ''))].sort();
  const visible = jobs.filter(job => filter === 'all' || (job.status === 'failed' && (filter === 'failed' || filter === `error:${job.error ?? ''}`)));
  return <section aria-label="索引任务列表">
    <label>失败原因筛选 <select aria-label="失败原因筛选" value={filter} onChange={event => setFilter(event.target.value)}>
      <option value="all">全部已加载任务</option>
      <option value="failed">全部失败任务</option>
      {failures.map(code => <option key={code} value={`error:${code}`}>{indexFailure(code).reason}（{code || '无错误码'}）</option>)}
      {filter.startsWith('error:') && !failures.includes(filter.slice(6)) && <option value={filter}>此前选择的原因（当前无记录）</option>}
    </select></label>
    <p>筛选范围：当前版本最近 20 条任务中属于所选模型的已加载记录，共 {jobs.length} 条；当前显示 {visible.length} 条。不是完整历史。</p>
    {!visible.length && <p>当前筛选范围内没有任务。</p>}
    {visible.map(task => <IndexJobProgress key={task.id} task={task}/>)}
  </section>;
}
