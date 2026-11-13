import { createHash } from 'node:crypto'
import { S3Client, GetObjectCommand } from '@aws-sdk/client-s3'
import { parquetReadObjects } from 'hyparquet'
import { compressors } from 'hyparquet-compressors'
import type { RailwayGeometry, RailwayFeature, RailwayResponse } from '../../shared/types/railway'

export const RFN_PREFIX = 'data/raw/formes-des-lignes-du-rfn'
interface MinioOptions { endpoint: string; accessKey: string; secretKey: string; bucket: string }
interface Manifest { dataset: string; key: string; run_id: string; rows: number; sha256: string; uploaded_at: string }

function validGeometry(value: unknown): value is RailwayGeometry {
  if (!value || typeof value !== 'object') return false
  const geometry = value as RailwayGeometry
  if (!['LineString', 'MultiLineString'].includes(geometry.type) || !Array.isArray(geometry.coordinates)) return false
  const lines = geometry.type === 'LineString' ? [geometry.coordinates] : geometry.coordinates
  return lines.length > 0 && lines.every(line => Array.isArray(line) && line.length >= 2 && line.every(point =>
    Array.isArray(point) && point.length >= 2 && Number.isFinite(point[0]) && Number.isFinite(point[1])
    && Math.abs(point[0]!) <= 180 && Math.abs(point[1]!) <= 90))
}

/** GeoParquet's WKB fields are decoded to GeoJSON by hyparquet. */
export async function decodeRailwayParquet(bytes: Uint8Array): Promise<RailwayFeature[]> {
  const rows = await parquetReadObjects({
    file: Uint8Array.from(bytes).buffer, compressors, utf8: false,
    columns: ['geo_shape', 'code_ligne', 'mnemo', 'libelle', 'rg_troncon', 'pk_debut_r', 'pk_fin_r'],
  })
  return rows.map((row, index) => {
    if (!validGeometry(row.geo_shape)) throw new Error(`Invalid RFN line geometry at row ${index}`)
    return {
      type: 'Feature', id: `rfn-${index}`, geometry: row.geo_shape,
      properties: {
        code_ligne: String(row.code_ligne), mnemo: String(row.mnemo), libelle: String(row.libelle),
        rg_troncon: Number(row.rg_troncon), pk_debut_r: String(row.pk_debut_r), pk_fin_r: String(row.pk_fin_r),
      },
    }
  })
}

export async function loadRailways(options: MinioOptions): Promise<RailwayResponse> {
  if (!options.accessKey || !options.secretKey) throw new Error('MinIO credentials are not configured')
  const client = new S3Client({
    endpoint: options.endpoint, region: 'us-east-1', forcePathStyle: true, maxAttempts: 2,
    credentials: { accessKeyId: options.accessKey, secretAccessKey: options.secretKey },
  })
  try {
    async function object(key: string, maxBytes: number) {
      const response = await client.send(new GetObjectCommand({ Bucket: options.bucket, Key: key }), {
        abortSignal: AbortSignal.timeout(20_000),
      })
      if (!response.Body) throw new Error('Empty MinIO response')
      if ((response.ContentLength ?? 0) > maxBytes) throw new Error('RFN object exceeds size limit')
      const bytes = await response.Body.transformToByteArray()
      if (bytes.length > maxBytes) throw new Error('RFN object exceeds size limit')
      return bytes
    }
    async function json(key: string) { return JSON.parse(new TextDecoder().decode(await object(key, 64_000))) }
    const pointer = await json(`${RFN_PREFIX}/_latest.json`)
    if (typeof pointer.manifest_key !== 'string' || !pointer.manifest_key.startsWith(`${RFN_PREFIX}/`) || !pointer.manifest_key.endsWith('/manifest.json')) {
      throw new Error('Invalid RFN latest pointer')
    }
    const manifest = await json(pointer.manifest_key) as Manifest
    if (manifest.dataset !== 'formes-des-lignes-du-rfn' || !manifest.key?.startsWith(`${RFN_PREFIX}/`) || !manifest.key.endsWith('.parquet')) {
      throw new Error('Invalid RFN manifest')
    }
    const bytes = await object(manifest.key, 64 * 1024 * 1024)
    if (createHash('sha256').update(bytes).digest('hex') !== manifest.sha256) throw new Error('RFN checksum mismatch')
    const features = await decodeRailwayParquet(bytes)
    if (features.length !== manifest.rows) throw new Error('RFN row count mismatch')
    return {
      type: 'FeatureCollection', features,
      metadata: {
        dataset: manifest.dataset, runId: manifest.run_id, uploadedAt: manifest.uploaded_at,
        segments: features.length, operatingSegments: features.filter(feature => feature.properties.mnemo === 'EXPLOITE').length,
        sha256: manifest.sha256,
      },
    }
  } finally { client.destroy() }
}
