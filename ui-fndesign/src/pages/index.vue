<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'

interface QwenPawInfo {
  pid?: string
  startAt?: number | null
  running?: boolean
  version?: string
  authEnabled?: boolean
  authConfigured?: boolean | null
  port?: number | null
  workingDir?: string
  workingDirDisplay?: string | null
}
const qwenpawInfo = ref<QwenPawInfo | null>(null)
const running = ref(false)
const statusAvailable = ref(false)
const now = ref(Date.now())
const version = ref('')
let runtimeTimer: number | undefined
let statusTimer: number | undefined

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

const statusText = computed(() => !statusAvailable.value ? '状态未知' : running.value ? '运行中' : '已停止')
const statusDescription = computed(() => !statusAvailable.value ? '无法获取服务状态，请检查连接' : running.value ? 'QwenPaw 服务进程正在运行' : 'QwenPaw 服务未运行')
const statusIcon = computed(() => !statusAvailable.value ? 'i-lucide-circle-help' : running.value ? 'i-lucide-activity' : 'i-lucide-stop-circle')
const statusColor = computed(() => !statusAvailable.value ? 'warning' : running.value ? 'success' : 'neutral')

const authText = computed(() => {
  if (!statusAvailable.value || qwenpawInfo.value?.authEnabled == null) return '未知'
  if (!qwenpawInfo.value.authEnabled) return '未启用'
  if (qwenpawInfo.value.authConfigured === false) return '已启用，待设置账号'
  if (qwenpawInfo.value.authConfigured === true) return '已启用，账号已设置'
  return '已启用，账号状态未知'
})

const workingDir = computed(() => statusAvailable.value ? qwenpawInfo.value?.workingDir || '' : '')
const workingDirShort = computed(() => {
  const path = workingDir.value
  if (!path) return '-'
  if (qwenpawInfo.value?.workingDirDisplay) return qwenpawInfo.value.workingDirDisplay
  const parts = path.split('/').filter(Boolean)
  return parts.length > 2 ? `…/${parts.slice(-2).join('/')}` : path
})

const copyWorkingDir = async () => {
  try {
    if (!workingDir.value || !navigator.clipboard?.writeText) throw new Error('clipboard unavailable')
    await navigator.clipboard.writeText(workingDir.value)
    showNotification('完整路径已复制', 'success')
  } catch {
    showNotification('无法自动复制，请选择完整路径后手动复制', 'warning')
  }
}

const runtimeText = computed(() => {
  const startAt = qwenpawInfo.value?.startAt
  if (!running.value || typeof startAt !== 'number' || !Number.isFinite(startAt) || startAt <= 0) {
    return '-'
  }
  const seconds = Math.max(0, Math.floor(now.value / 1000 - startAt))
  const pad2 = (n: number) => String(n).padStart(2, '0')
  const days = Math.floor(seconds / 86400)
  const hours = Math.floor((seconds % 86400) / 3600)
  const minutes = Math.floor((seconds % 3600) / 60)
  const secs = seconds % 60
  const time = `${pad2(hours)}:${pad2(minutes)}:${pad2(secs)}`
  return days > 0 ? `${days}天 ${time}` : time
})

const qwenpawUrl = computed(() => {
  if (typeof window !== 'undefined') {
    const url = new URL(window.location.href)
    url.protocol = 'http:'
    url.port = String(qwenpawInfo.value?.port || 19091)
    url.pathname = '/'
    url.search = ''
    url.hash = ''
    return url.toString()
  }
  return 'http://localhost:19091'
})

const isRestarting = ref(false)
const isUpgrading = ref(false)
const isResetting = ref(false)
const showResetConfirm = ref(false)

const restartService = async () => {
  isRestarting.value = true
  try {
    const res = await fetch('/cgi/ThirdParty/com.dustinky.qwenpaw/api.cgi?action=restart', { method: 'POST' })
    const result = await res.json()
    if (result.success) {
      showNotification('QwenPaw 重启成功', 'success')
      refreshStatus()
    } else {
      showNotification('重启失败: ' + (result.message || '未知错误'), 'error')
    }
  } catch (e: unknown) {
    const err = e as Error
    showNotification('重启出错: ' + (err?.message ?? String(e)), 'error')
  } finally {
    isRestarting.value = false
  }
}

