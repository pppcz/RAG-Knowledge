<script setup lang="ts">
import type { Citation } from '@/api/types'

defineProps<{ citations: Citation[] }>()

function scorePercent(score: number): string {
  return `${Math.round(score * 100)}%`
}
</script>

<template>
  <div v-if="citations.length" class="citations">
    <div class="citations__title">引用来源</div>
    <el-tooltip
      v-for="citation in citations"
      :key="citation.chunk_id"
      placement="top"
      :show-after="200"
      :content="citation.snippet"
    >
      <div class="citations__item">
        <el-tag size="small" type="primary" effect="plain">[{{ citation.index }}]</el-tag>
        <span class="citations__name">{{ citation.filename }}</span>
        <span class="rag-muted">
          片段 {{ citation.chunk_index }} · 相似度 {{ scorePercent(citation.score) }}
        </span>
      </div>
    </el-tooltip>
  </div>
</template>

<style scoped>
.citations {
  margin-top: 10px;
  padding-top: 8px;
  border-top: 1px dashed var(--el-border-color);
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.citations__title {
  font-size: 12px;
  color: var(--rag-sub);
}

.citations__item {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  cursor: default;
}

.citations__name {
  color: var(--el-color-primary);
}
</style>
