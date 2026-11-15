/** Copy one brand's setup into another: on a new brand, or later from Settings. */
import { useState } from "react";
import { useWorkspace } from "@/app/session";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { SETUP_PARTS, useCopySetup, type SetupPart } from "@/features/agency/api";

const ALL = SETUP_PARTS.map((p) => p.key);

/** Brands the person may copy from: ones they own or edit, other than `exclude`. */
export function useCopySources(exclude?: number) {
  const { brands } = useWorkspace();
  return brands.filter((b) => b.id !== exclude && (b.role === "owner" || b.role === "editor"));
}

export function PartPicker({ value, onChange, idPrefix }: { value: SetupPart[]; onChange: (v: SetupPart[]) => void; idPrefix: string }) {
  const toggle = (k: SetupPart) => onChange(value.includes(k) ? value.filter((x) => x !== k) : [...value, k]);
  return (
    <fieldset className="grid gap-2 sm:grid-cols-2">
      <legend className="sr-only">What to copy</legend>
      {SETUP_PARTS.map((p) => (
        <label key={p.key} htmlFor={`${idPrefix}-${p.key}`} className="flex items-start gap-2 rounded-control border border-line px-3 py-2 text-sm has-[:checked]:border-brand">
          <input id={`${idPrefix}-${p.key}`} type="checkbox" className="mt-0.5 accent-[var(--brand)]" checked={value.includes(p.key)} onChange={() => toggle(p.key)} />
          <span>{p.label}<span className="block text-xs text-ink-2">{p.hint}</span></span>
        </label>
      ))}
    </fieldset>
  );
}

export function SourceSelect({ value, onChange, sources, blank, id }: {
  value: string; onChange: (v: string) => void; sources: { id: number; name: string; color: string }[]; blank?: string; id: string;
}) {
  return (
    <Select value={value} onValueChange={onChange}>
      <SelectTrigger id={id}><SelectValue placeholder="Pick a brand" /></SelectTrigger>
      <SelectContent>
        {blank && <SelectItem value="none">{blank}</SelectItem>}
        {sources.map((b) => (
          <SelectItem key={b.id} value={String(b.id)}>
            <span className="inline-flex items-center gap-2"><span className="size-2.5 rounded-full" style={{ background: b.color }} aria-hidden />{b.name}</span>
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}

/** The Settings card: pick a brand, pick the parts, copy. */
export function CopySetupCard({ brandId }: { brandId: number }) {
  const sources = useCopySources(brandId);
  const [from, setFrom] = useState("");
  const [parts, setParts] = useState<SetupPart[]>(ALL);
  const copy = useCopySetup(brandId);
  if (!sources.length) return null;
  return (
    <section aria-labelledby="copy-setup-h" className="space-y-4 rounded-card border border-line bg-surface p-5">
      <div>
        <h2 id="copy-setup-h" className="font-semibold">Copy setup from another brand</h2>
        <p className="text-sm text-ink-2">Things this brand already has (same name) are skipped, so copying twice adds nothing.</p>
      </div>
      <div className="max-w-xs space-y-1.5"><Label htmlFor="cs-from">Copy from</Label><SourceSelect id="cs-from" value={from} onChange={setFrom} sources={sources} /></div>
      <PartPicker value={parts} onChange={setParts} idPrefix="cs" />
      <Button type="button" disabled={!from || !parts.length || copy.isPending} onClick={() => copy.mutate({ from: Number(from), parts })}>
        {copy.isPending ? "Copying…" : "Copy setup"}
      </Button>
    </section>
  );
}

export { ALL as ALL_SETUP_PARTS };
