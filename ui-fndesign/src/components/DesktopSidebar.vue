<script setup lang="ts">
import { navigationConfig } from '@/config/navigation'
import { ref } from 'vue'

const items = ref(navigationConfig.desktop)
</script>

<template>
  <aside class="h-full w-64 bg-[var(--ui-bg)] flex flex-col flex-shrink-0">
    <div class="flex-1 overflow-y-auto p-2">
      <UNavigationMenu
        orientation="vertical"
        :items="items"
        class="data-[orientation=vertical]:w-full"
        :ui="{
          link: 'py-2.5'
        }"
      />
    </div>
    <div class="pt-3 pb-1 text-xs text-[var(--ui-text-muted)] text-center border-t border-[var(--ui-border)]/90">
      v2.0.0 © {{ new Date().getFullYear() }}
      <a
        class="font-bold text-primary"
        href="https://fnosp.dustinky.com"
        target="_blank"
      >
        尘墨成
      </a>
      . All rights reserved.
    </div>
  </aside>
</template>
