"use client"

import { Play } from "lucide-react"
import { useRouter } from "next/navigation"
import { useEffect, useState, type FormEvent } from "react"
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
import { useExecuteRun } from "@/lib/api/hooks"

const STORAGE_KEY = "tracebench.target-url"

function readStored(): string {
  try {
    return window.localStorage.getItem(STORAGE_KEY) ?? ""
  } catch {
    return ""
  }
}

function store(value: string) {
  try {
    window.localStorage.setItem(STORAGE_KEY, value)
  } catch {
    // Storage can be unavailable (private mode); remembering the URL is only a convenience.
  }
}

export function RunEvalDialog({ datasetId, disabled }: { datasetId: string; disabled: boolean }) {
  const router = useRouter()
  const execute = useExecuteRun()
  const [open, setOpen] = useState(false)
  const [target, setTarget] = useState("")
  const [name, setName] = useState("")

  useEffect(() => {
    if (open) setTarget((current) => current || readStored() || "http://localhost:6405/support")
  }, [open])

  let urlError: string | null = null
  try {
    if (target) new URL(target)
  } catch {
    urlError = "Enter a full URL, including http:// or https://"
  }

  const submit = (event: FormEvent) => {
    event.preventDefault()
    if (!target || urlError) return
    store(target)
    execute.mutate(
      { dataset_id: datasetId, target_url: target, name: name.trim() || undefined },
      {
        onSuccess: (run) => {
          setOpen(false)
          toast.success("Eval run started")
          router.push(`/evals/${run.id}`)
        },
        onError: (error) => toast.error("Couldn't start the run", { description: error.message }),
      }
    )
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button disabled={disabled}>
          <Play strokeWidth={1.75} />
          Run eval
        </Button>
      </DialogTrigger>
      <DialogContent className="rounded-2xl sm:max-w-md">
        <form onSubmit={submit} className="space-y-5">
          <DialogHeader>
            <DialogTitle className="text-[17px]">Run this dataset</DialogTitle>
            <DialogDescription className="text-[13px]">
              Tracebench POSTs each case&apos;s input to your app and scores what comes back. In CI, use{" "}
              <code className="font-mono text-[12px]">tracebench eval run</code> instead.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-2">
            <Label htmlFor="target" className="text-[13px]">
              Target endpoint
            </Label>
            <Input
              id="target"
              value={target}
              onChange={(event) => setTarget(event.target.value)}
              aria-invalid={urlError !== null}
              aria-describedby="target-help"
              className="h-9 rounded-lg font-mono text-[13px]"
            />
            <p id="target-help" className={urlError ? "text-[12px] text-destructive" : "text-[12px] text-muted-foreground"}>
              {urlError ??
                "Must accept the case input as JSON and reply with {\"output\": ...}. The API only calls hosts on its allowlist (localhost in development)."}
            </p>
          </div>
          <div className="space-y-2">
            <Label htmlFor="run-name" className="text-[13px]">
              Label <span className="font-normal text-muted-foreground">(optional)</span>
            </Label>
            <Input
              id="run-name"
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder="Prompt v3 with shorter system message"
              className="h-9 rounded-lg"
            />
          </div>
          <DialogFooter className="gap-2">
            <Button type="button" variant="secondary" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={!target || urlError !== null || execute.isPending}>
              {execute.isPending ? "Starting…" : "Start run"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