const resetAuth = async () => {
    isResetting.value = true
    try {
      const res = await fetch('/cgi/ThirdParty/com.dustinky.qwenpaw/api.cgi?action=reset_auth', { method: 'POST' })
      const result = await res.json()
      if (result.success) {
        showNotification(result.message || '密码已重置', 'success')
      } else {
        showNotification('重置失败: ' + (result.message || '未知错误'), 'error')
      }
    } catch (e: unknown) {
      const err = e as Error
      showNotification('重置出错: ' + (err?.message ?? String(e)), 'error')
    } finally {
      isResetting.value = false
      showResetConfirm.value = false
    }
  }

const showUpgradeModal = ref(false)
const upgradeLogs = ref<{ message: string }[]>([])
let upgradePollTimer: number | null = null
const showUpgradeOptions = ref(false)
const selectedMirror = ref('tsinghua')
const showDisclaimer = ref(false)
const showBackupPrompt = ref(false)
const isBackingUp = ref(false)

const mirrorOptions = [
  { label: 'PyPI 官方源', value: 'official' },
  { label: '清华大学镜像源', value: 'tsinghua' },
  { label: '阿里云镜像源', value: 'aliyun' },
  { label: '中科大镜像源', value: 'ustc' }
]

const startUpgrade = async (mirror?: string) => {
  isUpgrading.value = true
  upgradeLogs.value = []
  showUpgradeModal.value = true
  try {
    const mirrorParam = mirror ? `&mirror=${mirror}` : ''
    const res = await fetch(`/cgi/ThirdParty/com.dustinky.qwenpaw/api.cgi?action=upgrade${mirrorParam}`, { method: 'POST' })
    const result = await res.json()
    if (!result.success) {
      showNotification('升级启动失败: ' + (result.message || '未知错误'), 'error')
      showUpgradeModal.value = false
      isUpgrading.value = false
      return
    }
    upgradePollTimer = window.setInterval(async () => {
      await pollUpgradeStatus()
    }, 2000)
  } catch (e: unknown) {
    const err = e as Error
    showNotification('升级出错: ' + (err?.message ?? String(e)), 'error')
    showUpgradeModal.value = false
    isUpgrading.value = false
  }
}

const pollUpgradeStatus = async () => {
  try {
    const [statusRes, logsRes] = await Promise.all([
      fetch('/cgi/ThirdParty/com.dustinky.qwenpaw/api.cgi?action=upgrade_status'),
      fetch('/cgi/ThirdParty/com.dustinky.qwenpaw/api.cgi?action=upgrade_logs')
    ])
    const statusData = await statusRes.json()
    const logsData = await logsRes.json()

    if (logsData?.logs) {
      upgradeLogs.value = logsData.logs
    }

    if (!statusData?.upgrading) {
      if (upgradePollTimer) {
        window.clearInterval(upgradePollTimer)
        upgradePollTimer = null
      }
      isUpgrading.value = false

      const logMessages = upgradeLogs.value.map(l => l.message).join('\n')
      if (logMessages.includes('升级失败')) {
        showNotification('升级失败，请查看日志详情', 'error')
      } else if (logMessages.includes('升级成功')) {
        showNotification('升级完成', 'success')
      } else {
        showNotification('升级已结束', 'warning')
      }
      refreshStatus()
    }
  } catch {}
}

const closeUpgradeModal = () => {
  showUpgradeModal.value = false
  if (upgradePollTimer) {
    window.clearInterval(upgradePollTimer)
    upgradePollTimer = null
  }
}

const confirmUpgrade = () => {
  showUpgradeOptions.value = false
  const mirror = selectedMirror.value === 'official' ? '' : selectedMirror.value
  startUpgrade(mirror)
}

const confirmDisclaimer = () => {
  showDisclaimer.value = false
  showBackupPrompt.value = true
}

