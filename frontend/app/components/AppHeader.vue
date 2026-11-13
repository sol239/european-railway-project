<script setup lang="ts">
defineProps<{ showSettings?: boolean }>()
defineEmits<{ openSettings: [] }>()
</script>

<template>
  <header class="app-header">
    <ULink to="/map" class="brand" aria-label="Railway Atlas map"><span class="brand-mark"><AppIcon name="rail" :size="24" /></span><span>railway<span class="brand-light">atlas</span><span class="brand-dot">.</span></span></ULink>
    <div class="header-divider" />
    <nav class="header-navigation" aria-label="Main navigation">
      <NuxtLink to="/map" active-class="active" :aria-current="$route.path === '/map' ? 'page' : undefined">Map</NuxtLink>
      <NuxtLink to="/statistics" active-class="active" :aria-current="$route.path === '/statistics' ? 'page' : undefined">Statistics</NuxtLink>
    </nav>
    <div v-if="showSettings" class="header-menu"><UButton type="button" class="settings-menu-button" aria-label="Map settings" aria-haspopup="dialog" @click="$emit('openSettings')"><AppIcon name="settings" :size="18" /><span>Map settings</span></UButton></div>
  </header>
</template>
