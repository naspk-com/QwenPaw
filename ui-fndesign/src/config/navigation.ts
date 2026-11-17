import type { NavigationMenuItem } from '@nuxt/ui'

export interface NavItem {
  label: string
  icon?: string
  to?: string
  children?: NavItem[]
  badge?: string | number
  target?: string
}

export interface NavigationConfig {
  desktop: NavigationMenuItem[][]
  mobile: NavigationMenuItem[]
}

export const navigationConfig: NavigationConfig = {
  desktop: [
    [
      {
        label: '控制台',
        icon: 'i-lucide-home',
        to: '/',
      },
      {
        label: '目录授权',
        icon: 'i-lucide-folder-key',
        to: '/files',
      },
      {
        label: '日志查看',
        icon: 'i-lucide-file-text',
        to: '/logs',
      },
      {
        label: '外网访问',
        icon: 'i-lucide-globe',
        to: '/tunnel',
      },
      {
        label: 'QQ群交流',
        icon: 'i-lucide-users',
        to: 'https://qm.qq.com/q/zXE0IqZtII',
        target: '_blank',
      },
      {
        label: '关于',
        icon: 'i-lucide-info',
        to: '/about',
      },
    ]
  ],
  mobile: [
    {
      label: '控制台',
      icon: 'i-lucide-home',
      to: '/',
    },
    {
      label: '目录',
      icon: 'i-lucide-folder-key',
      to: '/files',
    },
    {
      label: '日志',
      icon: 'i-lucide-file-text',
      to: '/logs',
    },
    {
      label: '外网',
      icon: 'i-lucide-globe',
      to: '/tunnel',
    },
    {
      label: '关于',
      icon: 'i-lucide-info',
      to: '/about',
    },
  ]
}
