import type { Overview } from '../types'

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...init?.headers,
    },
  })
  if (!response.ok) {
    const body = await response.json().catch(() => null) as { detail?: string } | null
    throw new Error(body?.detail ?? `Request failed (${response.status})`)
  }
  return response.json() as Promise<T>
}

export function getOverview(): Promise<Overview> {
  return request<Overview>('/api/overview')
}

export function startRefresh(): Promise<{ status: string; message: string }> {
  return request('/api/refresh', { method: 'POST' })
}
