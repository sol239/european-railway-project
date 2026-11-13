interface QueryPage {
  columns?: { name: string }[]
  data?: unknown[][]
  nextUri?: string
  error?: { message: string; errorName: string }
}

export interface TrinoOptions {
  url: string
  user: string
  timeoutMs?: number
}

/** Consume the Trino HTTP protocol, including all result pages. */
export async function queryTrino(sql: string, options: TrinoOptions): Promise<Record<string, unknown>[]> {
  const origin = new URL(options.url).origin
  const headers = { 'X-Trino-User': options.user, 'X-Trino-Source': 'railway-atlas', 'Content-Type': 'text/plain' }
  const signal = AbortSignal.timeout(options.timeoutMs ?? 45_000)
  let next: string | undefined = new URL('/v1/statement', origin).href
  let first = true
  let columns: { name: string }[] = []
  const rows: Record<string, unknown>[] = []
  try {
    while (next) {
      const pageUrl = new URL(next)
      if (pageUrl.origin !== origin || !pageUrl.pathname.startsWith('/v1/statement')) {
        throw new Error('Unexpected Trino pagination URL')
      }
      const response = await fetch(pageUrl, {
        method: first ? 'POST' : 'GET', headers, body: first ? sql : undefined,
        signal, redirect: 'error',
      })
      if (!response.ok) throw new Error(`Trino HTTP ${response.status}`)
      const page = await response.json() as QueryPage
      next = page.nextUri
      if (page.error) throw new Error(`Trino query failed: ${page.error.errorName}`)
      if (page.columns) columns = page.columns
      for (const row of page.data ?? []) {
        rows.push(Object.fromEntries(columns.map((column, index) => [column.name, row[index]])))
      }
      first = false
      if (next && !page.data?.length) {
        await new Promise(resolve => setTimeout(resolve, 50))
      }
    }
    return rows
  } catch (error) {
    if (next && new URL(next).origin === origin) {
      await fetch(next, { method: 'DELETE', headers, signal: AbortSignal.timeout(2000), redirect: 'error' }).catch(() => {})
    }
    throw error
  }
}
