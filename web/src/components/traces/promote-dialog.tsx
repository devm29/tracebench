"use client"

import { DatabaseZap } from "lucide-react"
import Link from "next/link"
import { useState, type FormEvent } from "react"
import { toast } from "sonner"

import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { ApiError } from "@/lib/api/client"
import { useDatasets, usePromoteTrace } from "@/lib/api/hooks"

const NEW = "__new__"
const NAME_PATTERN = /^[a-z0-9][a-z0-9._-]{1,79}$/

export function PromoteDialog({ traceId, spanId, spanName }: { traceId: string; spanId: string | undefined; spanName: string }) {
  const [open, setOpen] = useState(false)
  const datasets = useDatasets()
  const promote = usePromoteTrace(traceId)
  const [choice, setChoice] = useState<string>("")
  const [newName, setNewName] = useState("")
  const selected = choice || datasets.data?.[0]?.name || NEW
  const name = selected === NEW ? newName.trim() : selected
  const nameError = selected === NEW && newName.length > 0 && !NAME_PATTERN.test(newName.trim())
    ? "Use 2–80 lowercase letters, numbers, dots, dashes or underscores."
    : null

  const submit = (event: FormEvent) => {
    event.preventDefault()
    if (!name || nameError) return
    promote.mutate(
      { dataset_name: name, span_id: spanId },
      {
        onSuccess: (item) => {
          setOpen(false)
          toast.success(`Added to ${name}`, {
            description: "Edit the expected output any time; each edit creates a new dataset version.",
            action: { label: "Open", onClick: () => window.location.assign(`/datasets/${item.dataset_id}`) },
          })
        },
        onError: (error) => {
          toast.error(error instanceof ApiError && error.status === 409 ? "Already in that dataset" : "Couldn't add the trace", {
            description: error.message,
          })
        },
      }
    )
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button>
          <DatabaseZap strokeWidth={1.75} />
          Add to dataset
        </Button>
      </DialogTrigger>
      <DialogContent className="rounded-2xl sm:max-w-md">
        <form onSubmit={submit} className="space-y-5">
          <DialogHeader>
            <DialogTitle className="text-[17px]">Add to a golden dataset</DialogTitle>
            <DialogDescription className="text-[13px]">
              Captures the input and output of <span className="font-medium text-foreground">{spanName}</span> as a
              regression case. Evals replay the input against your app and compare with this output.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-2">
            <Label htmlFor="dataset" className="text-[13px]">
              Dataset
            </Label>
            <Select value={selected} onValueChange={setChoice}>
              <SelectTrigger id="dataset" className="h-9 w-full rounded-lg">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {datasets.data?.map((dataset) => (
                  <SelectItem key={dataset.id} value={dataset.name}>
                    {dataset.name}
                  </SelectItem>
                ))}
                <SelectItem value={NEW}>New dataset…</SelectItem>
              </SelectContent>
            </Select>
          </div>
          {selected === NEW ? (
            <div className="space-y-2">
              <Label htmlFor="new-dataset" className="text-[13px]">
                Name
              </Label>
              <Input
                id="new-dataset"
                autoFocus
                value={newName}
                onChange={(event) => setNewName(event.target.value)}
                placeholder="support-agent-golden"
                aria-invalid={nameError !== null}
                aria-describedby="new-dataset-help"
                className="h-9 rounded-lg"
              />
              <p id="new-dataset-help" className={nameError ? "text-[12px] text-destructive" : "text-[12px] text-muted-foreground"}>
                {nameError ?? "Lowercase, no spaces. It's created on first use."}
              </p>
            </div>
          ) : null}
          <DialogFooter className="gap-2">
            <Button type="button" variant="secondary" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={!name || nameError !== null || promote.isPending}>
              {promote.isPending ? "Adding…" : "Add case"}
            </Button>
          </DialogFooter>
          {datasets.data?.length === 0 ? (
            <p className="text-[12px] text-muted-foreground">
              No datasets yet. You can also create one on the <Link href="/datasets" className="text-primary">Datasets</Link> page.
            </p>
          ) : null}
        </form>
      </DialogContent>
    </Dialog>
  )
}
