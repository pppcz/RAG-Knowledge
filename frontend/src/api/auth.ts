/** 鉴权接口。 */

import { http } from './http'
import type { MeResponse, TokenResponse, UserOut } from './types'

export interface LoginPayload {
  username: string
  password: string
  tenant_slug?: string
}

export interface RegisterPayload {
  tenant_name: string
  tenant_slug?: string
  username: string
  email: string
  password: string
  full_name?: string
}

export async function login(payload: LoginPayload): Promise<TokenResponse> {
  const { data } = await http.post<TokenResponse>('/auth/login', payload)
  return data
}

export async function register(payload: RegisterPayload): Promise<TokenResponse> {
  const { data } = await http.post<TokenResponse>('/auth/register', payload)
  return data
}

export async function fetchMe(): Promise<MeResponse> {
  const { data } = await http.get<MeResponse>('/auth/me')
  return data
}

export async function listUsers(page = 1, pageSize = 20): Promise<{ items: UserOut[]; total: number }> {
  const { data } = await http.get<{ items: UserOut[]; total: number }>('/auth/users', {
    params: { page, page_size: pageSize },
  })
  return data
}
