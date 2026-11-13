export default defineNuxtConfig({
  compatibilityDate: '2026-11-13',
  modules: ['@nuxt/ui'],
  ui: { colorMode: false },
  devtools: { enabled: false },
  css: ['~/assets/css/ui.css', 'cesium/Build/Cesium/Widgets/widgets.css', '~/assets/css/main.css'],
  runtimeConfig: {
    trinoUrl: 'http://127.0.0.1:7006',
    trinoUser: 'admin',
    minioEndpoint: 'http://127.0.0.1:7004',
    minioBucket: 'railway',
    minioAccessKey: '',
    minioSecretKey: '',
  },
  vite: {
    define: { CESIUM_BASE_URL: JSON.stringify('/cesium/') },
  },
  app: {
    head: {
      title: 'Railway Atlas · Station explorer',
      meta: [{ name: 'description', content: 'Explore railway stations and scheduled stop visits on an interactive map with 2D and 3D views.' }],
      link: [{ rel: 'icon', type: 'image/svg+xml', href: '/favicon.svg' }],
    },
  },
})
