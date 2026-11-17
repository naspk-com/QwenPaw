<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'

interface LogItem {
  message: string
}

type LogSource = 'runtime' | 'upgrade' | 'install'
type LogLevel = 'all' | 'error' | 'warning' | 'info' | 'debug' | 'other'

const toast = useToast()
const showNotification = (message: string, type: 'success' | 'error' | 'warning' | 'info' = 'info') => {
  const color = type === 'error'
    ? 'error'
    : type === 'warning'
      ? 'warning'
      : type === 'success'
        ? 'success'
        : 'neutral'
  const icon = type === 'error'
    ? 'i-lucide-x-circle'
    : type === 'warning'
      ? 'i-lucide-alert-triangle'
      : type === 'success'
        ? 'i-lucide-check-circle'
        : 'i-lucide-info'
  toast.add({ title: message, color, icon })
}

const logs = ref<LogItem[]>([])
const isLoading = ref(false)
const filterText = ref('')
const source = ref<LogSource>('runtime')
const level = ref<LogLevel>('all')
const loadError = ref('')
const missing = ref(false)
const showClearConfirm = ref(false)
const isClearing = ref(false)
const sourceItems = [
  { label: '运行日志', value: 'runtime' },
  { label: '升级日志', value: 'upgrade' },
  { label: '安装日志（暂不可用）', value: 'install' }
]
const levelItems = [
  { label: '全部级别', value: 'all' },
  { label: '错误', value: 'error' },
  { label: '警告', value: 'warning' },
  { label: '信息', value: 'info' },
  { label: '调试', value: 'debug' },
  { label: '未标记级别', value: 'other' }
]

const autoRefresh = ref<boolean>(true)
let refreshTimer: number | null = null
const refreshIntervalMs = 3000
let requestId = 0
let disposed = false

const page = ref(1)
const pageSize = ref(10)
const pageSizeItems = [
  { label: '10 / 页', value: 10 },
  { label: '20 / 页', value: 20 },
  { label: '50 / 页', value: 50 },
  { label: '100 / 页', value: 100 }
]

const filteredLogs = computed(() => {
  const terms = filterText.value.toLowerCase().trim().split(/\s+/).filter(Boolean)
  return logs.value.filter((log) => {
    const message = log.message.toLowerCase()
    return terms.every(term => message.includes(term))
      && (level.value === 'all' || getLevel(log.message) === level.value)
  })
})

const getLevel = (message: string): Exclude<LogLevel, 'all'> => {
  const match = message.match(/(?:^|[\s[\]|:])(critical|fatal|error|warning|warn|info|debug)(?=$|[\s\]|:])/i)
  const value = match?.[1]?.toLowerCase()
  if (value === 'critical' || value === 'fatal' || value === 'error') return 'error'
  if (value === 'warning' || value === 'warn') return 'warning'
  if (value === 'info' || value === 'debug') return value
  return 'other'
}

const pageCount = computed(() => Math.max(1, Math.ceil(filteredLogs.value.length / pageSize.value)))
const pagedLogs = computed(() => {
  const start = (page.value - 1) * pageSize.value
  const end = start + pageSize.value
  return filteredLogs.value.slice(start, end)
})

const clampPage = () => {
  page.value = Math.min(Math.max(1, page.value), pageCount.value)
}

watch([filterText, level, pageSize], () => {
  page.value = 1
})

watch(pageCount, clampPage, { immediate: true })

const fetchLogs = async (notify = false) => {
  const currentRequest = ++requestId
  const selectedSource = source.value
  if (selectedSource === 'install') {
    logs.value = []
    isLoading.value = false
    loadError.value = ''
    missing.value = false
    return
  }
  isLoading.value = true
  loadError.value = ''
  try {
    const action = selectedSource === 'runtime' ? 'logs' : 'upgrade_logs'
    const response = await fetch(`/cgi/ThirdParty/com.dustinky.qwenpaw/api.cgi?action=${action}`)
    if (!response.ok) throw new Error(`HTTP ${response.status}`)
    const result = await response.json() as { success?: boolean; logs?: LogItem[]; message?: string; missing?: boolean }
    if (!result.success) throw new Error(result.message || '未知错误')
    if (currentRequest !== requestId || disposed) return
    logs.value = Array.isArray(result.logs) ? result.logs.filter(item => typeof item.message === 'string') : []
    missing.value = result.missing === true
    if (notify) showNotification('日志已刷新', 'success')
  } catch (err: unknown) {
    if (currentRequest !== requestId || disposed) return
    loadError.value = err instanceof Error ? err.message : String(err)
    if (notify) showNotification('获取日志失败：' + loadError.value, 'error')
  } finally {
    if (currentRequest === requestId) isLoading.value = false
  }
}

const exportLogs = () => {
  if (!filteredLogs.value.length) return
  const text = filteredLogs.value.map(log => log.message).join('\n') + '\n'
  const url = URL.createObjectURL(new Blob([text], { type: 'text/plain;charset=utf-8' }))
  const link = document.createElement('a')
  link.href = url
  link.download = `qwenpaw-${source.value}-filtered.log`
  link.click()
  window.setTimeout(() => URL.revokeObjectURL(url), 1000)
}

const clearLogs = async () => {
  isClearing.value = true
  try {
    const response = await fetch('/cgi/ThirdParty/com.dustinky.qwenpaw/api.cgi?action=clear_logs', { method: 'POST' })
    const result = await response.json() as { success?: boolean; message?: string }
    if (result?.success) {
      requestId++
      isLoading.value = false
      logs.value = []
      page.value = 1
      showNotification(result?.message || '日志已清空', 'success')
      return
    }
    showNotification('清空日志失败：' + (result?.message || '未知错误'), 'error')
  } catch (err: unknown) {
    const e = err as Error
    showNotification('清空日志失败：' + (e?.message || String(err)), 'error')
  } finally {
    isClearing.value = false
    showClearConfirm.value = false
  }
}

