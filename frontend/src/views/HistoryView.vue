<script setup lang="ts">
import { onMounted, ref } from 'vue'

import * as chatApi from '@/api/chat'
import type { ConversationDetail, ConversationOut } from '@/api/types'
import CitationList from '@/components/CitationList.vue'
import MarkdownBlock from '@/components/MarkdownBlock.vue'

const loading = ref(false)
const conversations = ref<ConversationOut[]>([])
const total = ref(0)

const drawerVisible = ref(false)
const detailLoading = ref(false)
const detail = ref<ConversationDetail | null>(null)

async function load(): Promise<void> {
  loading.value = true
  try {
    const page = await chatApi.listHistory(1, 50)
    conversations.value = page.items
    total.value = page.total
  } finally {
    loading.value = false
  }
}

async function openDetail(conversation: ConversationOut): Promise<void> {
  drawerVisible.value = true
  detailLoading.value = true
  try {
    detail.value = await chatApi.getHistoryDetail(conversation.id)
  } finally {
    detailLoading.value = false
  }
}

onMounted(load)
</script>

<template>
  <div class="rag-page">
    <div class="rag-page__header">
      <div>
        <h2 class="rag-page__title">会话历史</h2>
        <span class="rag-muted">共 {{ total }} 个会话（仅显示当前账号）</span>
      </div>
      <el-button :loading="loading" @click="load">刷新</el-button>
    </div>

    <el-card shadow="never">
      <el-table
        v-loading="loading"
        :data="conversations"
        empty-text="暂无会话，去问答页提一个问题吧"
      >
        <el-table-column prop="id" label="ID" width="70" />
        <el-table-column prop="title" label="标题" min-width="220" show-overflow-tooltip />
        <el-table-column prop="kb_id" label="知识库" width="90" align="center" />
        <el-table-column prop="message_count" label="消息数" width="90" align="center" />
        <el-table-column prop="created_at" label="创建时间" width="200">
          <template #default="{ row }">
            {{ new Date(row.created_at).toLocaleString() }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="100" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="openDetail(row)">查看</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-drawer v-model="drawerVisible" title="会话详情" size="52%">
      <div v-loading="detailLoading">
        <template v-if="detail">
          <el-descriptions :column="2" border size="small" class="history__meta">
            <el-descriptions-item label="会话 ID">{{ detail.conversation.id }}</el-descriptions-item>
            <el-descriptions-item label="知识库">{{ detail.conversation.kb_id }}</el-descriptions-item>
            <el-descriptions-item label="消息数">
              {{ detail.conversation.message_count }}
            </el-descriptions-item>
            <el-descriptions-item label="创建时间">
              {{ new Date(detail.conversation.created_at).toLocaleString() }}
            </el-descriptions-item>
          </el-descriptions>

          <div class="history__messages">
            <div
              v-for="message in detail.messages"
              :key="message.id"
              class="history__message"
              :class="message.role === 'user' ? 'history__message--user' : ''"
            >
              <div class="history__role rag-muted">
                {{ message.role === 'user' ? '我' : '助手' }} ·
                {{ new Date(message.created_at).toLocaleString() }}
              </div>
              <div class="history__bubble">
                <MarkdownBlock v-if="message.role === 'assistant'" :content="message.content" />
                <div v-else class="history__user-text">{{ message.content }}</div>
                <CitationList :citations="message.citations ?? []" />
              </div>
            </div>
          </div>
        </template>
        <el-empty v-else description="暂无数据" />
      </div>
    </el-drawer>
  </div>
</template>

<style scoped>
.history__meta {
  margin-bottom: 16px;
}

.history__messages {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.history__message--user {
  align-self: flex-end;
  max-width: 80%;
}

.history__role {
  font-size: 12px;
  margin-bottom: 4px;
}

.history__bubble {
  background: var(--el-fill-color-light);
  border-radius: 8px;
  padding: 10px 14px;
  font-size: 14px;
}

.history__message--user .history__bubble {
  background: var(--el-color-primary-light-9);
}

.history__user-text {
  white-space: pre-wrap;
}
</style>
