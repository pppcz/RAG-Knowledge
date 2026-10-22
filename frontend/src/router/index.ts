/** 路由与登录守卫。 */

import { createRouter, createWebHistory } from 'vue-router'

import { useAuthStore } from '@/stores/auth'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/login',
      name: 'login',
      component: () => import('@/views/LoginView.vue'),
      meta: { public: true, title: '登录' },
    },
    {
      path: '/',
      component: () => import('@/layouts/MainLayout.vue'),
      children: [
        { path: '', redirect: { name: 'kb' } },
        {
          path: 'kb',
          name: 'kb',
          component: () => import('@/views/KnowledgeBaseView.vue'),
          meta: { title: '知识库' },
        },
        {
          path: 'kb/:id/docs',
          name: 'documents',
          component: () => import('@/views/DocumentsView.vue'),
          props: true,
          meta: { title: '文档管理' },
        },
        {
          path: 'chat',
          name: 'chat',
          component: () => import('@/views/ChatView.vue'),
          meta: { title: '知识问答' },
        },
        {
          path: 'history',
          name: 'history',
          component: () => import('@/views/HistoryView.vue'),
          meta: { title: '会话历史' },
        },
      ],
    },
    { path: '/:pathMatch(.*)*', redirect: { name: 'kb' } },
  ],
})

router.beforeEach(async (to) => {
  const auth = useAuthStore()

  if (to.meta.public) {
    if (to.name === 'login' && auth.isAuthenticated) {
      return { name: 'kb' }
    }
    return true
  }

  if (!auth.isAuthenticated) {
    return { name: 'login', query: { redirect: to.fullPath } }
  }

  if (!auth.user) {
    try {
      await auth.fetchMe()
    } catch {
      auth.logout()
      return { name: 'login' }
    }
  }

  return true
})

router.afterEach((to) => {
  const title = to.meta.title as string | undefined
  document.title = title ? `${title} · 企业知识库` : '企业知识库 · RAG 问答平台'
})

export default router
