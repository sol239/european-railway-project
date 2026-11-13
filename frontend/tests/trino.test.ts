import { afterEach, describe, expect, it, vi } from 'vitest'
import { queryTrino } from '../server/utils/trino'
import { stationQuery, validServiceDate } from '../server/utils/station-query'

afterEach(() => vi.unstubAllGlobals())
const options = { url: 'http://localhost:7006', user: 'admin' }

describe('Trino pagination', () => {
  it('collects queued and paginated results with their columns', async () => {
    const fetch = vi.fn()
      .mockResolvedValueOnce(Response.json({ nextUri: 'http://localhost:7006/v1/statement/queued/1' }))
      .mockResolvedValueOnce(Response.json({ columns: [{ name: 'station_key' }], data: [[543]], nextUri: 'http://localhost:7006/v1/statement/executing/1' }))
      .mockResolvedValueOnce(Response.json({ data: [[544]] }))
    vi.stubGlobal('fetch', fetch)
    expect(await queryTrino('SELECT station_key FROM railway.gold.dim_station', options)).toEqual([{ station_key: 543 }, { station_key: 544 }])
    expect(fetch.mock.calls[0]?.[1].method).toBe('POST')
    expect(fetch.mock.calls[1]?.[1].method).toBe('GET')
  })
  it('rejects query errors', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(Response.json({ error: { errorName: 'SERVER_STARTING_UP' } })))
    await expect(queryTrino('SELECT 1', options)).rejects.toThrow('SERVER_STARTING_UP')
  })
  it('does not follow pagination to another origin', async () => {
    const fetch = vi.fn().mockResolvedValue(Response.json({ nextUri: 'http://untrusted.invalid/v1/statement/1' }))
    vi.stubGlobal('fetch', fetch)
    await expect(queryTrino('SELECT 1', options)).rejects.toThrow('Unexpected Trino pagination URL')
    expect(fetch).toHaveBeenCalledTimes(1)
  })
  it('fails cleanly for an unreachable HTTP service', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('', { status: 503 })))
    await expect(queryTrino('SELECT 1', options)).rejects.toThrow('Trino HTTP 503')
  })
})
describe('service date filtering', () => {
  it('accepts a real date and uses EXISTS to avoid multiplying stop visits', () => {
    expect(validServiceDate('2026-11-12')).toBe('2026-11-12')
    expect(stationQuery('2026-11-12')).toContain("d.service_date = DATE '2026-11-12'")
    expect(stationQuery('2026-11-12')).toContain('WHERE EXISTS')
    expect(stationQuery(null)).not.toContain('WHERE EXISTS')
  })
  it.each(['2026-02-30', "2026-11-12' OR 1=1", 'not-a-date', ['2026-11-12']])('rejects invalid dates and SQL fragments', value => {
    expect(() => validServiceDate(value)).toThrow()
  })
})
