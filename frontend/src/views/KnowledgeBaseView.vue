<script setup lang="ts">
import { ElMessage, ElMessageBox, type FormInstance, type FormRules } from 'element-plus'
import { onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'

import * as kbApi from '@/api/kb'
import type { KbOut } from '@/api/types'

const router = useRouter()

const loading = ref(false)
const kbs = ref<KbOut[]>([])
const total = ref(0)

const dialogVisible = ref(false)
const submitting = ref(false)
const editingId = ref<number | null>(null)
const formRef = ref<FormInstance>()
const form = reactive({ name: '', description: '' })
const rules: FormRules = {
  name: [{ required: true, message: '请输入知识库名称', trigger: 'blur' }],
}

async function load(): Promise<void> {
  loading.value = true
  try {
    const page = await kbApi.listKbs(1, 50)
    kbs.value = page.items
    total.value = page.total
  } finally {
    loading.value = false
  }
}

function openCreate(): void {
  editingId.value = null
  form.name = ''
  form.description = ''
  dialogVisible.value = true
}

function openEdit(kb: KbOut): void {
  editingId.value = kb.id
  form.name = kb.name
  form.description = kb.description ?? ''
  dialogVisible.value = true
}

async function submit(): Promise<void> {
  if (!formRef.value) {
    return
  }
  const valid = await formRef.value.validate().catch(() => false)
  if (!valid) {
    return
  }

  submitting.value = true
  try {
    const payload = { name: form.name, description: form.description || null }
    if (editingId.value === null) {
      await kbApi.createKb(payload)
      ElMessage.success('知识库已创建')
    } else {
      await kbApi.updateKb(editingId.value, payload)
      ElMessage.success('知识库已更新')
    }
    dialogVisible.value = false
    await load()
  } finally {
    submitting.value = false
  }
}

async function remove(kb: KbOut): Promise<void> {
  try {
    await ElMessageBox.confirm(`确认删除知识库「${kb.name}」及其文档？`, '删除确认', {
      type: 'warning',
      confirmButtonText: '删除',
      cancelButtonText: '取消',
    })
  } catch {
    return
  }

  await kbApi.deleteKb(kb.id)
  ElMessage.success('已删除')
  await load()
}

function goDocuments(kb: KbOut): void {
  router.push({ name: 'documents', params: { id: String(kb.id) } })
}

function goChat(kb: KbOut): void {
  router.push({ name: 'chat', query: { kb: String(kb.id) } })
}

onMounted(load)
</script>

<template>
  <div class="rag-page">
    <div class="rag-page__header">
      <div>
        <h2 class="rag-page__title">知识库</h2>
        <span class="rag-muted">共 {{ total }} 个知识库</span>
      </div>
      <div class="rag-toolbar">
        <el-button :loading="loading" @click="load">刷新</el-button>
        <el-button type="primary" @click="openCreate">新建知识库</el-button>
      </div>
    </div>

    <el-card shadow="never">
      <el-table v-loading="loading" :data="kbs" empty-text="暂无知识库，请先新建">
        <el-table-column prop="id" label="ID" width="70" />
        <el-table-column prop="name" label="名称" min-width="160" />
        <el-table-column prop="description" label="说明" min-width="200">
          <template #default="{ row }">
            <span class="rag-muted">{{ row.description || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="document_count" label="文档数" width="90" align="center" />
        <el-table-column prop="updated_at" label="更新时间" width="200">
          <template #default="{ row }">
            {{ new Date(row.updated_at).toLocaleString() }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="290" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="goDocuments(row)">文档</el-button>
            <el-button link type="primary" @click="goChat(row)">问答</el-button>
            <el-button link type="primary" @click="openEdit(row)">编辑</el-button>
            <el-button link type="danger" @click="remove(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog
      v-model="dialogVisible"
      :title="editingId === null ? '新建知识库' : '编辑知识库'"
      width="480px"
    >
      <el-form ref="formRef" :model="form" :rules="rules" label-width="80px">
        <el-form-item label="名称" prop="name">
          <el-input v-model="form.name" maxlength="128" show-word-limit />
        </el-form-item>
        <el-form-item label="说明">
          <el-input
            v-model="form.description"
            type="textarea"
            :rows="3"
            maxlength="512"
            show-word-limit
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="submit">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>
