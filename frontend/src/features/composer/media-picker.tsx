import { useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Check, Upload } from "lucide-react";
import { toast } from "sonner";
import { keys, uploadMedia, useMedia, type MediaOut } from "@/features/posts/api";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

/** Pick from the brand's library or upload; returns the chosen items. */
export function MediaPicker({ brandId, open, onOpenChange, selectedIds, onPick }: {
  brandId: number; open: boolean; onOpenChange: (o: boolean) => void; selectedIds: number[]; onPick: (items: MediaOut[]) => void;
}) {
  const { data, isPending } = useMedia(brandId, open);
  const [chosen, setChosen] = useState<MediaOut[]>([]);
  const [busy, setBusy] = useState(0);
  const qc = useQueryClient();
  const fileRef = useRef<HTMLInputElement>(null);

  const toggle = (m: MediaOut) => setChosen((c) => c.some((x) => x.id === m.id) ? c.filter((x) => x.id !== m.id) : [...c, m]);
  const done = () => { onPick(chosen); setChosen([]); onOpenChange(false); };

  async function upload(files: FileList | null) {
    if (!files?.length) return;
    setBusy(files.length);
    for (const f of Array.from(files)) {
      try {
        const items = await uploadMedia(brandId, f, () => undefined);
        setChosen((c) => [...c, ...items]);
      } catch (e) { toast.error(e instanceof Error ? e.message : "Upload failed"); }
      setBusy((b) => b - 1);
    }
    void qc.invalidateQueries({ queryKey: keys.media(brandId) });
  }

  return (
    <Dialog open={open} onOpenChange={(o) => { if (!o) setChosen([]); onOpenChange(o); }}>
      <DialogContent className="max-h-[85vh] sm:max-w-2xl">
        <DialogHeader className="flex-row items-center justify-between gap-3 pr-6">
          <DialogTitle>Media library</DialogTitle>
          <Button size="sm" variant="outline" onClick={() => fileRef.current?.click()} disabled={busy > 0}>
            <Upload className="size-4" />{busy ? `Uploading ${busy}…` : "Upload"}
          </Button>
          <input ref={fileRef} type="file" className="sr-only" multiple accept="image/*,video/mp4,video/quicktime" onChange={(e) => { void upload(e.target.files); e.target.value = ""; }} />
        </DialogHeader>
        <div className="grid max-h-[55vh] grid-cols-3 gap-2 overflow-y-auto p-0.5 sm:grid-cols-5">
          {isPending && Array.from({ length: 10 }).map((_, i) => <Skeleton key={i} className="aspect-square" />)}
          {data?.items.map((m) => {
            const picked = chosen.some((x) => x.id === m.id);
            const already = selectedIds.includes(m.id);
            return (
              <button key={m.id} type="button" onClick={() => !already && toggle(m)} disabled={already} title={m.name}
                      className={cn("relative aspect-square overflow-hidden rounded-control border bg-hover", picked ? "border-brand ring-2 ring-brand" : "border-line", already && "opacity-40")}>
                {m.is_video ? <span className="grid h-full place-items-center text-xs text-ink-2">▶ video</span> : <img src={m.url} alt={m.alt_text ?? ""} className="h-full w-full object-cover" />}
                {(picked || already) && <span className="absolute right-1 top-1 grid size-5 place-items-center rounded-full bg-brand text-brand-fg"><Check className="size-3" /></span>}
              </button>
            );
          })}
          {data && data.items.length === 0 && <p className="col-span-full py-10 text-center text-sm text-ink-2">No media yet. Upload images or videos to reuse them across posts.</p>}
        </div>
        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button onClick={done} disabled={!chosen.length}>Add {chosen.length || ""}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
