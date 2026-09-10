// @vitest-environment jsdom
import {cleanup, fireEvent, render, screen} from '@testing-library/react';
import {afterEach, expect, test, vi} from 'vitest';
import {AdminClient} from '../../shared/client';
import {AnswerPanel} from './AnswerPanel';
afterEach(() => {cleanup(); vi.restoreAllMocks();});
test('uses separate models and displays answer and original citations as text', async () => {
  const client = new AdminClient();
  const request = vi.spyOn(client, 'request').mockResolvedValue({answer:'回答 [1]', status:'answered', citations:[{
    citation_id:'1', filename:'手册.txt', chunk_index:0, source_kind:'page', source_index:2, start:0, end:10, text:'<script>test</script>',
  }]} as never);
  render(<AnswerPanel client={client} root="/scope" model="embed" chatModels={[{alias:'chat',deployment:'local'}]}/>);
  fireEvent.change(screen.getByLabelText('聊天模型'), {target:{value:'chat'}});
  fireEvent.change(screen.getByLabelText('提问'), {target:{value:'如何使用'}});
  fireEvent.click(screen.getByText('生成引用回答'));
  await screen.findByText('回答 [1]');
  expect(request).toHaveBeenCalledWith('/scope/answers', 'POST', {model:'embed',chat_model:'chat',query:'如何使用',limit:5}, expect.any(AbortSignal));
  expect(screen.getByText('<script>test</script>')).toBeTruthy();
  expect(document.querySelector('.knowledge-text script')).toBeNull();
  fireEvent.change(screen.getByLabelText('提问'), {target:{value:'新问题'}});
  expect(screen.queryByText('回答 [1]')).toBeNull();
});
