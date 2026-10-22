<script setup lang="ts">
import { ElMessage, type FormInstance, type FormRules } from 'element-plus'
import { reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const router = useRouter()
const route = useRoute()

const activeTab = ref<'login' | 'register'>('login')
const loading = ref(false)

const loginFormRef = ref<FormInstance>()
const loginForm = reactive({
  username: 'admin',
  password: '123456',
  tenant_slug: '',
})
const loginRules: FormRules = {
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }],
}

const registerFormRef = ref<FormInstance>()
const registerForm = reactive({
  tenant_name: '',
  tenant_slug: '',
  username: '',
  email: '',
  password: '',
  full_name: '',
})
const registerRules: FormRules = {
  tenant_name: [{ required: true, message: '请输入租户名称', trigger: 'blur' }],
  username: [
    { required: true, message: '请输入用户名', trigger: 'blur' },
    { pattern: /^[A-Za-z0-9_]{3,64}$/, message: '3-64 位字母、数字或下划线', trigger: 'blur' },
  ],
  email: [
    { required: true, message: '请输入邮箱', trigger: 'blur' },
    { type: 'email', message: '邮箱格式不正确', trigger: 'blur' },
  ],
  password: [
    { required: true, message: '请输入密码', trigger: 'blur' },
    { min: 6, max: 72, message: '密码长度 6-72 位', trigger: 'blur' },
  ],
}

function afterLogin(): void {
  const redirect = route.query.redirect
  if (typeof redirect === 'string' && redirect.startsWith('/')) {
    router.replace(redirect)
    return
  }
  router.replace({ name: 'kb' })
}

async function submitLogin(): Promise<void> {
  if (!loginFormRef.value) {
    return
  }
  const valid = await loginFormRef.value.validate().catch(() => false)
  if (!valid) {
    return
  }

  loading.value = true
  try {
    await auth.login({
      username: loginForm.username,
      password: loginForm.password,
      tenant_slug: loginForm.tenant_slug || undefined,
    })
    ElMessage.success('登录成功')
    afterLogin()
  } finally {
    loading.value = false
  }
}

async function submitRegister(): Promise<void> {
  if (!registerFormRef.value) {
    return
  }
  const valid = await registerFormRef.value.validate().catch(() => false)
  if (!valid) {
    return
  }

  loading.value = true
  try {
    await auth.register({
      tenant_name: registerForm.tenant_name,
      tenant_slug: registerForm.tenant_slug || undefined,
      username: registerForm.username,
      email: registerForm.email,
      password: registerForm.password,
      full_name: registerForm.full_name || undefined,
    })
    ElMessage.success('注册成功，已自动登录')
    afterLogin()
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="login">
    <el-card class="login__card" shadow="always">
      <div class="login__brand">
        <h1>企业知识库</h1>
        <p class="rag-muted">RAG 问答平台 · 多租户 · 引用溯源</p>
      </div>

      <el-tabs v-model="activeTab" stretch>
        <el-tab-pane label="登录" name="login">
          <el-form
            ref="loginFormRef"
            :model="loginForm"
            :rules="loginRules"
            label-position="top"
            @submit.prevent="submitLogin"
          >
            <el-form-item label="用户名" prop="username">
              <el-input v-model="loginForm.username" placeholder="admin" autocomplete="username" />
            </el-form-item>
            <el-form-item label="密码" prop="password">
              <el-input
                v-model="loginForm.password"
                type="password"
                show-password
                placeholder="123456"
                autocomplete="current-password"
                @keyup.enter="submitLogin"
              />
            </el-form-item>
            <el-form-item label="租户标识（同名用户存在多个租户时必填）">
              <el-input v-model="loginForm.tenant_slug" placeholder="例如 default，可留空" />
            </el-form-item>
            <el-button type="primary" class="login__submit" :loading="loading" @click="submitLogin">
              登录
            </el-button>
          </el-form>
        </el-tab-pane>

        <el-tab-pane label="注册租户" name="register">
          <el-form
            ref="registerFormRef"
            :model="registerForm"
            :rules="registerRules"
            label-position="top"
            @submit.prevent="submitRegister"
          >
            <el-form-item label="租户名称" prop="tenant_name">
              <el-input v-model="registerForm.tenant_name" placeholder="例如 示例公司" />
            </el-form-item>
            <el-form-item label="租户标识（可选）">
              <el-input v-model="registerForm.tenant_slug" placeholder="小写字母、数字、短横线" />
            </el-form-item>
            <el-form-item label="管理员用户名" prop="username">
              <el-input v-model="registerForm.username" placeholder="3-64 位字母、数字或下划线" />
            </el-form-item>
            <el-form-item label="邮箱" prop="email">
              <el-input v-model="registerForm.email" placeholder="admin@example.com" />
            </el-form-item>
            <el-form-item label="密码" prop="password">
              <el-input v-model="registerForm.password" type="password" show-password />
            </el-form-item>
            <el-button
              type="primary"
              class="login__submit"
              :loading="loading"
              @click="submitRegister"
            >
              注册并登录
            </el-button>
          </el-form>
        </el-tab-pane>
      </el-tabs>

      <p class="login__hint rag-muted">
        默认开发账号：admin / 123456（由 <code>uv run python -m scripts.seed</code> 初始化）
      </p>
    </el-card>
  </div>
</template>

<style scoped>
.login {
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #eef4ff 0%, #f7f8fa 60%, #eaf7f2 100%);
}

.login__card {
  width: 420px;
  padding: 8px 12px 16px;
}

.login__brand {
  text-align: center;
  margin-bottom: 8px;
}

.login__brand h1 {
  font-size: 22px;
  margin: 0 0 4px;
}

.login__brand p {
  margin: 0 0 8px;
}

.login__submit {
  width: 100%;
  margin-top: 4px;
}

.login__hint {
  margin: 16px 0 0;
  text-align: center;
  font-size: 12px;
}
</style>
