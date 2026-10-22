/** 文档接口。 */

import { http } from './http'
import type { DocumentOut, PageResult } from './types'

export async function listDocs(
  params: { kb_id?: number; page?: number; page_size?: number } = {},
): Promise<PageResult<DocumentOut>> {
  const { data } = await http.get<PageResult<DocumentOut>>('/docs', {
    params: { page: 1, page_size: 50, ...params },
  })
  return data
}

export async function uploadDoc(
  file: File,
  kbId?: number,
  onProgress?: (percent: number) => void,
): Promise<DocumentOut> {
  const form = new FormData()
  form.append('file', file)
  if (kbId !== undefined) {
    form.append('kb_id', String(kbId))
  }
  const { data } = await http.post<DocumentOut>('/docs/upload', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
    onUploadProgress: (event) => {
      if (onProgress && event.total) {
        onProgress(Math.round((event.loaded / event.total) * 100))
      }
    },
  })
  return data
}

export async function getDoc(docId: number): Promise<DocumentOut> {
  const { data } = await http.get<DocumentOut>(`/docs/${docId}`)
  return data
}

export async function deleteDoc(docId: number): Promise<void> {
  await http.delete(`/docs/${docId}`)
}

export async function reindexDoc(docId: number): Promise<DocumentOut> {
  const { data } = await http.post<DocumentOut>(`/docs/${docId}/reindex`)
  return data
}
