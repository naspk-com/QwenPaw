<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'

const APP_NAME = 'com.dustinky.qwenpaw'
const API_BASE = '/cgi/ThirdParty/com.dustinky.qwenpaw/api.cgi'

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

const tunnelInstalled = ref<boolean | null>(null)
const isCheckingInstall = ref(false)

const getDefaultService = (): string => {
  if (typeof window !== 'undefined') {
    const hostname = window.location.hostname
    return `http://${hostname}:19091`
  }
  return 'http://localhost:19091'
}

const checkTunnelInstalled = async () => {
  isCheckingInstall.value = true
  try {
    const res = await fetch(`${API_BASE}?action=check_tunnel`)
    const result = await res.json()
    if (result.success) {
      tunnelInstalled.value = result.installed
    } else {
      tunnelInstalled.value = false
    }
  } catch {
    tunnelInstalled.value = false
  } finally {
    isCheckingInstall.value = false
  }
}

const refreshInstallStatus = () => {
  checkTunnelInstalled()
}

// Tunnel 状态
interface TunnelStatus {
  success: boolean
  status: string
  running: boolean
  pid: string
  arch: string
  startAt: number
  tunnelId: string
  cfConfigured?: boolean
}

const tunnelStatus = ref<TunnelStatus | null>(null)
const isLoadingTunnel = ref(false)

// 域名注册状态
interface DomainStatus {
  success: boolean
  registered: boolean
  appName: string
  domain: string
  service: string
  dnsValid: boolean
  ingressValid: boolean
  tunnelRunning: boolean
  cfConfigured: boolean
  message: string
}

const domainStatus = ref<DomainStatus | null>(null)
const isLoadingDomain = ref(false)

// 域名注册表单
const domain = ref('')
const service = ref(getDefaultService())
const isRegistering = ref(false)

const tunnelStatusText = computed(() => {
  if (!tunnelStatus.value) return '未知'
  if (!tunnelStatus.value.running) return '未运行'
  return tunnelStatus.value.status === 'healthy' ? '运行中' : '异常'
})

const tunnelStatusColor = computed(() => {
  if (!tunnelStatus.value) return 'neutral'
  if (!tunnelStatus.value.running) return 'neutral'
  return tunnelStatus.value.status === 'healthy' ? 'success' : 'warning'
})

const tunnelStatusIcon = computed(() => {
  if (!tunnelStatus.value) return 'i-lucide-help-circle'
  if (!tunnelStatus.value.running) return 'i-lucide-stop-circle'
  return tunnelStatus.value.status === 'healthy' ? 'i-lucide-activity' : 'i-lucide-alert-triangle'
})

const domainStatusText = computed(() => {
  if (!domainStatus.value) return '未知'
  if (!domainStatus.value.registered) return '未注册'
  return domainStatus.value.dnsValid && domainStatus.value.ingressValid ? '已生效' : '异常'
})

const domainStatusColor = computed(() => {
  if (!domainStatus.value) return 'neutral'
  if (!domainStatus.value.registered) return 'neutral'
  return domainStatus.value.dnsValid && domainStatus.value.ingressValid ? 'success' : 'warning'
})

const domainStatusIcon = computed(() => {
  if (!domainStatus.value) return 'i-lucide-help-circle'
  if (!domainStatus.value.registered) return 'i-lucide-minus-circle'
  return domainStatus.value.dnsValid && domainStatus.value.ingressValid ? 'i-lucide-check-circle' : 'i-lucide-alert-triangle'
})

const TUNNEL_API_BASE = '/cgi/ThirdParty/com.dustinky.tunnel/api.cgi'

const fetchTunnelStatus = async () => {
  if (!tunnelInstalled.value) return
  
  isLoadingTunnel.value = true
  try {
    const res = await fetch(`${TUNNEL_API_BASE}?action=status`)
    const result = await res.json()
    if (result.success) {
      tunnelStatus.value = result
    } else {
      showNotification('获取 Tunnel 状态失败: ' + (result.message || '未知错误'), 'error')
    }
  } catch (e: unknown) {
    const err = e as Error
    showNotification('获取 Tunnel 状态出错: ' + (err?.message ?? String(e)), 'error')
  } finally {
    isLoadingTunnel.value = false
  }
}

