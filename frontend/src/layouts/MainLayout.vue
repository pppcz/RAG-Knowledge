<script setup lang="ts">
import { ChatDotRound, Clock, Folder, SwitchButton } from '@element-plus/icons-vue'
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const router = useRouter()
const route = useRoute()

const activeMenu = computed(() => {
  if (route.name === 'documents') {
    return 'kb'
  }
  return String(route.name ?? 'kb')
})

function handleLogout(): void {
  auth.logout()
  router.replace({ name: 'login' })
}
</script>

<template>
  <el-container class="layout">
    <el-aside width="220px" class="layout__aside">
      <div class="layout__brand">
        <el-icon :size="20"><ChatDotRound /></el-icon>
        <span>企业知识库</span>
      </div>
      <el-menu :default-active="activeMenu" router class="layout__menu">
        <el-menu-item index="kb" :route="{ name: 'kb' }">
          <el-icon><Folder /></el-icon>
          <span>知识库</span>
        </el-menu-item>
        <el-menu-item index="chat" :route="{ name: 'chat' }">
          <el-icon><ChatDotRound /></el-icon>
          <span>知识问答</span>
        </el-menu-item>
        <el-menu-item index="history" :route="{ name: 'history' }">
          <el-icon><Clock /></el-icon>
          <span>会话历史</span>
        </el-menu-item>
      </el-menu>
    </el-aside>

    <el-container>
      <el-header class="layout__header">
        <span class="rag-muted">RAG 知识库问答平台</span>
        <div class="layout__user">
          <span>{{ auth.displayName }}</span>
          <el-tag v-if="auth.roles.length" size="small" type="info">{{ auth.roles.join(', ') }}</el-tag>
          <el-button text :icon="SwitchButton" @click="handleLogout">退出</el-button>
        </div>
      </el-header>

      <el-main class="layout__main">
        <RouterView />
      </el-main>
    </el-container>
  </el-container>
</template>

<style scoped>
.layout {
  height: 100%;
}

.layout__aside {
  background: #ffffff;
  border-right: 1px solid var(--el-border-color-light);
  display: flex;
  flex-direction: column;
}

.layout__brand {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 18px 20px;
  font-weight: 600;
  font-size: 16px;
  border-bottom: 1px solid var(--el-border-color-lighter);
}

.layout__menu {
  border-right: none;
}

.layout__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: #ffffff;
  border-bottom: 1px solid var(--el-border-color-light);
}

.layout__user {
  display: flex;
  align-items: center;
  gap: 10px;
}

.layout__main {
  padding: 20px;
  overflow: auto;
}
</style>
