import { useEffect, useState } from "react";
import { useNavigate, useRouterState } from "@tanstack/react-router";
import { Menu, Plus, Search } from "lucide-react";
import { useWorkspace } from "@/app/session";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { useComposer } from "@/features/composer/composer-host";

const PAGES = [
  ["Today", "/"], ["Publishing", "/publishing"], ["Inbox", "/inbox"], ["Ideas", "/ideas"], ["Library", "/library"],
  ["Analytics", "/analytics"], ["Campaigns", "/campaigns"], ["Links", "/links"], ["Audience", "/audience"],
  ["Channels", "/channels"], ["Settings", "/settings"],
] as const;

export function Topbar({ onMenu }: { onMenu: () => void }) {
  const { brand, brands, setBrand } = useWorkspace();
  const pathname = useRouterState({ select: (s) => s.location.pathname });
  const page = PAGES.find(([, to]) => to === pathname)?.[0] ?? "Spark";
  const [open, setOpen] = useState(false);
  const composer = useComposer();

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") { e.preventDefault(); setOpen(true); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  return (
    <header className="sticky top-0 z-20 flex h-12 items-center gap-2 border-b border-line bg-paper/85 px-3 backdrop-blur md:px-6">
      <Button variant="ghost" size="icon" className="md:hidden" onClick={onMenu} aria-label="Open navigation"><Menu className="size-5" /></Button>
      <div className="hidden min-w-0 items-center gap-1.5 text-sm text-ink-2 sm:flex">
        <span className="truncate">{brand?.name}</span><span aria-hidden>/</span><span className="truncate text-ink">{page}</span>
      </div>
      <button type="button" onClick={() => setOpen(true)}
              className="ml-auto flex h-8 w-full max-w-sm items-center gap-2 rounded-control border border-line bg-surface px-2.5 text-left text-sm text-ink-2 hover:border-line-strong">
        <Search className="size-4" /><span className="flex-1 truncate">Jump to a page or brand…</span>
        <kbd className="hidden rounded border border-line px-1 text-[10px] sm:inline">⌘K</kbd>
      </button>
      <Button size="sm" onClick={() => composer.open()}><Plus className="size-4" />New post</Button>
      <JumpDialog open={open} onOpenChange={setOpen} brands={brands} onBrand={setBrand} />
    </header>
  );
}

function JumpDialog({ open, onOpenChange, brands, onBrand }: {
  open: boolean; onOpenChange: (o: boolean) => void; brands: { slug: string; name: string; color: string }[]; onBrand: (slug: string) => void;
}) {
  const [q, setQ] = useState("");
  const navigate = useNavigate();
  const needle = q.trim().toLowerCase();
  const pages = PAGES.filter(([label]) => label.toLowerCase().includes(needle));
  const matches = brands.filter((b) => b.name.toLowerCase().includes(needle));
  const close = (o: boolean) => { if (!o) setQ(""); onOpenChange(o); };
  return (
    <Dialog open={open} onOpenChange={close}>
      <DialogContent className="top-[20%] translate-y-0 gap-0 p-0 sm:max-w-md" showCloseButton={false}>
        <DialogTitle className="sr-only">Jump to</DialogTitle>
        <Input autoFocus value={q} onChange={(e) => setQ(e.target.value)} placeholder="Type a page or a brand"
               className="h-11 rounded-none border-0 border-b border-line shadow-none focus-visible:ring-0" />
        <ul className="max-h-80 overflow-y-auto p-1 text-sm">
          {pages.map(([label, to]) => (
            <li key={to}><button type="button" className="nav-item w-full" onClick={() => { close(false); void navigate({ to, search: (p) => p }); }}>{label}</button></li>
          ))}
          {matches.length > 0 && <li className="px-2.5 pb-1 pt-2 text-[11px] text-ink-2">Brands</li>}
          {matches.map((b) => (
            <li key={b.slug}><button type="button" className="nav-item w-full" onClick={() => { close(false); onBrand(b.slug); }}>
              <span className="size-3 rounded-full" style={{ background: b.color }} aria-hidden />{b.name}
            </button></li>
          ))}
          {pages.length === 0 && matches.length === 0 && <li className="px-2.5 py-6 text-center text-ink-2">Nothing matches “{q}”</li>}
        </ul>
      </DialogContent>
    </Dialog>
  );
}
