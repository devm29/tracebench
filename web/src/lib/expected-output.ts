export type ParsedExpected = { ok: true; value: unknown } | { ok: false; error: string }

/**
 * Turns the editor text back into an expected output. Text stays text when the original was
 * text (or absent); structured originals must stay valid JSON, since scorers such as
 * json_schema compare against the parsed value.
 */
export function parseExpected(text: string, original: unknown): ParsedExpected {
  if (!text.trim()) return { ok: true, value: null }
  if (typeof original === "string" || original === null || original === undefined) return { ok: true, value: text }
  try {
    return { ok: true, value: JSON.parse(text) }
  } catch (error) {
    const detail = error instanceof SyntaxError ? error.message : "invalid JSON"
    return { ok: false, error: `The original expected output is JSON, so this must be too (${detail}).` }
  }
}
