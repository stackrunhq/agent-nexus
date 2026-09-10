export interface KnowledgeDocument {
  id: string;
  filename: string;
  status: 'queued' | 'processing' | 'ready' | 'failed';
  published: boolean;
  error: string | null;
  warnings: string[];
}
export interface Chunk {
  chunk_index: number;
  text: string;
  source_kind: string;
  source_index: number;
  start: number;
  end: number;
}
export const statusLabels = {queued: '等待处理', processing: '正在解析', ready: '解析完成', failed: '处理失败'};
export const errorLabels: Record<string, string> = {
  invalid_document: '文件损坏或内容与格式不符', encrypted_pdf: '请先移除 PDF 密码保护',
  no_extractable_text: '没有可提取文本；扫描件暂不支持 OCR', unsupported_encoding: '请转为 UTF-8 编码',
  parser_timeout: '解析超时', parser_resource_limit: '解析资源超限',
  parser_process_failed: '解析进程异常，请检查 Worker', worker_interrupted: '任务多次中断，请检查 Worker 后重试',
  text_too_large: '文档文本过大', too_many_pages: 'PDF 超过 500 页', too_many_chunks: '分片超过 10000 个',
  archive_too_large: 'DOCX 解压体积过大', file_too_large: '文件超过 10 MiB',
};
