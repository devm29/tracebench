"use client"

import { Plus } from "lucide-react"
import { useRouter } from "next/navigation"
import { useState, type FormEvent } from "react"
import { toast } from "sonner"

import { Button } from "@/components/ui/button"
import { Checkbox } from "@/components/ui/checkbox"
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
import { Textarea } from "@/components/ui/textarea"
import { useCreateDataset } from "@/lib/api/hooks"
import type { ScorerSpec } from "@/lib/api/schemas"

const NAME_PATTERN = /^[a-z0-9][a-z0-9._-]{1,79}$/

const SCORERS: Array<{ id: string; label: string; help: string; spec: ScorerSpec }> = [
  {
    id: "embedding",
    label: "Embedding similarity",
    help: "Passes when the answer means the same thing (cosine ≥ 0.85).",
    spec: { type: "embedding_similarity", threshold: 0.85 },
  },
  {
    id: "judge",
    label: "LLM judge",
    help: "A model grades the answer against the expected one.",
    spec: {
      type: "llm_judge",
      threshold: 0.6,
      rubric:
        "The response answers the user's request with the same facts and outcome as the expected answer. Wording may differ; missing or contradicting facts may not.",
    },
  },
  {
    id: "exact",
    label: "Exact match",
    help: "Ignores case and whitespace. Best for classifiers and structured output.",
    spec: { type: "exact_match", case_sensitive: false, normalize_whitespace: true },
  },
]

export function CreateDatasetDialog() {
  const router = useRouter()
  const create = useCreateDataset()
  const [open, setOpen] = useState(false)
  const [name, setName] = useState("")
  const [description, setDescription] = useState("")
  const [selected, setSelected] = useState<ReadonlySet<string>>(new Set(["embedding", "judge"]))
  const nameError = name && !NAME_PATTERN.test(name) ? "Use 2–80 lowercase letters, numbers, dots, dashes or underscores." : null

  const submit = (event: FormEvent) => {
    event.preventDefault()
    if (!name || nameError) return
    create.mutate(
      {
        name,
        description,
        default_scorers: SCORERS.filter((s) => selected.has(s.id)).map((s) => s.spec),
      },
      {
        onSuccess: (dataset) => {
          setOpen(false)
          toast.success(`Created ${dataset.name}`)
          router.push(`/datasets/${dataset.id}`)
        },
        onError: (error) => toast.error("Couldn't create the dataset", { description: error.message }),
      }
    )
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button>
          <Plus strokeWidth={1.75} />
          New dataset
        </Button>
      </DialogTrigger>
      <DialogContent className="rounded-2xl sm:max-w-lg">
        <form onSubmit={submit} className="space-y-5">
          <DialogHeader>
            <DialogTitle className="text-[17px]">New dataset</DialogTitle>
            <DialogDescription className="text-[13px]">
              A golden dataset holds real inputs and the outputs you expect. Fill it from the trace viewer.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-2">
            <Label htmlFor="name" className="text-[13px]">
              Name
            </Label>
            <Input
              id="name"
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder="checkout-assistant-golden"
              aria-invalid={nameError !== null}
              aria-describedby="name-help"
              className="h-9 rounded-lg"
              autoFocus
            />
            <p id="name-help" className={nameError ? "text-[12px] text-destructive" : "text-[12px] text-muted-foreground"}>
              {nameError ?? "Used by the CLI: tracebench eval run <name>"}
            </p>
          </div>
          <div className="space-y-2">
            <Label htmlFor="description" className="text-[13px]">
              Description
            </Label>
            <Textarea
              id="description"
              value={description}
              onChange={(event) => setDescription(event.target.value)}
              placeholder="What this dataset protects against"
              className="min-h-20 rounded-lg"
            />
          </div>
          <fieldset className="space-y-2">
            <legend className="text-[13px] font-medium">Default scorers</legend>
            <div className="divide-y divide-border/60 rounded-xl ring-1 ring-border/60">
              {SCORERS.map((scorer) => (
                <label key={scorer.id} className="flex cursor-pointer items-start gap-3 px-3 py-2.5">
                  <Checkbox
                    checked={selected.has(scorer.id)}
                    onCheckedChange={(checked) =>
                      setSelected((prev) => {
                        const next = new Set(prev)
                        if (checked === true) next.add(scorer.id)
                        else next.delete(scorer.id)
                        return next
                      })
                    }
                    className="mt-0.5"
                  />
                  <span>
                    <span className="block text-[13px] font-medium">{scorer.label}</span>
                    <span className="block text-[12px] text-muted-foreground">{scorer.help}</span>
                  </span>
                </label>
              ))}
            </div>
          </fieldset>
          <DialogFooter className="gap-2">
            <Button type="button" variant="secondary" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={!name || nameError !== null || create.isPending}>
              {create.isPending ? "Creating…" : "Create dataset"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
