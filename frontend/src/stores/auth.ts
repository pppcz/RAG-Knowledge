/** 登录态 store：JWT、用户、角色与权限。 */

import { computed, ref } from 'vue'
import { defineStore } from 'pinia'

import * as authApi from '@/api/auth'
import type { LoginPayload, RegisterPayload } from '@/api/auth'
import { TOKEN_KEY } from '@/api/http'
import type { UserOut } from '@/api/types'

export const useAuthStore = defineStore('auth', () => {
  const token = ref<string>(localStorage.getItem(TOKEN_KEY) ?? '')
  const user = ref<UserOut | null>(null)
  const roles = ref<string[]>([])
  const permissions = ref<string[]>([])

  const isAuthenticated = computed(() => Boolean(token.value))
  const displayName = computed(() => user.value?.full_name || user.value?.username || '未登录')

  function setToken(value: string): void {
    token.value = value
    if (value) {
      localStorage.setItem(TOKEN_KEY, value)
    } else {
      localStorage.removeItem(TOKEN_KEY)
    }
  }

  function can(permission: string): boolean {
    return permissions.value.includes(permission) || roles.value.includes('admin')
  }

  async function login(payload: LoginPayload): Promise<void> {
    const result = await authApi.login(payload)
    setToken(result.access_token)
    user.value = result.user
    await fetchMe()
  }

  async function register(payload: RegisterPayload): Promise<void> {
    const result = await authApi.register(payload)
    setToken(result.access_token)
    user.value = result.user
    await fetchMe()
  }

  async function fetchMe(): Promise<void> {
    const result = await authApi.fetchMe()
    user.value = result.user
    roles.value = result.roles
    permissions.value = result.permissions
  }

  function logout(): void {
    setToken('')
    user.value = null
    roles.value = []
    permissions.value = []
  }

  return {
    token,
    user,
    roles,
    permissions,
    isAuthenticated,
    displayName,
    can,
    login,
    register,
    fetchMe,
    logout,
  }
})
