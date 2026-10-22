<script setup lang="ts">
import DOMPurify from 'dompurify'
import MarkdownIt from 'markdown-it'
import { computed } from 'vue'

const props = defineProps<{ content: string }>()

const markdown = new MarkdownIt({
  html: false,
  linkify: true,
  breaks: true,
})

const rendered = computed(() => {
  if (!props.content) {
    return ''
  }
  return DOMPurify.sanitize(markdown.render(props.content))
})
</script>

<template>
  <!-- 内容经 DOMPurify 过滤，禁止原始 HTML -->
  <div class="markdown" v-html="rendered" />
</template>

<style scoped>
.markdown {
  line-height: 1.7;
  word-break: break-word;
}

.markdown :deep(p) {
  margin: 0 0 8px;
}

.markdown :deep(p:last-child) {
  margin-bottom: 0;
}

.markdown :deep(ul),
.markdown :deep(ol) {
  margin: 0 0 8px;
  padding-left: 20px;
}

.markdown :deep(code) {
  background: rgba(0, 0, 0, 0.05);
  border-radius: 4px;
  padding: 1px 4px;
  font-size: 0.92em;
}

.markdown :deep(pre) {
  background: #f6f8fa;
  border-radius: 6px;
  padding: 10px 12px;
  overflow-x: auto;
}

.markdown :deep(pre code) {
  background: transparent;
  padding: 0;
}

.markdown :deep(blockquote) {
  margin: 0 0 8px;
  padding: 4px 12px;
  color: var(--rag-sub);
  border-left: 3px solid var(--el-border-color);
}

.markdown :deep(table) {
  border-collapse: collapse;
  margin-bottom: 8px;
}

.markdown :deep(th),
.markdown :deep(td) {
  border: 1px solid var(--el-border-color);
  padding: 4px 8px;
}
</style>
