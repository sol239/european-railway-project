import type { RailStatistics } from '../../shared/types/statistics'
import { loadRailways } from '../utils/railways'
import { operatingRailLength } from '../utils/rail-statistics'

export default defineCachedEventHandler(async (event): Promise<RailStatistics> => {
  const config = useRuntimeConfig(event)
  try {
    const railway = await loadRailways({
      endpoint: config.minioEndpoint, bucket: config.minioBucket,
      accessKey: config.minioAccessKey || process.env.MINIO_ROOT_USER || '',
      secretKey: config.minioSecretKey || process.env.MINIO_ROOT_PASSWORD || '',
    })
    return {
      operatingLengthMeters: operatingRailLength(railway.features),
      operatingSegments: railway.metadata.operatingSegments,
      uploadedAt: railway.metadata.uploadedAt,
    }
  } catch (error) {
    console.error('Rail statistics unavailable:', error instanceof Error ? error.message : 'Unknown error')
    throw createError({ statusCode: 503, statusMessage: 'Rail statistics are unavailable.' })
  }
}, { maxAge: 300, swr: false })