const backupAndProceed = async () => {
  isBackingUp.value = true
  try {
    const res = await fetch('/cgi/ThirdParty/com.dustinky.qwenpaw/api.cgi?action=backup_download')
    const contentType = res.headers.get('content-type') || ''
    if (contentType.includes('application/json')) {
      const result = await res.json()
      showNotification(result.message || '备份失败', 'error')
      return
    }
    const blob = await res.blob()
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    const disposition = res.headers.get('content-disposition') || ''
    const filenameMatch = disposition.match(/filename="?(.+?)"?$/)
    a.download = filenameMatch?.[1] || 'qwenpaw-backup.tar.gz'
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
    showNotification('数据备份下载成功', 'success')
    showBackupPrompt.value = false
    showUpgradeOptions.value = true
  } catch (e: unknown) {
    const err = e as Error
    showNotification('备份下载出错: ' + (err?.message ?? String(e)), 'error')
  } finally {
    isBackingUp.value = false
  }
}

const skipBackup = () => {
  showBackupPrompt.value = false
  showUpgradeOptions.value = true
}

const upgradeLogContainer = ref<HTMLElement | null>(null)
watch(upgradeLogs, () => {
  setTimeout(() => {
    if (upgradeLogContainer.value) {
      upgradeLogContainer.value.scrollTop = upgradeLogContainer.value.scrollHeight
    }
  }, 100)
})

const refreshStatus = async () => {
  try {
    const res = await fetch('/cgi/ThirdParty/com.dustinky.qwenpaw/api.cgi?action=status')
    const result = await res.json()
    if (result.success) {
      qwenpawInfo.value = result
      statusAvailable.value = true
      running.value = result.running || false
      version.value = result.version || ''
    } else {
      statusAvailable.value = false
      running.value = false
    }
  } catch {
    statusAvailable.value = false
    running.value = false
  }
}

onMounted(() => {
  refreshStatus()
  runtimeTimer = window.setInterval(() => {
    now.value = Date.now()
  }, 1000)
  statusTimer = window.setInterval(refreshStatus, 15000)
})

onUnmounted(() => {
  if (runtimeTimer) window.clearInterval(runtimeTimer)
  if (statusTimer) window.clearInterval(statusTimer)
  if (upgradePollTimer) window.clearInterval(upgradePollTimer)
})
</script>

