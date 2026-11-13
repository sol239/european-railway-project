import { loadRailways } from '../utils/railways'

export default defineCachedEventHandler(async (event) => {
  const config = useRuntimeConfig(event)
  try {
    return await loadRailways({
      endpoint: config.minioEndpoint, bucket: config.minioBucket,
      accessKey: config.minioAccessKey || process.env.MINIO_ROOT_USER || '',
      secretKey: config.minioSecretKey || process.env.MINIO_ROOT_PASSWORD || '',
    })
  } catch (error) {
    console.error('Railway layer unavailable:', error instanceof Error ? error.message : 'Unknown error')
    throw createError({ statusCode: 503, statusMessage: 'Railway lines are unavailable. Check MinIO and run the RFN download DAG.' })
  }
}, { maxAge: 60, swr: false })