const fetchDomainStatus = async () => {
  if (!tunnelInstalled.value) return
  
  isLoadingDomain.value = true
  try {
    const res = await fetch(`${TUNNEL_API_BASE}?action=get_app_domain_status&appName=${APP_NAME}`)
    const result = await res.json()
    if (result.success) {
      domainStatus.value = result
      if (result.registered && result.domain) {
        domain.value = result.domain
      }
      if (result.registered && result.service) {
        service.value = result.service
      }
    } else {
      showNotification('获取域名状态失败: ' + (result.message || '未知错误'), 'error')
    }
  } catch (e: unknown) {
    const err = e as Error
    showNotification('获取域名状态出错: ' + (err?.message ?? String(e)), 'error')
  } finally {
    isLoadingDomain.value = false
  }
}

const registerDomain = async () => {
  if (!tunnelInstalled.value) {
    showNotification('请先安装 Cloudflare Tunnel 应用', 'warning')
    return
  }
  
  if (!domain.value.trim()) {
    showNotification('请输入域名', 'warning')
    return
  }
  if (!service.value.trim()) {
    showNotification('请输入本地服务地址', 'warning')
    return
  }
  if (service.value.toLowerCase().startsWith('https://')) {
    showNotification('本地服务地址请使用 http 协议，不要使用 https', 'warning')
    return
  }

  isRegistering.value = true
  try {
    const res = await fetch(`${TUNNEL_API_BASE}?action=register_app_domain`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        appName: APP_NAME,
        domain: domain.value.trim(),
        service: service.value.trim(),
      }),
    })
    const result = await res.json()
    if (result.success) {
      showNotification('域名注册成功', 'success')
      await fetchDomainStatus()
    } else {
      showNotification('域名注册失败: ' + (result.message || '未知错误'), 'error')
    }
  } catch (e: unknown) {
    const err = e as Error
    showNotification('域名注册出错: ' + (err?.message ?? String(e)), 'error')
  } finally {
    isRegistering.value = false
  }
}

const refreshAll = async () => {
  if (!tunnelInstalled.value) {
    await checkTunnelInstalled()
    if (!tunnelInstalled.value) {
      showNotification('Cloudflare Tunnel 未安装', 'warning')
      return
    }
  }
  await Promise.all([fetchTunnelStatus(), fetchDomainStatus()])
  showNotification('已刷新', 'success')
}

onMounted(async () => {
  await checkTunnelInstalled()
  if (tunnelInstalled.value) {
    await refreshAll()
  }
})
</script>

