<script setup lang="ts">
import { ElMessage } from 'element-plus'
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'

import * as kbApi from '@/api/kb'
import type { KbOut } from '@/api/types'
import CitationList from '@/components/CitationList.vue'
import MarkdownBlock from '@/components/MarkdownBlock.vue'
import { useChatStore } from '@/stores/chat'

const route = useRoute()
const chat = useChatStore()

const kbs = ref<KbOut[]>([])
const kbId = ref<number | null>(null)
const question = ref('')
const messagesRef = ref<HTMLElement | null>(null)

const currentKb = computed(() => kbs.value.find((item) => item.id === kbId.value) ?? null)
const canSend = computed(
  () => Boolean(kbId.value) && question.value.trim().length > 0 && !chat.streaming,
)

async function loadKbs(): Promise<void> {
  const page = await kbApi.listKbs(1, 50)
  kbs.value = page.items

  const queryKb = Number(route.query.kb)
  if (Number.isFinite(queryKb) && page.items.some((item) => item.id === queryKb)) {
    kbId.value = queryKb
  } else if (!kbId.value && page.items.length > 0) {
    kbId.value = page.items[0].id
  }
}

function scrollToBottom(): void {
  nextTick(() => {
    const element = messagesRef.value
    if (element) {
      element.scrollTop = element.scrollHeight
    }
  })
}

watch(
  () => chat.messages.map((message) => message.content.length).join(':'),
  scrollToBottom,
)

async function send(): Promise<void> {
  if (!canSend.value || kbId.value === null) {
    return
  }
  const text = question.value.trim()
  question.value = ''
  await chat.ask(kbId.value, text)
}

async function openConversation(conversationId: number): Promise<void> {
  await chat.loadConversation(conversationId)
  const conversation = chat.conversations.find((item) => item.id === conversationId)
  if (conversation) {
    kbId.value = conversation.kb_id
  }
}

function startNew(): void {
  chat.startNewConversation()
  question.value = ''
}

async function copyAnswer(content: string): Promise<void> {
  try {
    await navigator.clipboard.writeText(content)
    ElMessage.success('已复制')
  } catch {
    ElMessage.warning('复制失败，请手动选择文本')
  }
}

onMounted(async () => {
  await loadKbs()
  await chat.loadConversations()
})
</script>

<template>
  <div class="chat">
    <aside class="chat__aside">
      <el-button type="primary" plain class="chat__new" @click="startNew">
        + 新建对话
      </el-button>
      <div class="chat__history-title rag-muted">最近会话</div>
      <el-scrollbar class="chat__history">
        <div
          v-for="conversation in chat.conversations"
          :key="conversation.id"
          class="chat__history-item"
          :class="{ 'is-active': conversation.id === chat.currentConversationId }"
          @click="openConversation(conversation.id)"
        >
          <div class="chat__history-title-text">{{ conversation.title }}</div>
          <div class="rag-muted">{{ conversation.message_count }} 条消息</div>
        </div>
        <el-empty
          v-if="chat.conversations.length === 0"
          description="暂无会话"
          :image-size="60"
        />
      </el-scrollbar>
    </aside>

    <section class="chat__main">
      <div class="chat__toolbar">
        <el-select
          v-model="kbId"
          placeholder="选择知识库"
          style="width: 260px"
          :disabled="chat.streaming"
        >
          <el-option
            v-for="kb in kbs"
            :key="kb.id"
            :label="`${kb.name}（${kb.document_count} 个文档）`"
            :value="kb.id"
          />
        </el-select>
        <span v-if="currentKb" class="rag-muted">{{ currentKb.description || '暂无说明' }}</span>
      </div>

      <div ref="messagesRef" class="chat__messages">
        <el-empty
          v-if="chat.messages.length === 0"
          description="选择知识库后提问，例如：报销流程是什么？"
        />

        <div
          v-for="message in chat.messages"
          :key="`${message.role}-${message.id}-${message.content.length}`"
          class="chat__message"
          :class="message.role === 'user' ? 'chat__message--user' : 'chat__message--assistant'"
        >
          <div class="chat__bubble">
            <template v-if="message.role === 'user'">
              <div class="chat__user-text">{{ message.content }}</div>
            </template>
            <template v-else>
              <MarkdownBlock v-if="message.content" :content="message.content" />
              <span v-else class="rag-muted">正在生成…</span>
              <CitationList :citations="message.citations" />
              <div v-if="!message.streaming && message.content" class="chat__actions">
                <el-button link size="small" @click="copyAnswer(message.content)">复制</el-button>
              </div>
            </template>
          </div>
        </div>
      </div>

      <div class="chat__input">
        <el-input
          v-model="question"
          type="textarea"
          :rows="3"
          resize="none"
          maxlength="1000"
          show-word-limit
          placeholder="输入问题，Enter 发送，Shift + Enter 换行"
          :disabled="chat.streaming"
          @keydown.enter.exact.prevent="send"
        />
        <div class="chat__input-actions">
          <el-button v-if="chat.streaming" type="danger" plain @click="chat.stopStreaming()">
            停止
          </el-button>
          <el-button type="primary" :disabled="!canSend" :loading="chat.streaming" @click="send">
            发送
          </el-button>
        </div>
      </div>
    </section>
  </div>
</template>

<style scoped>
.chat {
  display: flex;
  gap: 16px;
  height: calc(100vh - 140px);
}

.chat__aside {
  width: 240px;
  background: #ffffff;
  border: 1px solid var(--el-border-color-light);
  border-radius: 8px;
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.chat__new {
  width: 100%;
}

.chat__history {
  flex: 1;
}

.chat__history-item {
  padding: 8px 10px;
  border-radius: 6px;
  cursor: pointer;
  margin-bottom: 4px;
}

.chat__history-item:hover {
  background: var(--el-fill-color-light);
}

.chat__history-item.is-active {
  background: var(--el-color-primary-light-9);
}

.chat__history-title-text {
  font-size: 13px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.chat__main {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 10px;
  min-width: 0;
}

.chat__toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
}

.chat__messages {
  flex: 1;
  overflow-y: auto;
  background: #ffffff;
  border: 1px solid var(--el-border-color-light);
  border-radius: 8px;
  padding: 16px;
}

.chat__message {
  display: flex;
  margin-bottom: 12px;
}

.chat__message--user {
  justify-content: flex-end;
}

.chat__bubble {
  max-width: 78%;
  padding: 10px 14px;
  border-radius: 8px;
  background: var(--el-fill-color-light);
  font-size: 14px;
}

.chat__message--user .chat__bubble {
  background: var(--el-color-primary-light-9);
}

.chat__user-text {
  white-space: pre-wrap;
}

.chat__actions {
  margin-top: 6px;
}

.chat__input {
  background: #ffffff;
  border: 1px solid var(--el-border-color-light);
  border-radius: 8px;
  padding: 12px;
}

.chat__input-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 8px;
}
</style>
