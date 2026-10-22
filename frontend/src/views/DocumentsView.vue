<script setup lang="ts">
import { ElMessage, ElMessageBox, type UploadRequestOptions } from 'element-plus'
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import * as docsApi from '@/api/docs'
import * as kbApi from '@/api/kb'
import type { DocumentOut, DocumentStatus, KbOut } from '@/api/types'

const props = defineProps<{ id: string }>()

const router = useRouter()
const kbId = computed(() => Number(props.id))

const kb = ref<KbOut | null>(null)
const docs = ref<DocumentOut[]>([])
const loading = ref(false)
const uploading = ref(false)
const uploadPercent = ref(0)

const STATUS_TYPES: Record<DocumentStatus, 'success' | 'warning' | 'danger' | 'info'> = {
  ready: 'success',
  processing: 'warning',
  pending: 'info',
  failed: 'danger',
}

const STATUS_LABELS: Record<DocumentStatus, string> = {
  ready: '已索引',
  processing: '处理中',
  pending: '待处理',
  failed: '失败',
}

async function load(): Promise<void> {
  loading.value = true
  try {
    const [kbDetail, page] = await Promise.all([
      kbApi.getKb(kbId.value),
      docsApi.listDocs({ kb_id: kbId.value, page_size: 100 }),
    ])
    kb.value = kbDetail
    docs.value = page.items
  } finally {
    loading.value = false
  }
}

async function handleUpload(options: UploadRequestOptions): Promise<void> {
  uploading.value = true
  uploadPercent.value = 0
  try {
    const document = await docsApi.uploadDoc(options.file, kbId.value, (percent) => {
      uploadPercent.value = percent
    })
    if (document.status === 'failed') {
      ElMessage.warning(`上传成功但解析失败：${document.error_message ?? '未知原因'}`)
    } else {
      ElMessage.success(`上传成功，已切分为 ${document.chunk_count} 个片段`)
    }
    await load()
  } finally {
    uploading.value = false
  }
}

async function reindex(document: DocumentOut): Promise<void> {
  const result = await docsApi.reindexDoc(document.id)
  if (result.status === 'ready') {
    ElMessage.success(`重建完成，共 ${result.chunk_count} 个片段`)
  } else {
    ElMessage.warning(`重建失败：${result.error_message ?? '未知原因'}`)
  }
  await load()
}

async function remove(document: DocumentOut): Promise<void> {
  try {
    await ElMessageBox.confirm(`确认删除文档「${document.title}」？`, '删除确认', {
      type: 'warning',
      confirmButtonText: '删除',
      cancelButtonText: '取消',
    })
  } catch {
    return
  }
  await docsApi.deleteDoc(document.id)
  ElMessage.success('已删除')
  await load()
}

function formatSize(bytes: number): string {
  if (bytes < 1024) {
    return `${bytes} B`
  }
  if (bytes < 1024 * 1024) {
    return `${(bytes / 1024).toFixed(1)} KB`
  }
  return `${(bytes / 1024 / 1024).toFixed(2)} MB`
}

onMounted(load)
</script>

<template>
  <div class="rag-page">
    <div class="rag-page__header">
      <div>
        <h2 class="rag-page__title">
          <el-button link @click="router.push({ name: 'kb' })">← 返回</el-button>
          {{ kb?.name ?? '文档管理' }}
        </h2>
        <span class="rag-muted">知识库 #{{ kbId }} · 共 {{ docs.length }} 个文档</span>
      </div>
      <div class="rag-toolbar">
        <el-button :loading="loading" @click="load">刷新</el-button>
      </div>
    </div>

    <el-card shadow="never">
      <el-upload
        drag
        :show-file-list="false"
        :http-request="handleUpload"
        :disabled="uploading"
        accept=".pdf,.docx,.md,.txt"
      >
        <div class="upload">
          <p class="upload__title">拖拽文件到此处，或<em>点击上传</em></p>
          <p class="rag-muted">支持 PDF / Word(.docx) / Markdown / TXT，单个文件不超过 20 MB</p>
          <el-progress
            v-if="uploading"
            :percentage="uploadPercent"
            :stroke-width="6"
            class="upload__progress"
          />
        </div>
      </el-upload>
    </el-card>

    <el-card shadow="never">
      <el-table v-loading="loading" :data="docs" empty-text="暂无文档，请先上传">
        <el-table-column prop="title" label="标题" min-width="180" show-overflow-tooltip />
        <el-table-column prop="file_ext" label="类型" width="80" align="center" />
        <el-table-column label="大小" width="100" align="right">
          <template #default="{ row }">{{ formatSize(row.size_bytes) }}</template>
        </el-table-column>
        <el-table-column label="状态" width="110" align="center">
          <template #default="{ row }">
            <el-tooltip
              v-if="row.status === 'failed'"
              :content="row.error_message || '解析失败'"
              placement="top"
            >
              <el-tag :type="STATUS_TYPES[row.status as DocumentStatus]" size="small">
                {{ STATUS_LABELS[row.status as DocumentStatus] }}
              </el-tag>
            </el-tooltip>
            <el-tag v-else :type="STATUS_TYPES[row.status as DocumentStatus]" size="small">
              {{ STATUS_LABELS[row.status as DocumentStatus] }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="chunk_count" label="片段数" width="90" align="center" />
        <el-table-column prop="created_at" label="上传时间" width="200">
          <template #default="{ row }">
            {{ new Date(row.created_at).toLocaleString() }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="180" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="reindex(row)">重建索引</el-button>
            <el-button link type="danger" @click="remove(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<style scoped>
.upload {
  padding: 12px 0;
  text-align: center;
}

.upload__title {
  margin: 0 0 6px;
  font-size: 14px;
}

.upload__title em {
  color: var(--el-color-primary);
  font-style: normal;
}

.upload__progress {
  margin: 12px auto 0;
  max-width: 320px;
}
</style>