<template>
  <div class="mx-auto space-y-6">
    <!-- 加载中 -->
    <div v-if="isCheckingInstall" class="flex flex-col items-center justify-center py-20">
      <UIcon name="i-lucide-loader" class="w-10 h-10 animate-spin text-[var(--ui-text-muted)]" />
      <p class="mt-4 text-[var(--ui-text-muted)]">检查 Cloudflare Tunnel 应用...</p>
    </div>

    <!-- 未安装引导页面 -->
    <div v-else-if="tunnelInstalled === false" class="flex flex-col items-center justify-center py-20">
      <div class="w-24 h-24 rounded-full bg-amber-100 dark:bg-amber-500/20 flex items-center justify-center mb-6">
        <UIcon name="i-lucide-cloud-off" class="w-12 h-12 text-amber-500" />
      </div>
      <h2 class="text-2xl font-bold text-[var(--ui-text)] mb-3">
        Cloudflare Tunnel 未安装
      </h2>
      <p class="text-[var(--ui-text-muted)] text-center max-w-md mb-8">
        要使用外网访问功能，您需要先在飞牛应用商店安装 Cloudflare Tunnel 应用。
        安装后，QwenPaw 可以通过 Cloudflare Tunnel 将服务暴露到公网。
      </p>
      
      <UCard class="w-full max-w-lg bg-[var(--ui-bg-card)] shadow-sm mb-6">
        <div class="p-6">
          <h3 class="text-lg font-semibold text-[var(--ui-text)] mb-4">
            <UIcon name="i-lucide-list" class="w-5 h-5 inline-block mr-2" />
            安装步骤
          </h3>
          <ol class="space-y-4">
            <li class="flex items-start gap-3">
              <span class="flex-shrink-0 w-6 h-6 rounded-full bg-blue-100 dark:bg-blue-500/20 text-blue-600 dark:text-blue-400 flex items-center justify-center text-sm font-medium">1</span>
              <div>
                <p class="text-[var(--ui-text)]">打开飞牛应用商店</p>
                <p class="text-sm text-[var(--ui-text-muted)]">在应用中心搜索 "Cloudflare Tunnel"</p>
              </div>
            </li>
            <li class="flex items-start gap-3">
              <span class="flex-shrink-0 w-6 h-6 rounded-full bg-blue-100 dark:bg-blue-500/20 text-blue-600 dark:text-blue-400 flex items-center justify-center text-sm font-medium">2</span>
              <div>
                <p class="text-[var(--ui-text)]">安装 Cloudflare Tunnel 应用</p>
                <p class="text-sm text-[var(--ui-text-muted)]">点击安装按钮，等待应用安装完成</p>
              </div>
            </li>
            <li class="flex items-start gap-3">
              <span class="flex-shrink-0 w-6 h-6 rounded-full bg-blue-100 dark:bg-blue-500/20 text-blue-600 dark:text-blue-400 flex items-center justify-center text-sm font-medium">3</span>
              <div>
                <p class="text-[var(--ui-text)]">配置 Cloudflare 账号</p>
                <p class="text-sm text-[var(--ui-text-muted)]">安装完成后，按照应用指引配置您的 Cloudflare 账号</p>
              </div>
            </li>
            <li class="flex items-start gap-3">
              <span class="flex-shrink-0 w-6 h-6 rounded-full bg-blue-100 dark:bg-blue-500/20 text-blue-600 dark:text-blue-400 flex items-center justify-center text-sm font-medium">4</span>
              <div>
                <p class="text-[var(--ui-text)]">返回此页面</p>
                <p class="text-sm text-[var(--ui-text-muted)]">配置完成后，点击下方按钮刷新状态</p>
              </div>
            </li>
          </ol>
        </div>
      </UCard>

      <UButton color="primary" size="lg" @click="refreshInstallStatus">
        <UIcon name="i-lucide-refresh-cw" class="w-4 h-4 mr-2" />
        我已安装，刷新状态
      </UButton>
    </div>

    <!-- 已安装的正常页面 -->
    <template v-else-if="tunnelInstalled === true">
      <div class="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
        <div>
          <h1 class="text-3xl font-bold text-[var(--ui-text)]">
            外网访问
          </h1>
          <p class="text-[var(--ui-text-muted)] mt-2">
            通过 Cloudflare Tunnel 将 QwenPaw 暴露到公网，实现外网域名访问
          </p>
        </div>
        <UButton
          icon="i-lucide-refresh-cw"
          variant="outline"
          @click="refreshAll"
        >
          刷新
        </UButton>
      </div>

    <!-- Tunnel 状态卡片 -->
    <UCard
      class="bg-[var(--ui-bg-card)] shadow-sm"
      :ui="{ root: 'ring-0 divide-y-0', body: 'p-6' }"
    >
      <div class="flex items-center gap-4 mb-4">
        <UIcon :name="tunnelStatusIcon" class="w-6 h-6" :class="{
          'text-emerald-500': tunnelStatusColor === 'success',
          'text-amber-500': tunnelStatusColor === 'warning',
          'text-gray-400': tunnelStatusColor === 'neutral',
        }" />
        <h2 class="text-lg font-semibold text-[var(--ui-text)]">Cloudflare Tunnel 状态</h2>
        <UBadge :color="tunnelStatusColor" variant="subtle" size="sm">
          {{ tunnelStatusText }}
        </UBadge>
      </div>

      <div v-if="isLoadingTunnel" class="text-center py-8 text-[var(--ui-text-muted)]">
        <UIcon name="i-lucide-loader" class="w-5 h-5 animate-spin inline-block mr-2" />
        加载中...
      </div>

      <div v-else-if="tunnelStatus" class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <div class="p-3 rounded-lg bg-[var(--ui-bg-elevated)]">
          <div class="text-xs text-[var(--ui-text-muted)] mb-1">Tunnel ID</div>
          <div class="text-sm font-mono text-[var(--ui-text)] truncate" :title="tunnelStatus.tunnelId">
            {{ tunnelStatus.tunnelId ? tunnelStatus.tunnelId.slice(0, 16) + '...' : '-' }}
          </div>
        </div>
        <div class="p-3 rounded-lg bg-[var(--ui-bg-elevated)]">
          <div class="text-xs text-[var(--ui-text-muted)] mb-1">架构</div>
          <div class="text-sm text-[var(--ui-text)]">{{ tunnelStatus.arch || '-' }}</div>
        </div>
        <div class="p-3 rounded-lg bg-[var(--ui-bg-elevated)]">
          <div class="text-xs text-[var(--ui-text-muted)] mb-1">进程 PID</div>
          <div class="text-sm text-[var(--ui-text)]">{{ tunnelStatus.pid || '-' }}</div>
        </div>
        <div class="p-3 rounded-lg bg-[var(--ui-bg-elevated)]">
          <div class="text-xs text-[var(--ui-text-muted)] mb-1">健康状态</div>
          <div class="text-sm text-[var(--ui-text)]">{{ tunnelStatus.status || '-' }}</div>
        </div>
      </div>

      <div v-else class="text-center py-8 text-[var(--ui-text-muted)]">
        <p>无法获取 Tunnel 状态，请确认 Cloudflare Tunnel 应用已安装</p>
      </div>
    </UCard>

    <!-- 域名注册状态卡片 -->
    <UCard
      class="bg-[var(--ui-bg-card)] shadow-sm"
      :ui="{ root: 'ring-0 divide-y-0', body: 'p-6' }"
    >
      <div class="flex items-center gap-4 mb-4">
        <UIcon :name="domainStatusIcon" class="w-6 h-6" :class="{
          'text-emerald-500': domainStatusColor === 'success',
          'text-amber-500': domainStatusColor === 'warning',
          'text-gray-400': domainStatusColor === 'neutral',
        }" />
        <h2 class="text-lg font-semibold text-[var(--ui-text)]">域名注册状态</h2>
        <UBadge :color="domainStatusColor" variant="subtle" size="sm">
          {{ domainStatusText }}
        </UBadge>
      </div>

      <div v-if="isLoadingDomain" class="text-center py-8 text-[var(--ui-text-muted)]">
        <UIcon name="i-lucide-loader" class="w-5 h-5 animate-spin inline-block mr-2" />
        加载中...
      </div>

      <div v-else-if="domainStatus && domainStatus.registered" class="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <div class="p-3 rounded-lg bg-[var(--ui-bg-elevated)]">
          <div class="text-xs text-[var(--ui-text-muted)] mb-1">注册域名</div>
          <div class="text-sm font-mono text-[var(--ui-text)]">{{ domainStatus.domain }}</div>
        </div>
        <div class="p-3 rounded-lg bg-[var(--ui-bg-elevated)]">
          <div class="text-xs text-[var(--ui-text-muted)] mb-1">本地服务</div>
          <div class="text-sm font-mono text-[var(--ui-text)]">{{ domainStatus.service }}</div>
        </div>
        <div class="p-3 rounded-lg bg-[var(--ui-bg-elevated)]">
          <div class="text-xs text-[var(--ui-text-muted)] mb-1">DNS 记录</div>
          <UBadge :color="domainStatus.dnsValid ? 'success' : 'error'" variant="subtle" size="xs">
            {{ domainStatus.dnsValid ? '有效' : '无效' }}
          </UBadge>
        </div>
        <div class="p-3 rounded-lg bg-[var(--ui-bg-elevated)]">
          <div class="text-xs text-[var(--ui-text-muted)] mb-1">Ingress 规则</div>
          <UBadge :color="domainStatus.ingressValid ? 'success' : 'error'" variant="subtle" size="xs">
            {{ domainStatus.ingressValid ? '有效' : '无效' }}
          </UBadge>
        </div>
      </div>

      <div v-else-if="domainStatus && !domainStatus.registered" class="text-center py-6 text-[var(--ui-text-muted)]">
        <p>{{ domainStatus.message || '该应用未注册域名' }}</p>
      </div>
    </UCard>

    <!-- 域名注册表单 -->
    <UCard
      class="bg-[var(--ui-bg-card)] shadow-sm"
      :ui="{ root: 'ring-0 divide-y-0', body: 'p-6' }"
    >
      <div class="flex items-center gap-4 mb-6">
        <UIcon name="i-lucide-globe" class="w-6 h-6 text-[var(--ui-text-muted)]" />
        <h2 class="text-lg font-semibold text-[var(--ui-text)]">
          {{ domainStatus?.registered ? '更新域名配置' : '注册域名' }}
        </h2>
      </div>

      <div class="space-y-4 max-w-lg">
        <UFormField label="应用标识">
          <UInput
            :model-value="APP_NAME"
            disabled
            class="w-full"
          />
          <p class="text-xs text-[var(--ui-text-muted)] mt-1">
            应用的唯一标识，用于索引域名配置
          </p>
        </UFormField>

        <UFormField label="域名" required>
          <UInput
            v-model="domain"
            placeholder="例如: qwenpaw.example.com"
            class="w-full"
          />
          <p class="text-xs text-[var(--ui-text-muted)] mt-1">
            需要已添加到 Cloudflare 的完整域名
          </p>
        </UFormField>

        <UFormField label="本地服务地址" required>
          <UInput
            v-model="service"
            :placeholder="getDefaultService()"
            class="w-full"
          />
          <p class="text-xs text-[var(--ui-text-muted)] mt-1">
            QwenPaw 服务的本地访问地址
          </p>
          <div
            v-if="service.toLowerCase().startsWith('https://')"
            class="mt-2 p-2 rounded-lg bg-red-50 dark:bg-red-500/10 text-xs text-red-600 dark:text-red-400"
          >
            <UIcon name="i-lucide-alert-circle" class="w-3 h-3 inline-block mr-1" />
            本地服务地址请使用 http 协议，不要使用 https
          </div>
        </UFormField>

        <UButton
          :loading="isRegistering"
          :disabled="!tunnelStatus?.running || !domainStatus?.cfConfigured"
          color="primary"
          @click="registerDomain"
        >
          {{ domainStatus?.registered ? '更新域名' : '注册域名' }}
        </UButton>

        <div
          v-if="!tunnelStatus?.running || !domainStatus?.cfConfigured"
          class="p-3 rounded-lg bg-amber-50 dark:bg-amber-500/10 text-sm text-amber-700 dark:text-amber-400"
        >
          <UIcon name="i-lucide-alert-triangle" class="w-4 h-4 inline-block mr-1" />
          <span v-if="!tunnelStatus?.running">Tunnel 未运行，请先在 Cloudflare Tunnel 应用中启动 Tunnel</span>
          <span v-else-if="!domainStatus?.cfConfigured">Cloudflare 账号未配置，请先在 Cloudflare Tunnel 应用中完成配置</span>
        </div>
      </div>
    </UCard>
    </template>
  </div>
</template>