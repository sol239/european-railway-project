import { createHash } from 'node:crypto'
import { readFileSync } from 'node:fs'
import { beforeEach, describe, expect, it, vi } from 'vitest'
const mocks = vi.hoisted(() => ({ send: vi.fn(), destroy: vi.fn() }))
vi.mock('@aws-sdk/client-s3', () => ({
  S3Client: class { send = mocks.send; destroy = mocks.destroy },
  GetObjectCommand: class { constructor(public input: unknown) {} },
}))
import { decodeRailwayParquet, loadRailways, RFN_PREFIX } from '../server/utils/railways'

const bytes = new Uint8Array(readFileSync(new URL('./fixtures/rfn-lines.parquet', import.meta.url)))
const manifest = {
  dataset: 'formes-des-lignes-du-rfn', key: `${RFN_PREFIX}/sample/lines.parquet`, run_id: 'sample', rows: 2,
  sha256: createHash('sha256').update(bytes).digest('hex'), uploaded_at: '2026-11-13T10:00:00Z',
}
const options = { endpoint: 'http://localhost:7004', bucket: 'railway', accessKey: 'test-user', secretKey: 'test-secret' }
function body(value: object | Uint8Array) {
  const data = value instanceof Uint8Array ? value : new TextEncoder().encode(JSON.stringify(value))
  return { ContentLength: data.length, Body: { transformToByteArray: async () => data } }
}
beforeEach(() => { mocks.send.mockReset(); mocks.destroy.mockReset() })
function goodObjects(override = {}) {
  mocks.send.mockResolvedValueOnce(body({ manifest_key: `${RFN_PREFIX}/sample/manifest.json` }))
    .mockResolvedValueOnce(body({ ...manifest, ...override })).mockResolvedValueOnce(body(bytes))
}

describe('RFN GeoParquet decoding', () => {
  it('decodes real compressed WKB, preserving longitude/latitude and status', async () => {
    const features = await decodeRailwayParquet(bytes)
    expect(features).toHaveLength(2)
    expect(features[0]?.geometry).toEqual({ type: 'LineString', coordinates: [[2, 48], [2.1, 48.1]] })
    expect(features[0]?.properties).toMatchObject({ code_ligne: '001000', mnemo: 'EXPLOITE', rg_troncon: 1 })
    expect(features[1]?.properties.mnemo).toBe('FERME')
    expect(() => JSON.stringify(features)).not.toThrow()
    expect(features[0]?.id).not.toBe(features[1]?.id)
  })
  it('rejects invalid Parquet data', async () => {
    await expect(decodeRailwayParquet(new Uint8Array([1, 2, 3]))).rejects.toThrow()
  })
})
describe('MinIO railway snapshot loading', () => {
  it('follows the latest pointer, verifies the snapshot and returns safe GeoJSON', async () => {
    goodObjects()
    const response = await loadRailways(options)
    expect(response.metadata.segments).toBe(2)
    expect(response.metadata.operatingSegments).toBe(1)
    expect(response.metadata.runId).toBe('sample')
    expect(mocks.send.mock.calls.map(call => call[0].input.Key)).toEqual([
      `${RFN_PREFIX}/_latest.json`, `${RFN_PREFIX}/sample/manifest.json`, manifest.key,
    ])
    expect(JSON.stringify(response)).not.toContain('test-secret')
    expect(mocks.destroy).toHaveBeenCalledOnce()
  })
  it('rejects an altered file before decoding it', async () => {
    goodObjects({ sha256: 'bad-checksum' })
    await expect(loadRailways(options)).rejects.toThrow('checksum mismatch')
    expect(mocks.destroy).toHaveBeenCalledOnce()
  })
  it('rejects an incomplete dataset', async () => {
    goodObjects({ rows: 3 })
    await expect(loadRailways(options)).rejects.toThrow('row count mismatch')
  })
  it('rejects pointers outside the RFN dataset', async () => {
    mocks.send.mockResolvedValueOnce(body({ manifest_key: 'private/manifest.json' }))
    await expect(loadRailways(options)).rejects.toThrow('Invalid RFN latest pointer')
    expect(mocks.send).toHaveBeenCalledOnce()
  })
  it('handles a missing dataset or unreachable MinIO service', async () => {
    mocks.send.mockRejectedValueOnce(new Error('NoSuchKey'))
    await expect(loadRailways(options)).rejects.toThrow('NoSuchKey')
    expect(mocks.destroy).toHaveBeenCalledOnce()
  })
})
