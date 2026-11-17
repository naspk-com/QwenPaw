<script setup lang="ts">
import { TrimApp } from '@trimjs/web-app'
import { ref } from 'vue'

const sdk = new TrimApp()
const busy = ref(false)
const resultMessage = ref('')
const resultType = ref<'success' | 'warning' | 'error'>('warning')

const chooseFolder = async () => {
  resultMessage.value = ''
  busy.value = true
  try {
    await sdk.ready()
    if (sdk.isStandaloneWeb) {
      resultType.value = 'warning'
      resultMessage.value = '请从飞牛桌面打开 QwenPaw 控制台，或前往应用设置中的授权路径管理目录。'
      return
    }
    const result = await sdk.pickSharedFile({
      title: '选择 QwenPaw 可访问的目录',
      okText: '确认授权',
      sidebarGroup: ['myFiles', 'otherShare', 'favorites'],
    })
    if (!result) {
      resultType.value = 'warning'
      resultMessage.value = '未收到授权结果，请在应用设置中检查授权路径。'
    } else if (result.code !== 0) {
      resultType.value = 'error'
      resultMessage.value = result.msg || '授权未完成，请确认当前用户为管理员。'
    } else if (result.data?.length) {
      resultType.value = 'success'
      resultMessage.value = '目录授权已完成。可以在应用设置中查看或撤销授权。'
    } else {
      resultType.value = 'warning'
      resultMessage.value = '未选择目录，现有授权未改变。'
    }
  } catch (error) {
    resultType.value = 'error'
    resultMessage.value = error instanceof Error ? error.message : '无法打开授权选择器，请在应用设置中管理授权路径。'
  } finally {
    busy.value = false
  }
}

const openSettings = async () => {
  try {
    await sdk.ready()
    if (sdk.isStandaloneWeb) {
      resultType.value = 'warning'
      resultMessage.value = '请在飞牛应用中心打开 QwenPaw 的设置，然后选择授权路径。'
      return
    }
    await sdk.openAppSetting()
  } catch {
    resultType.value = 'error'
    resultMessage.value = '无法打开应用设置，请从飞牛应用中心进入。'
  }
}
</script>

<template>
  <div class="mx-auto max-w-5xl space-y-6">
    <div>
      <h1 class="text-3xl font-bold text-[var(--ui-text)]">目录授权</h1>
      <p class="mt-2 text-[var(--ui-text-muted)]">选择 QwenPaw 可以访问的 NAS 目录。</p>
    </div>

    <UCard class="bg-[var(--ui-bg-card)] shadow-sm" :ui="{ root: 'ring-0 divide-y-0' }">
      <div class="flex flex-col gap-5 sm:flex-row sm:items-start sm:justify-between">
        <div class="flex items-start gap-4">
          <div class="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl bg-primary/10 text-primary">
            <UIcon name="i-lucide-folder-key" class="h-6 w-6" />
          </div>
          <div class="space-y-2">
            <h2 class="text-lg font-semibold text-[var(--ui-text)]">共享目录</h2>
            <p class="max-w-xl text-sm leading-6 text-[var(--ui-text-muted)]">
              由飞牛管理员选择并授权目录。授权后，QwenPaw 可能通过文件工具、插件或命令访问其中的内容。
            </p>
          </div>
        </div>
        <UButton class="shrink-0 whitespace-nowrap" icon="i-lucide-folder-plus" :loading="busy" @click="chooseFolder">
          授权目录
        </UButton>
      </div>
      <UAlert
        v-if="resultMessage"
        class="mt-5"
        :color="resultType"
        variant="subtle"
        :title="resultMessage"
      />
    </UCard>

    <div class="grid gap-6 md:grid-cols-2">
      <UCard class="bg-[var(--ui-bg-card)] shadow-sm" :ui="{ root: 'ring-0 divide-y-0' }">
        <div class="space-y-3">
          <h2 class="flex items-center gap-2 font-semibold text-[var(--ui-text)]">
            <UIcon name="i-lucide-settings-2" class="h-5 w-5 text-primary" />
            管理已有授权
          </h2>
          <p class="text-sm leading-6 text-[var(--ui-text-muted)]">
            在飞牛应用设置中查看或撤销已授权目录。撤销授权不会删除目录或文件。
          </p>
          <UButton color="neutral" variant="outline" icon="i-lucide-external-link" @click="openSettings">
            打开应用设置
          </UButton>
        </div>
      </UCard>

      <UCard class="bg-[var(--ui-bg-card)] shadow-sm" :ui="{ root: 'ring-0 divide-y-0' }">
        <div class="space-y-3">
          <h2 class="flex items-center gap-2 font-semibold text-[var(--ui-text)]">
            <UIcon name="i-lucide-shield-alert" class="h-5 w-5 text-warning" />
            使用前请注意
          </h2>
          <p class="text-sm leading-6 text-[var(--ui-text-muted)]">
            目录授权面向整个应用，不区分 QwenPaw 用户。只授权需要的目录，并留意文件内容可能被发送给所用模型或聊天频道。
          </p>
        </div>
      </UCard>
    </div>
  </div>
</template>
