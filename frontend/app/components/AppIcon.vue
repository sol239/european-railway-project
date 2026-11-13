<script setup lang="ts">
const props = defineProps<{ name: string; size?: number }>()
const icons: Record<string, string> = { rail: 'train-track', search: 'search', arrow: 'arrow-right', pin: 'map-pin', layers: 'layers', calendar: 'calendar-days', close: 'x', home: 'house', plus: 'plus', minus: 'minus', compass: 'compass', refresh: 'refresh-cw', settings: 'sliders-horizontal', camera: 'camera', 'camera-locked': 'camera' }
</script>
<template><UIcon :name="'i-lucide-' + (icons[props.name] || 'map-pin')" :style="{ width: (size || 20) + 'px', height: (size || 20) + 'px', flexShrink: 0 }" aria-hidden="true" /></template>
