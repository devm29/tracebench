import type { z } from "zod"

import { apiErrorSchema } from "./schemas"

export const API_URL = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8105").replace(/\/$/, "")

// Compiled into the bundle, so only meant for a UI that already sits behind SSO or a VPN.
const API_TOKEN = process.env.NEXT_PUBLIC_API_TOKEN

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string
  ) {
    super(message)
    this.name = "ApiError"
  }
}

type Query = Record<string, string | number | boolean | null | undefined>

export function buildUrl(path: string, query?: Query): string {
  const url = new URL(`${API_URL}${path}`)
  for (const [key, value] of Object.entries(query ?? {})) {
    if (value !== undefined && value !== null && value !== "") url.searchParams.set(key, String(value))
  }
  return url.toString()
}

interface RequestOptions {
  method?: "GET" | "POST" | "PATCH" | "DELETE"
  query?: Query
  body?: unknown
  signal?: AbortSignal
}

export async function request<S extends z.ZodType>(
  path: string,
  schema: S,
  { method = "GET", query, body, signal }: RequestOptions = {}
): Promise<z.output<S>> {
  const headers: Record<string, string> = { Accept: "application/json" }
  if (API_TOKEN && method !== "GET") headers.Authorization = `Bearer ${API_TOKEN}`
  const init: RequestInit = { method, headers }
  if (signal) init.signal = signal
  if (body !== undefined) {
    init.body = JSON.stringify(body)
    headers["Content-Type"] = "application/json"
  }
  let response: Response
  try {
    response = await fetch(buildUrl(path, query), init)
  } catch (cause) {
    if (cause instanceof DOMException && cause.name === "AbortError") throw cause
    throw new ApiError(0, "network_error", `Can't reach the Tracebench API at ${API_URL}. Is it running?`)
  }
  if (!response.ok) {
    const parsed = apiErrorSchema.safeParse(await response.json().catch(() => null))
    throw new ApiError(
      response.status,
      parsed.success ? parsed.data.error.code : "http_error",
      parsed.success ? parsed.data.error.message : `Request failed with status ${response.status}`
    )
  }
  if (response.status === 204) return schema.parse(undefined)
  const payload: unknown = await response.json()
  const result = schema.safeParse(payload)
  if (!result.success) {
    throw new ApiError(response.status, "invalid_response", `Unexpected response from ${path}`)
  }
  return result.data
}