const scheduleRefresh = () => {
  if (refreshTimer) {
    window.clearTimeout(refreshTimer)
    refreshTimer = null
  }
  if (disposed || autoRefresh.value !== true) return

  refreshTimer = window.setTimeout(async () => {
    if (!isClearing.value) await fetchLogs()
    scheduleRefresh()
  }, refreshIntervalMs)
}

watch(autoRefresh, () => {
  scheduleRefresh()
})

watch(source, () => {
  logs.value = []
  page.value = 1
  missing.value = false
  void fetchLogs()
})

onMounted(async () => {
  await fetchLogs()
  scheduleRefresh()
})

onUnmounted(() => {
  disposed = true
  requestId++
  if (refreshTimer) window.clearTimeout(refreshTimer)
})
</script>

<template>
  <div class="mx-auto space-y-6">
    <div class="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
      <div>
        <h1 class="text-3xl font-bold text-[var(--ui-text)]">
          日志查看
        </h1>
        <p class="text-[var(--ui-text-muted)] mt-2">
          查看运行和升级日志，筛选或导出最近 500 行。
        </p>
      </div>

      <div class="flex flex-wrap gap-2 w-full md:w-auto">
        <div class="flex items-center gap-2 px-3 py-2 rounded-lg ring-1 ring-primary">
          <span class="text-sm text-[var(--ui-text-muted)]">
            自动刷新
          </span>
          <USwitch
            v-model="autoRefresh"
            aria-label="自动刷新"
          />
        </div>
        <UButton
          color="neutral"
          variant="outline"
          icon="i-lucide-rotate-cw"
          :loading="isLoading"
          @click="fetchLogs(true)"
        >
          刷新
        </UButton>
        <UButton
          color="neutral"
          variant="outline"
          icon="i-lucide-download"
          :disabled="!filteredLogs.length || !!loadError || source === 'install'"
          @click="exportLogs"
        >
          导出筛选结果
        </UButton>
        <UButton
          color="error"
          variant="soft"
          icon="i-lucide-trash-2"
          @click="showClearConfirm = true"
        >
          清空
        </UButton>
      </div>
    </div>

    <div class="flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-center">
      <USelect
        v-model="source"
        :items="sourceItems"
        aria-label="日志类型"
        class="w-full sm:w-48"
      />
      <UInput
        v-model="filterText"
        icon="i-lucide-search"
        placeholder="搜索关键词，空格分隔"
        aria-label="搜索日志"
        class="w-full sm:min-w-48 sm:flex-1"
      />
      <USelect
        v-model="level"
        :items="levelItems"
        aria-label="日志级别"
        class="w-full sm:w-40"
      />

      <div class="flex items-center gap-2 sm:ml-auto">
        <span class="text-sm text-[var(--ui-text-muted)] whitespace-nowrap">
          每页
        </span>
        <USelect
          v-model="pageSize"
          class="w-28"
          :items="pageSizeItems"
        />
      </div>
    </div>

    <p class="text-sm text-[var(--ui-text-muted)]">
      搜索同时匹配所有关键词；级别依据日志中的英文标记识别。导出仅包含当前筛选出的已加载日志，可能包含敏感信息。
    </p>

    <UAlert
      v-if="source === 'install'"
      color="warning"
      variant="soft"
      title="安装日志暂不可用"
      description="安装日志可能包含敏感信息。管理接口完成管理员身份校验后，才能安全开放查看和导出。"
      icon="i-lucide-shield-alert"
    />
    <UAlert
      v-else-if="loadError"
      color="error"
      variant="soft"
      title="日志读取失败"
      :description="loadError"
      icon="i-lucide-circle-alert"
    />

    <div
      v-else
      class="space-y-3"
    >
      <div
        v-if="pagedLogs.length === 0"
        class="py-10 text-center text-sm text-[var(--ui-text-muted)]"
      >
        {{ isLoading ? '正在读取日志...' : missing ? '日志文件尚未生成' : logs.length ? '没有符合筛选条件的日志' : '暂无日志' }}
      </div>

      <UCard
        v-for="(log, idx) in pagedLogs"
        :key="`${idx}-${log.message ?? ''}`"
        class="rounded-2xl"
        :ui="{ root: 'divide-y-0', body: 'py-3' }"
      >
        <div class="flex items-start gap-3">
          <div class="text-sm text-[var(--ui-text)] min-w-0 break-words whitespace-pre-wrap font-mono">
            {{ log.message || '-' }}
          </div>
        </div>
      </UCard>
    </div>

    <div
      v-if="filteredLogs.length > 0"
      class="flex flex-col gap-3 md:flex-row md:items-center md:justify-between"
    >
      <div class="text-sm text-[var(--ui-text-muted)]">
        匹配 {{ filteredLogs.length }} / {{ logs.length }} 行
      </div>
      <UPagination
        v-model:page="page"
        :total="filteredLogs.length"
        :items-per-page="pageSize"
        :disabled="isLoading"
        :show-edges="true"
        :sibling-count="1"
        size="sm"
      />
    </div>

    <UModal
      v-model:open="showClearConfirm"
      title="清空日志"
      description="将清空运行日志和升级日志，此操作无法撤销。"
    >
      <template #footer>
        <div class="flex w-full justify-end gap-2">
          <UButton
            color="neutral"
            variant="outline"
            @click="showClearConfirm = false"
          >
            取消
          </UButton>
          <UButton
            color="error"
            :loading="isClearing"
            @click="clearLogs"
          >
            确认清空
          </UButton>
        </div>
      </template>
    </UModal>
  </div>
</template>
