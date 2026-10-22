/** Axios 实例：统一 baseURL、JWT 注入与错误处理。 */

import axios, { type AxiosError } from 'axios'
import { ElMessage } from 'element-plus'

export interface ApiErrorBody {
  code: number
  message: string
  detail?: Record<string, unknown>
}

export const TOKEN_KEY = 'rag_token'

export const http = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL ?? '/api',
  timeout: 30_000,
})

http.interceptors.request.use((config) => {
  const token = localStorage.getItem(TOKEN_KEY)
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

http.interceptors.response.use(
  (response) => response,
  (error: AxiosError<ApiErrorBody>) => {
    const status = error.response?.status
    const message = error.response?.data?.message ?? error.message ?? '请求失败'

    if (status === 401) {
      localStorage.removeItem(TOKEN_KEY)
      if (!window.location.pathname.startsWith('/login')) {
        window.location.replace('/login')
      }
    } else {
      ElMessage.error(message)
    }

    return Promise.reject(new Error(message))
  },
)

export function apiBaseUrl(): string {
  return import.meta.env.VITE_API_BASE_URL ?? '/api'
}
