<script setup lang="ts">
import { computed, watch, ref, onMounted } from 'vue'
import { useTheme } from '@/composables/useTheme'
// @ts-expect-error qrcode 模块缺少类型声明，但功能正常
import QRCode from 'qrcode'
import bilibiliLogo from '/bilibili.jpg'
import douyinLogo from '/douyin.jpg'

const { themeMode, getSystemTheme } = useTheme()

const systemTheme = ref(getSystemTheme())
const bilibiliQrUrl = ref('')
const douyinQrUrl = ref('')
const publicBase = import.meta.env.BASE_URL

const isDark = computed(() => {
  return themeMode.value === 'system' ? systemTheme.value === 'dark' : themeMode.value === 'dark'
})

watch(isDark, (newValue) => {
  console.log('主题变化:', newValue ? '深色' : '浅色')
})

if (typeof window !== 'undefined' && window.matchMedia) {
  const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)')
  mediaQuery.addEventListener('change', () => {
    systemTheme.value = getSystemTheme()
    console.log('系统主题变化:', systemTheme.value)
  })
}

const loadImage = (src: string): Promise<HTMLImageElement> => {
  return new Promise((resolve, reject) => {
    const img = new Image()
    img.onload = () => resolve(img)
    img.onerror = reject
    img.src = src
  })
}

const drawRoundRect = (ctx: CanvasRenderingContext2D, x: number, y: number, width: number, height: number, radius: number) => {
  ctx.beginPath()
  ctx.moveTo(x + radius, y)
  ctx.lineTo(x + width - radius, y)
  ctx.quadraticCurveTo(x + width, y, x + width, y + radius)
  ctx.lineTo(x + width, y + height - radius)
  ctx.quadraticCurveTo(x + width, y + height, x + width - radius, y + height)
  ctx.lineTo(x + radius, y + height)
  ctx.quadraticCurveTo(x, y + height, x, y + height - radius)
  ctx.lineTo(x, y + radius)
  ctx.quadraticCurveTo(x, y, x + radius, y)
  ctx.closePath()
}

const generateQrCodeWithLogo = async (url: string, logoSrc: string, dark: boolean): Promise<string> => {
  const qrSize = 600
  const logoSize = qrSize * 0.25
  const borderRadius = 40
  
  const qrDataUrl = await QRCode.toDataURL(url, {
    width: qrSize,
    margin: 0,
    color: {
      dark: dark ? '#ffffff' : '#0C0C0D',
      light: dark ? '#0C0C0D' : '#F2F3F4'
    }
  })
  
  const qrImg = await loadImage(qrDataUrl)
  
  const canvas = document.createElement('canvas')
  canvas.width = qrSize
  canvas.height = qrSize
  const ctx = canvas.getContext('2d')
  if (!ctx) throw new Error('无法获取 canvas context')
  
  ctx.drawImage(qrImg, 0, 0)
  
  try {
    const logoImg = await loadImage(logoSrc)
    
    const logoX = (qrSize - logoSize) / 2
    const logoY = (qrSize - logoSize) / 2
    const bgSize = logoSize + 20
    const bgX = logoX - 10
    const bgY = logoY - 10
    
    ctx.save()
    drawRoundRect(ctx, bgX, bgY, bgSize, bgSize, borderRadius)
    ctx.fillStyle = dark ? '#0C0C0D' : '#F2F3F4'
    ctx.fill()
    ctx.restore()
    
    const logoCanvas = document.createElement('canvas')
    logoCanvas.width = logoSize
    logoCanvas.height = logoSize
    const logoCtx = logoCanvas.getContext('2d')
    if (logoCtx) {
      logoCtx.save()
      drawRoundRect(logoCtx, 0, 0, logoSize, logoSize, borderRadius - 2)
      logoCtx.clip()
      logoCtx.drawImage(logoImg, 0, 0, logoSize, logoSize)
      logoCtx.restore()
    }
    
    ctx.drawImage(logoCanvas, logoX, logoY)
  } catch (error) {
    console.error('加载logo失败，将显示无logo的二维码:', error)
  }
  
  return canvas.toDataURL('image/png')
}

const generateQrCode = async () => {
  try {
    bilibiliQrUrl.value = await generateQrCodeWithLogo(
      'https://space.bilibili.com/293679297',
      bilibiliLogo,
      isDark.value
    )
    
    douyinQrUrl.value = await generateQrCodeWithLogo(
      'https://v.douyin.com/CkiOU7VVuTY/',
      douyinLogo,
      isDark.value
    )
  } catch (error) {
    console.error('生成二维码失败:', error)
  }
}

watch(isDark, () => {
  generateQrCode()
})

onMounted(() => {
  generateQrCode()
})
</script>

