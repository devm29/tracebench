"use client"

import Link from "next/link"
import { useState } from "react"
import { toast } from "sonner"

import { CodeBlock } from "@/components/code-block"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog"
import { Label } from "@/components/ui/label"
import { Sheet, SheetContent, SheetDescription, SheetFooter, SheetHeader, SheetTitle } from "@/components/ui/sheet"
import { Textarea } from "@/components/ui/textarea"
import { useDeleteItem, useUpdateItem } from "@/lib/api/hooks"
import type { DatasetItem } from "@/lib/api/schemas"
import { parseExpected } from "@/lib/expected-output"
import { lastUserMessage, toText } from "@/lib/format"

interface ItemSheetProps {
  item: DatasetItem | undefined
  datasetId: string
  readOnly: boolean
  onClose: () => void
}

export function ItemSheet({ item, ...props }: ItemSheetProps) {
  return (
    <Sheet open={item !== undefined} onOpenChange={(open) => !open && props.onClose()}>
      <SheetContent className="flex w-full flex-col gap-0 sm:max-w-xl">
        {/* Keyed by revision id: the draft resets when another revision opens, not on every refetch. */}
        {item ? <ItemEditor key={item.id} item={item} {...props} /> : null}
      </SheetContent>
    </Sheet>
  )
}

function ItemEditor({ item, datasetId, readOnly, onClose }: ItemSheetProps & { item: DatasetItem }) {
  const update = useUpdateItem(datasetId)
  const remove = useDeleteItem(datasetId)
  const [draft, setDraft] = useState(() => toText(item.expected_output ?? ""))

  const dirty = draft !== toText(item.expected_output ?? "")
  const parsed = parseExpected(draft, item.expected_output)
  const invalid = parsed.ok ? undefined : parsed.error

  const save = () => {
    if (!parsed.ok) return
    update.mutate(
      { itemKey: item.item_key, expected: parsed.value },
      {
        onSuccess: () => {
          toast.success("Saved as a new dataset version")
          onClose()
        },
        onError: (error) => toast.error("Couldn't save", { description: error.message }),
      }
    )
  }

  return (
    <>
      <SheetHeader className="border-b border-border/60 px-5 py-4">
        <SheetTitle className="text-[17px]">Case {item.item_key.slice(0, 8)}</SheetTitle>
        <SheetDescription className="text-[13px]">
          Revision {item.revision}
          {item.source_trace_id ? (
            <>
              {" · from "}
              <Link href={`/traces/${item.source_trace_id}`} className="text-primary hover:underline">
                trace {item.source_trace_id.slice(0, 8)}
              </Link>
            </>
          ) : null}
        </SheetDescription>
      </SheetHeader>
      <div className="flex-1 space-y-5 overflow-y-auto px-5 py-5">
        <section className="space-y-2">
          <h3 className="text-[11px] font-medium tracking-wide text-muted-foreground uppercase">Input</h3>
          <p className="rounded-lg bg-secondary px-3 py-2 text-[13px] dark:bg-accent/30">{lastUserMessage(item.input)}</p>
          <details className="text-[12px] text-muted-foreground">
            <summary className="cursor-pointer">Raw request body</summary>
            <CodeBlock value={item.input} className="mt-2" />
          </details>
        </section>
        <section className="space-y-2">
          <Label htmlFor="expected" className="text-[11px] font-medium tracking-wide text-muted-foreground uppercase">
            Expected output
          </Label>
          <Textarea
            id="expected"
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            readOnly={readOnly}
            className="min-h-48 rounded-lg font-mono text-[12px] leading-[18px]"
            aria-describedby={invalid ? "expected-error expected-help" : "expected-help"}
            aria-invalid={invalid !== undefined}
          />
          {invalid ? (
            <p id="expected-error" role="alert" className="text-[12px] text-destructive">
              {invalid}
            </p>
          ) : null}
          <p id="expected-help" className="text-[12px] text-muted-foreground">
            {readOnly
              ? "You're viewing an older version. Switch to the latest version to edit."
              : "Saving creates a new dataset version; runs pinned to older versions are unaffected."}
          </p>
        </section>
        {Object.keys(item.metadata).length ? (
          <section className="space-y-2">
            <h3 className="text-[11px] font-medium tracking-wide text-muted-foreground uppercase">Metadata</h3>
            <CodeBlock value={item.metadata} />
          </section>
        ) : null}
      </div>
      <SheetFooter className="flex-row items-center justify-between border-t border-border/60 px-5 py-3">
        {readOnly ? (
          <span />
        ) : (
          <Dialog>
            <DialogTrigger asChild>
              <Button variant="ghost" className="text-destructive hover:text-destructive">
                Remove case
              </Button>
            </DialogTrigger>
            <DialogContent className="rounded-2xl sm:max-w-sm">
              <DialogHeader>
                <DialogTitle className="text-[17px]">Remove this case?</DialogTitle>
                <DialogDescription className="text-[13px]">
                  It disappears from the next version. Earlier versions and past runs keep it.
                </DialogDescription>
              </DialogHeader>
              <DialogFooter className="gap-2">
                <DialogClose asChild>
                  <Button variant="secondary">Cancel</Button>
                </DialogClose>
                <Button
                  variant="destructive"
                  disabled={remove.isPending}
                  onClick={() =>
                    remove.mutate(item.item_key, {
                      onSuccess: () => {
                        toast.success("Case removed")
                        onClose()
                      },
                      onError: (error) => toast.error("Couldn't remove", { description: error.message }),
                    })
                  }
                >
                  {remove.isPending ? "Removing…" : "Remove"}
                </Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>
        )}
        <div className="flex gap-2">
          <Button variant="secondary" onClick={onClose}>
            Close
          </Button>
          {readOnly ? null : (
            <Button onClick={save} disabled={!dirty || invalid !== undefined || update.isPending}>
              {update.isPending ? "Saving…" : "Save"}
            </Button>
          )}
        </div>
      </SheetFooter>
    </>
  )
}