<template>
  <div class="mx-auto space-y-6">
    <div class="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
      <div>
        <h1 class="text-3xl font-bold text-[var(--ui-text)]">
          QwenPaw 控制台
        </h1>
        <p class="text-[var(--ui-text-muted)] mt-2">
          管理 QwenPaw 服务的运行状态与版本升级
        </p>
      </div>
    </div>

    <UCard
      class="bg-[var(--ui-bg-card)] shadow-sm"
      :ui="{ root: 'ring-0 divide-y-0', body: 'p-6' }"
    >
      <div class="flex flex-col md:flex-row gap-6 items-start md:items-center justify-between">
        <div class="flex items-center gap-5">
          <div class="relative">
            <div
              class="w-16 h-16 rounded-2xl flex items-center justify-center transition-all duration-500 shadow-sm ring-1 ring-inset"
              :class="running
                ? 'bg-emerald-50 text-emerald-600 ring-emerald-200 dark:bg-emerald-500/10 dark:text-emerald-400 dark:ring-emerald-500/20'
                : 'bg-slate-50 text-slate-500 ring-slate-200 dark:bg-slate-500/10 dark:text-slate-400 dark:ring-slate-500/20'"
            >
              <UIcon
                :name="statusIcon"
                class="w-8 h-8 transition-transform duration-500"
                :class="running ? 'scale-110' : 'scale-100'"
              />
            </div>
            <div
              class="absolute -top-1 -right-1 w-4 h-4 rounded-full border-2 border-[var(--ui-bg-card)] flex items-center justify-center"
              :class="running ? 'bg-emerald-500' : 'bg-slate-400'"
            >
              <div
                v-if="running"
                class="w-full h-full rounded-full bg-emerald-500 animate-ping opacity-75 absolute"
              />
            </div>
          </div>

          <div>
            <div class="flex items-center gap-3 mb-1.5">
              <h2 class="text-2xl font-bold text-[var(--ui-text)] tracking-tight">
                {{ statusText }}
              </h2>
              <UBadge
                :color="statusColor"
                variant="soft"
                size="md"
                class="px-2 py-0.5"
              >
                {{ statusText }}
              </UBadge>
            </div>
            <p class="text-[var(--ui-text-muted)] text-base">
              {{ statusDescription }}
            </p>
          </div>
        </div>

        <div class="flex flex-wrap items-center gap-2 w-full md:w-auto">
          <UButton
            color="primary"
            variant="solid"
            icon="i-lucide-rotate-cw"
            size="lg"
            :loading="isRestarting"
            @click="restartService"
          >
            重启服务
          </UButton>
        </div>
      </div>

      <div class="grid grid-cols-1 sm:grid-cols-3 gap-4 mt-6">
        <div class="p-4 rounded-lg bg-[var(--ui-bg-elevated)]/50 ring-1 ring-transparent shadow-sm hover:ring-1 hover:ring-primary-500/50 transition-all duration-200">
          <div class="text-xs font-medium text-[var(--ui-text-muted)] uppercase tracking-wider mb-1">
            进程 ID (PID)
          </div>
          <div class="text-lg font-mono text-[var(--ui-text)]">
            {{ qwenpawInfo?.pid || '-' }}
          </div>
        </div>

        <div class="p-4 rounded-lg bg-[var(--ui-bg-elevated)]/50 ring-1 ring-transparent shadow-sm hover:ring-1 hover:ring-primary-500/50 transition-all duration-200">
          <div class="text-xs font-medium text-[var(--ui-text-muted)] uppercase tracking-wider mb-1">
            已运行
          </div>
          <div class="text-lg font-mono text-[var(--ui-text)]">
            {{ runtimeText }}
          </div>
        </div>

        <div class="p-4 rounded-lg bg-[var(--ui-bg-elevated)]/50 ring-1 ring-transparent shadow-sm hover:ring-1 hover:ring-primary-500/50 transition-all duration-200">
          <div class="text-xs font-medium text-[var(--ui-text-muted)] uppercase tracking-wider mb-1">
            当前版本
          </div>
          <div class="text-lg font-mono text-[var(--ui-text)]">
            {{ version || '-' }}
          </div>
        </div>
      </div>
    </UCard>

    <div class="grid grid-cols-1 gap-6 lg:grid-cols-[1.15fr_1fr]">
      <UCard
        class="bg-[var(--ui-bg-card)] shadow-sm"
        :ui="{ root: 'ring-0 divide-y-0', body: '!p-0 !px-6 !pb-6' }"
      >
        <template #header>
          <div>
            <div class="flex items-center gap-2">
              <UIcon name="i-lucide-zap" class="w-5 h-5 text-primary" />
              <h2 class="font-semibold text-[var(--ui-text)]">快速操作</h2>
            </div>
            <p class="mt-1 text-xs text-[var(--ui-text-muted)]">打开应用或管理常用功能</p>
          </div>
        </template>
        <div class="grid grid-cols-1 gap-2 sm:grid-cols-2">
          <UButton
            class="w-full justify-start gap-3 rounded-lg bg-primary/10 p-3 text-left sm:col-span-2"
            color="primary"
            variant="ghost"
            :to="qwenpawUrl"
            target="_blank"
            :disabled="!running"
          >
            <span class="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
              <UIcon name="i-lucide-globe" class="h-5 w-5" />
            </span>
            <span class="min-w-0 flex-1">
              <span class="block text-sm font-semibold text-[var(--ui-text)]">打开 QwenPaw</span>
              <span class="mt-0.5 block text-xs font-normal text-[var(--ui-text-muted)]">
                {{ running ? '在新窗口访问应用' : '服务运行后可打开应用' }}
              </span>
            </span>
            <UIcon name="i-lucide-external-link" class="h-4 w-4 shrink-0 text-primary" />
          </UButton>

          <UButton
            class="w-full justify-start gap-3 rounded-lg bg-[var(--ui-bg-elevated)]/50 p-3 text-left"
            color="neutral"
            variant="ghost"
            to="/logs"
          >
            <UIcon name="i-lucide-file-text" class="h-5 w-5 shrink-0 text-primary" />
            <span class="min-w-0">
              <span class="block text-sm font-medium text-[var(--ui-text)]">查看日志</span>
              <span class="mt-0.5 block text-xs font-normal text-[var(--ui-text-muted)]">运行与升级记录</span>
            </span>
          </UButton>
          <UButton
            class="w-full justify-start gap-3 rounded-lg bg-[var(--ui-bg-elevated)]/50 p-3 text-left"
            color="neutral"
            variant="ghost"
            to="/files"
          >
            <UIcon name="i-lucide-folder-key" class="h-5 w-5 shrink-0 text-primary" />
            <span class="min-w-0">
              <span class="block text-sm font-medium text-[var(--ui-text)]">目录授权</span>
              <span class="mt-0.5 block text-xs font-normal text-[var(--ui-text-muted)]">管理可访问目录</span>
            </span>
          </UButton>
          <UButton
            class="w-full justify-start gap-3 rounded-lg bg-[var(--ui-bg-elevated)]/50 p-3 text-left"
            color="neutral"
            variant="ghost"
            :loading="isUpgrading"
            @click="showDisclaimer = true"
          >
            <UIcon name="i-lucide-arrow-up-circle" class="h-5 w-5 shrink-0 text-success" />
            <span class="min-w-0">
              <span class="block text-sm font-medium text-[var(--ui-text)]">升级 QwenPaw</span>
              <span class="mt-0.5 block text-xs font-normal text-[var(--ui-text-muted)]">更新应用版本</span>
            </span>
          </UButton>
          <UButton
            class="w-full justify-start gap-3 rounded-lg bg-[var(--ui-bg-elevated)]/50 p-3 text-left"
            color="neutral"
            variant="ghost"
            @click="showResetConfirm = true"
          >
            <UIcon name="i-lucide-key-round" class="h-5 w-5 shrink-0 text-warning" />
            <span class="min-w-0">
              <span class="block text-sm font-medium text-[var(--ui-text)]">重置密码</span>
              <span class="mt-0.5 block text-xs font-normal text-[var(--ui-text-muted)]">重新设置登录账号</span>
            </span>
          </UButton>
        </div>
      </UCard>

      <UCard
        class="bg-[var(--ui-bg-card)] shadow-sm"
        :ui="{ root: 'ring-0 divide-y-0', body: '!p-0 !px-6 !pb-6' }"
      >
        <template #header>
          <div>
            <div class="flex items-center gap-2">
              <UIcon name="i-lucide-server" class="w-5 h-5 text-info" />
              <h2 class="font-semibold text-[var(--ui-text)]">服务信息</h2>
            </div>
            <p class="mt-1 text-xs text-[var(--ui-text-muted)]">查看当前服务配置</p>
          </div>
        </template>
        <div class="space-y-2">
          <div class="grid grid-cols-1 gap-2 sm:grid-cols-2">
            <div class="rounded-lg bg-[var(--ui-bg-elevated)]/50 p-3">
              <div class="flex items-center gap-2 text-xs text-[var(--ui-text-muted)]">
                <UIcon name="i-lucide-radio" class="h-4 w-4" />
                <span>服务端口</span>
              </div>
              <div class="mt-2 text-sm font-semibold text-[var(--ui-text)]">
                {{ statusAvailable ? qwenpawInfo?.port || '-' : '-' }}
              </div>
            </div>
            <div class="rounded-lg bg-[var(--ui-bg-elevated)]/50 p-3">
              <div class="flex items-center gap-2 text-xs text-[var(--ui-text-muted)]">
                <UIcon name="i-lucide-shield" class="h-4 w-4" />
                <span>认证状态</span>
              </div>
              <div class="mt-2 text-sm font-semibold text-[var(--ui-text)]">
                {{ authText }}
              </div>
            </div>
          </div>
          <div class="rounded-lg bg-[var(--ui-bg-elevated)]/50 p-3">
            <div class="flex items-center gap-2 text-xs text-[var(--ui-text-muted)]">
              <UIcon name="i-lucide-folder" class="h-4 w-4" />
              <span>工作目录</span>
            </div>
            <div class="mt-2 text-sm font-medium text-[var(--ui-text)] break-all" :title="workingDir">
              {{ workingDirShort }}
            </div>
            <details v-if="workingDir" class="mt-2">
              <summary class="cursor-pointer text-xs text-primary">查看完整路径</summary>
              <div class="mt-2 flex items-start gap-2">
                <code class="min-w-0 flex-1 select-all break-all text-xs text-[var(--ui-text-muted)]">{{ workingDir }}</code>
                <UButton
                  color="neutral"
                  variant="ghost"
                  size="xs"
                  icon="i-lucide-copy"
                  aria-label="复制完整工作目录路径"
                  @click="copyWorkingDir"
                />
              </div>
            </details>
          </div>
        </div>
      </UCard>
    </div>

    <UModal
      v-model:open="showDisclaimer"
      :dismissible="true"
      :ui="{ content: 'w-full md:w-auto md:max-w-lg' }"
    >
      <template #header>
        <div class="flex items-center gap-2">
          <UIcon
            name="i-lucide-triangle-alert"
            class="w-5 h-5 text-warning"
          />
          <div class="font-semibold text-[var(--ui-text)]">
            免责声明
          </div>
        </div>
      </template>

      <template #body>
        <div class="space-y-3 text-sm text-[var(--ui-text-muted)]">
          <p>升级 QwenPaw 操作可能会对系统产生影响，包括但不限于：</p>
          <ul class="list-disc list-inside space-y-1 ml-1">
            <li>升级过程中服务将暂时中断</li>
            <li>升级可能导致配置丢失或不兼容</li>
            <li>升级失败可能导致服务无法正常运行</li>
          </ul>
          <p class="font-medium text-[var(--ui-text)]">
            请确认您已了解相关风险。升级过程中发生的一切意外，由使用者自行承担。
          </p>
        </div>
      </template>

      <template #footer>
        <div class="flex justify-end gap-2 w-full">
          <UButton
            color="neutral"
            variant="outline"
            @click="showDisclaimer = false"
          >
            取消
          </UButton>
          <UButton
            color="success"
            icon="i-lucide-check-circle"
            @click="confirmDisclaimer"
          >
            我已知晓，继续
          </UButton>
        </div>
      </template>
    </UModal>

    <UModal
      v-model:open="showBackupPrompt"
      :dismissible="true"
      :ui="{ content: 'w-full md:w-auto md:max-w-lg' }"
    >
      <template #header>
        <div class="flex items-center gap-2">
          <UIcon
            name="i-lucide-hard-drive"
            class="w-5 h-5 text-info"
          />
          <div class="font-semibold text-[var(--ui-text)]">
            备份数据
          </div>
        </div>
      </template>

      <template #body>
        <div class="space-y-3 text-sm text-[var(--ui-text-muted)]">
          <p>升级前建议备份您的数据，以防止升级过程中出现意外导致数据丢失。</p>
          <p>备份内容包括：</p>
          <ul class="list-disc list-inside space-y-1 ml-1">
            <li>工作目录中的配置文件</li>
            <li>Agent 相关数据</li>
            <li>技能池数据</li>
          </ul>
          <p class="font-medium text-[var(--ui-text)]">
            是否现在备份数据？
          </p>
        </div>
      </template>

      <template #footer>
        <div class="flex justify-end gap-2 w-full">
          <UButton
            color="neutral"
            variant="outline"
            @click="skipBackup"
          >
            跳过备份
          </UButton>
          <UButton
            color="info"
            icon="i-lucide-download"
            :loading="isBackingUp"
            @click="backupAndProceed"
          >
            备份并下载
          </UButton>
        </div>
      </template>
    </UModal>

    <UModal
      v-model:open="showUpgradeOptions"
      :dismissible="true"
      :ui="{ content: 'w-full md:w-auto md:max-w-md' }"
    >
      <template #header>
        <div class="flex items-center gap-2">
          <UIcon
            name="i-lucide-arrow-up-circle"
            class="w-5 h-5 text-success"
          />
          <div class="font-semibold text-[var(--ui-text)]">
            升级 QwenPaw
          </div>
        </div>
      </template>

      <template #body>
        <div class="space-y-4">
          <div>
            <label class="text-sm font-medium text-[var(--ui-text)] mb-2 block">
              选择安装源
            </label>
            <USelect
              v-model="selectedMirror"
              :items="mirrorOptions"
              class="w-full"
            />
          </div>
          <p class="text-xs text-[var(--ui-text-muted)]">
            如果您的网络环境连接官方源较慢，建议选择清华源或阿里云源。
          </p>
        </div>
      </template>

      <template #footer>
        <div class="flex justify-end gap-2 w-full">
          <UButton
            color="neutral"
            variant="outline"
            @click="showUpgradeOptions = false"
          >
            取消
          </UButton>
          <UButton
            color="success"
            icon="i-lucide-arrow-up-circle"
            @click="confirmUpgrade"
          >
            开始升级
          </UButton>
        </div>
      </template>
    </UModal>

    <UModal
      v-model:open="showUpgradeModal"
      :dismissible="false"
      :ui="{ content: 'w-full md:min-w-[650px] md:max-w-4xl h-[80vh]' }"
    >
      <template #header="{ close }">
        <div class="flex items-center justify-between gap-3 w-full">
          <div class="flex items-center gap-2">
            <UIcon
              name="i-lucide-arrow-up-circle"
              class="w-5 h-5 text-success"
            />
            <div class="font-semibold text-[var(--ui-text)]">
              升级 QwenPaw
            </div>
          </div>
          <div class="flex items-center gap-2">
            <UIcon
              v-if="isUpgrading"
              name="i-lucide-loader-circle"
              class="w-5 h-5 animate-spin text-primary"
            />
            <UButton
              v-if="!isUpgrading"
              color="neutral"
              variant="ghost"
              icon="i-lucide-x"
              @click="close"
            />
          </div>
        </div>
      </template>

      <template #body>
        <div
          ref="upgradeLogContainer"
          class="h-full w-full overflow-auto bg-[var(--ui-bg-content)] rounded-md p-4"
        >
          <div v-if="upgradeLogs.length === 0" class="text-center py-10 text-sm text-[var(--ui-text-muted)]">
            <UIcon name="i-lucide-loader-circle" class="w-6 h-6 animate-spin mx-auto mb-2" />
            正在启动升级...
          </div>
          <pre
            v-else
            class="text-xs font-mono text-[var(--ui-text)] whitespace-pre-wrap break-words"
          >{{ upgradeLogs.map(l => l.message).join('\n') }}</pre>
        </div>
      </template>

      <template #footer>
        <div class="flex justify-end gap-2 w-full">
          <UButton
            v-if="!isUpgrading"
            color="primary"
            @click="closeUpgradeModal"
          >
            关闭
          </UButton>
          <span v-else class="text-sm text-[var(--ui-text-muted)] flex items-center gap-2">
            <UIcon name="i-lucide-loader-circle" class="w-4 h-4 animate-spin" />
            升级中，请稍候...
          </span>
        </div>
      </template>
    </UModal>

    <UModal
      v-model:open="showResetConfirm"
      :dismissible="true"
      :ui="{ content: 'w-full md:w-auto md:max-w-md' }"
    >
      <template #header>
        <div class="flex items-center gap-2">
          <UIcon
            name="i-lucide-triangle-alert"
            class="w-5 h-5 text-warning"
          />
          <div class="font-semibold text-[var(--ui-text)]">
            重置密码
          </div>
        </div>
      </template>

      <template #body>
        <p class="text-sm text-[var(--ui-text-muted)]">
          重置后，下次进入 QwenPaw 时将需要重新设置账号密码。确定要继续吗？
        </p>
      </template>

      <template #footer>
        <div class="flex justify-end gap-2 w-full">
          <UButton
            color="neutral"
            variant="outline"
            @click="showResetConfirm = false"
          >
            取消
          </UButton>
          <UButton
            color="warning"
            :loading="isResetting"
            @click="resetAuth"
          >
            确认重置
          </UButton>
        </div>
      </template>
    </UModal>
  </div>
</template>