<template>
  <div class="mx-auto space-y-8">
    <div class="text-center space-y-4">
      <div class="w-28 h-28 mx-auto">
        <img
          :src="`${publicBase}favicon.png`"
          alt="Logo"
          class="w-full h-full object-contain"
        >
      </div>
      <h1 class="text-3xl font-bold text-[var(--ui-text)]">
        关于 QwenPaw
      </h1>
      <p class="text-[var(--ui-text-muted)] mx-auto max-w-2xl">
        QwenPaw 是一款个人助理型 AI 应用，部署在你自己的环境中，保护你的数据隐私。
      </p>
    </div>

    <div class="grid gap-6 md:grid-cols-2 items-stretch">
      <UCard class="h-full rounded-2xl">
        <template #header>
          <div class="flex items-center gap-2">
            <UIcon
              name="i-lucide-user"
              class="w-5 h-5 text-primary"
            />
            <h2 class="font-semibold text-lg">
              关于作者
            </h2>
          </div>
        </template>

        <div class="h-full flex flex-col gap-4">
          <div class="space-y-2">
            <p class="text-[var(--ui-text)]">
              本项目由 <span class="font-bold text-primary">尘墨成</span> 开发与维护。
              <span class="text-sm text-[var(--ui-text-muted)]">
                致力于为 fnOS 用户提供更多优质的原生应用体验。
              </span>
            </p>
          </div>

          <div class="mt-auto">
            <UButton
              to="https://www.dustinky.com"
              target="_blank"
              color="primary"
              variant="soft"
              icon="i-lucide-globe"
              block
            >
              访问官网 www.dustinky.com
            </UButton>
            <UButton
              to="https://qm.qq.com/q/zXE0IqZtII"
              target="_blank"
              color="neutral"
              variant="outline"
              icon="i-lucide-users"
              class="mt-2"
              block
            >
              加入 QQ 交流群
            </UButton>
          </div>
        </div>
      </UCard>

      <UCard class="h-full rounded-2xl">
        <template #header>
          <div class="flex items-center gap-2">
            <UIcon
              name="i-lucide-book-open"
              class="w-5 h-5 text-primary"
            />
            <h2 class="font-semibold text-lg">
              fnOS 原生应用适配文档库
            </h2>
          </div>
        </template>

        <div class="h-full flex flex-col gap-4">
          <p class="text-sm text-[var(--ui-text-muted)]">
            这里是开发者尘墨成维护的 fnOS 原生应用适配文档库。我们致力于为 fnOS 用户提供体验更佳、集成度更高的原生应用解决方案。
          </p>

          <div class="mt-auto">
            <UButton
              to="https://fnosp.dustinky.com/"
              target="_blank"
              color="primary"
              variant="outline"
              icon="i-lucide-external-link"
              block
            >
              打开文档库 fnosp.dustinky.com
            </UButton>
          </div>
        </div>
      </UCard>
    </div>

    <div class="grid grid-cols-1 gap-6 md:grid-cols-3">
      <UCard class="h-full rounded-2xl">
        <template #header>
          <div class="flex items-center justify-between">
            <div class="flex items-center gap-2">
              <UIcon
                name="i-lucide-heart"
                class="w-5 h-5 text-error"
              />
              <h2 class="font-semibold text-lg">
                支持维护
              </h2>
            </div>
          </div>
        </template>
        
        <div class="text-center space-y-4">
          <div class="relative inline-block">
            <img
              :src="`${publicBase}${isDark ? 'donate-dark.png' : 'donate-light.png'}`"
              alt="微信赞赏码"
              class="w-full mx-auto rounded-lg"
            >
          </div>
        </div>
      </UCard>

      <UCard class="h-full rounded-2xl">
        <template #header>
          <div class="flex items-center justify-between">
            <div class="flex items-center gap-2">
              <UIcon
                name="i-lucide-play-circle"
                class="w-5 h-5 text-[#00A1D6]"
              />
              <h2 class="font-semibold text-lg">
                哔哩哔哩
              </h2>
            </div>
            <UButton
              to="https://space.bilibili.com/293679297"
              target="_blank"
              color="primary"
              variant="ghost"
              size="sm"
              icon="i-lucide-external-link"
            >
              链接
            </UButton>
          </div>
        </template>
        
        <div class="text-center space-y-4">
          <div class="inline-block">
            <img
              :src="bilibiliQrUrl"
              alt="B站二维码"
              class="w-full mx-auto rounded-lg"
            >
          </div>
        </div>
      </UCard>

      <UCard class="h-full rounded-2xl">
        <template #header>
          <div class="flex items-center justify-between">
            <div class="flex items-center gap-2">
              <UIcon
                name="i-lucide-video"
                class="w-5 h-5 text-[#FE2C55]"
              />
              <h2 class="font-semibold text-lg">
                抖音
              </h2>
            </div>
            <UButton
              to="https://v.douyin.com/CkiOU7VVuTY/"
              target="_blank"
              color="primary"
              variant="ghost"
              size="sm"
              icon="i-lucide-external-link"
            >
              链接
            </UButton>
          </div>
        </template>
        
        <div class="text-center space-y-4">
          <div class="inline-block">
            <img
              :src="douyinQrUrl"
              alt="抖音二维码"
              class="w-full mx-auto rounded-lg"
            >
          </div>
        </div>
      </UCard>
    </div>

    <div class="grid grid-cols-1">
      <UCard class="rounded-2xl">
        <template #header>
          <div class="flex items-center gap-2">
            <UIcon
              name="i-lucide-message-circle"
              class="w-5 h-5 text-[#07C160]"
            />
            <h2 class="font-semibold text-lg">
              关注微信公众号
            </h2>
          </div>
        </template>
        
        <div class="flex flex-col items-center gap-6">
          <div class="relative flex-shrink-0">
            <img
              :src="`${publicBase}wechat-qrcode.png`"
              alt="微信公众号二维码"
              class="w-full"
            >
          </div>
        </div>
      </UCard>
    </div>
  </div>
</template>
