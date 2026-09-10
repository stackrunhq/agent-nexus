// @vitest-environment jsdom
import {cleanup, fireEvent, render, screen, waitFor} from '@testing-library/react';
import {afterEach, beforeEach, expect, test, vi} from 'vitest';
import {AdminClient} from '../../shared/client';
import {SearchPanel} from './SearchPanel';

beforeEach(() => {
  Object.defineProperty(window, 'matchMedia', {writable:true, value:vi.fn(() => ({matches:false, addListener(){}, removeListener(){}, addEventListener(){}, removeEventListener(){}}))});
});
afterEach(() => {cleanup(); vi.restoreAllMocks();});

test('search sends the version scope and renders source text without HTML interpretation', async () => {
  const client = new AdminClient();
  const request = vi.spyOn(client, 'request').mockResolvedValue({data:[{document_id:'d', chunk_index:0, filename:'manual.txt', source_kind:'page', source_index:2, start:0, end:10, text:'<img src=x>', score:1}]} as never);
  render(<SearchPanel client={client} root="/tenants/t/applications/a/versions/v/search" enabled/>);
  fireEvent.change(screen.getByLabelText('手册关键词'), {target:{value:'重置密码'}});
  fireEvent.click(screen.getByRole('button', {name:'检索手册'}));
  await screen.findByText('<img src=x>');
  expect(document.querySelector('.knowledge-text img')).toBeNull();
  expect(request).toHaveBeenCalledWith('/tenants/t/applications/a/versions/v/search', 'POST', {query:'重置密码',limit:5}, expect.any(AbortSignal));
});

test('search distinguishes empty results and cancels when scope closes', async () => {
  const client = new AdminClient();
  const request = vi.spyOn(client, 'request').mockResolvedValue({data:[]} as never);
  const view = render(<SearchPanel client={client} root="/search" enabled/>);
  fireEvent.change(screen.getByLabelText('手册关键词'), {target:{value:'missing'}});
  fireEvent.click(screen.getByRole('button', {name:'检索手册'}));
  await screen.findByText(/未找到匹配内容/);
  request.mockImplementation(() => new Promise(() => {}));
  fireEvent.click(screen.getByRole('button', {name:'检索手册'}));
  await waitFor(() => expect(request).toHaveBeenCalledTimes(2));
  const signal = request.mock.calls[1][3];
  view.unmount();
  expect(signal?.aborted).toBe(true);
});
