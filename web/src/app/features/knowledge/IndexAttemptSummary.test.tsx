// @vitest-environment jsdom
import {cleanup,fireEvent,render,screen} from '@testing-library/react';
import {afterEach,expect,test,vi} from 'vitest';
import {IndexAttemptSummary, type AttemptSummary} from './IndexAttemptSummary';
afterEach(cleanup);
test('distinguishes zero, unknown usage and unconfirmed attribution',()=>{
 const value:AttemptSummary={scope:'all_exact_task_calls',unconfirmed_request_calls:3,attempts:[{attempt:null,calls:2,succeeded:1,failed:0,pending:1,known_input_tokens:0,known_output_tokens:null,known_elapsed_ms:0,unknown_input_tokens_calls:1,unknown_output_tokens_calls:2,unknown_elapsed_ms_calls:1}]};
 const {rerender}=render(<IndexAttemptSummary value={value}/>);
 expect(screen.getByText('尝试次数未知')).toBeTruthy();
 expect(screen.getByText(/已知输入 token：0/)).toBeTruthy();
 expect(screen.getByText(/已知输出 token：未知/)).toBeTruthy();
 expect(screen.getByText(/另有 3 次/)).toBeTruthy();
 expect(screen.getByText(/0 ms/)).toBeTruthy();
 rerender(<IndexAttemptSummary value={{...value,attempts:[]}}/>);
 expect(screen.getByText(/暂无精确关联调用/)).toBeTruthy();
 const select=vi.fn();
 rerender(<IndexAttemptSummary value={{...value,attempts:[{...value.attempts[0],attempt:2,failed:1}]}} onSelect={select}/>);
 fireEvent.click(screen.getByText('查看本次失败调用'));
 expect(select).toHaveBeenCalledWith(2,'failed');
 fireEvent.click(screen.getByText('查看本次调用'));
 expect(select).toHaveBeenCalledWith(2,'');
 const onError=vi.fn();
 rerender(<IndexAttemptSummary value={{...value,failure_reasons:[{attempt:2,error:null,calls:1}]}} onError={onError}/>);
 expect(screen.getByText(/缺失错误码 · 1 次/)).toBeTruthy();
 fireEvent.click(screen.getByText('查看此类失败'));
 expect(onError).toHaveBeenCalledWith(2,null);
});
