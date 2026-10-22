/** 知识库接口。 */

import { http } from './http'
import type { KbOut, PageResult, SearchResponse } from './types'

export interface KbPayload {
  name: string
  description?: string | null
}

export async function listKbs(page = 1, pageSize = 50): Promise<PageResult<KbOut>> {
  const { data } = await http.get<PageResult<KbOut>>('/kb', {
    params: { page, page_size: pageSize },
  })
  return data
}

export async function createKb(payload: KbPayload): Promise<KbOut> {
  const { data } = await http.post<KbOut>('/kb', payload)
  return data
}

export async function getKb(kbId: number): Promise<KbOut> {
  const { data } = await http.get<KbOut>(`/kb/${kbId}`)
  return data
}

export async function updateKb(kbId: number, payload: Partial<KbPayload>): Promise<KbOut> {
  const { data } = await http.patch<KbOut>(`/kb/${kbId}`, payload)
  return data
}

export async function deleteKb(kbId: number): Promise<void> {
  await http.delete(`/kb/${kbId}`)
}

export async function searchKb(
  kbId: number,
  query: string,
  topK = 5,
): Promise<SearchResponse> {
  const { data } = await http.get<SearchResponse>('/kb/search', {
    params: { kb_id: kbId, q: query, top_k: topK },
  })
  return data
}
