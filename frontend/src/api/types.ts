/** 后端接口数据类型（与 docs/api.md 保持一致）。 */

export interface PageResult<T> {
  items: T[]
  total: number
  page: number
  page_size: number
}

export interface UserOut {
  id: number
  tenant_id: number
  username: string
  email: string
  full_name: string | null
  is_active: boolean
  is_superuser: boolean
  created_at: string
}

export interface TokenResponse {
  access_token: string
  token_type: string
  expires_in: number
  user: UserOut
}

export interface MeResponse {
  user: UserOut
  roles: string[]
  permissions: string[]
}

export interface KbOut {
  id: number
  tenant_id: number
  name: string
  description: string | null
  document_count: number
  created_at: string
  updated_at: string
}

export type DocumentStatus = 'pending' | 'processing' | 'ready' | 'failed'

export interface DocumentOut {
  id: number
  tenant_id: number
  kb_id: number
  title: string
  filename: string
  file_ext: string
  content_type: string | null
  size_bytes: number
  checksum: string | null
  status: DocumentStatus
  error_message: string | null
  chunk_count: number
  created_at: string
  updated_at: string
}

export interface SearchHit {
  chunk_id: number
  document_id: number
  document_title: string
  filename: string
  chunk_index: number
  content: string
  score: number
}

export interface SearchResponse {
  kb_id: number
  query: string
  top_k: number
  total: number
  items: SearchHit[]
}

export interface Citation {
  index: number
  document_id: number
  document_title: string
  filename: string
  chunk_id: number
  chunk_index: number
  score: number
  snippet: string
}

export interface MessageOut {
  id: number
  role: 'user' | 'assistant'
  content: string
  citations: Citation[] | null
  created_at: string
}

export interface ConversationOut {
  id: number
  kb_id: number
  title: string
  message_count: number
  created_at: string
  updated_at: string
}

export interface ConversationDetail {
  conversation: ConversationOut
  messages: MessageOut[]
}

export interface AskDonePayload {
  conversation_id: number
  message_id: number
  content_length: number
  citations: Citation[]
}
