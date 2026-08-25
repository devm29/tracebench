export type DiffOp = { kind: "same" | "added" | "removed"; text: string }

const MAX_TOKENS = 1200

function tokenize(text: string): string[] {
  return text.match(/\s+|[^\s]+/g) ?? []
}

/** Word-level diff via LCS; inputs beyond MAX_TOKENS fall back to a whole-text replacement. */
export function wordDiff(before: string, after: string): DiffOp[] {
  const a = tokenize(before)
  const b = tokenize(after)
  if (a.length > MAX_TOKENS || b.length > MAX_TOKENS) {
    return [
      { kind: "removed", text: before },
      { kind: "added", text: after },
    ]
  }
  const rows = a.length + 1
  const cols = b.length + 1
  const table = new Uint16Array(rows * cols)
  for (let i = a.length - 1; i >= 0; i -= 1) {
    for (let j = b.length - 1; j >= 0; j -= 1) {
      table[i * cols + j] =
        a[i] === b[j]
          ? (table[(i + 1) * cols + j + 1] ?? 0) + 1
          : Math.max(table[(i + 1) * cols + j] ?? 0, table[i * cols + j + 1] ?? 0)
    }
  }
  const ops: DiffOp[] = []
  const push = (kind: DiffOp["kind"], text: string) => {
    const last = ops[ops.length - 1]
    if (last && last.kind === kind) last.text += text
    else ops.push({ kind, text })
  }
  let i = 0
  let j = 0
  while (i < a.length && j < b.length) {
    const left = a[i] ?? ""
    const right = b[j] ?? ""
    if (left === right) {
      push("same", left)
      i += 1
      j += 1
    } else if ((table[(i + 1) * cols + j] ?? 0) >= (table[i * cols + j + 1] ?? 0)) {
      push("removed", left)
      i += 1
    } else {
      push("added", right)
      j += 1
    }
  }
  while (i < a.length) push("removed", a[i++] ?? "")
  while (j < b.length) push("added", b[j++] ?? "")
  return ops
}
