import { useEffect, useState } from "react";
import { Outlet } from "@tanstack/react-router";
import { useSession, WorkspaceProvider } from "@/app/session";
import { Sidebar } from "@/components/shell/sidebar";
import { Topbar } from "@/components/shell/topbar";
import { Sheet, SheetContent, SheetTitle } from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";

const COLLAPSE_KEY = "spark.sidebar";

export function AppShell() {
  const { data: session } = useSession();
  const [collapsed, setCollapsed] = useState(() => {
    try { return localStorage.getItem(COLLAPSE_KEY) === "1"; } catch { return false; }
  });
  const [mobileOpen, setMobileOpen] = useState(false);

  useEffect(() => {
    try { localStorage.setItem(COLLAPSE_KEY, collapsed ? "1" : "0"); } catch { /* ignore */ }
  }, [collapsed]);

  if (!session) return <ShellSkeleton />;

  return (
    <WorkspaceProvider session={session}>
      <div className="flex min-h-dvh">
        <aside className={`brand-rail hidden md:flex sticky top-0 h-dvh shrink-0 flex-col border-r border-line bg-surface transition-[width] ${collapsed ? "w-[3.75rem]" : "w-60"}`}>
          <Sidebar collapsed={collapsed} onToggle={() => setCollapsed((c) => !c)} />
        </aside>
        <Sheet open={mobileOpen} onOpenChange={setMobileOpen}>
          <SheetContent side="left" className="w-72 p-0 brand-rail">
            <SheetTitle className="sr-only">Navigation</SheetTitle>
            {/* any link tap closes the drawer; no effect on route change needed */}
            <div className="h-full" onClickCapture={(e) => { if ((e.target as HTMLElement).closest("a")) setMobileOpen(false); }}>
              <Sidebar collapsed={false} onToggle={() => setMobileOpen(false)} />
            </div>
          </SheetContent>
        </Sheet>
        <div className="flex min-w-0 flex-1 flex-col">
          <Topbar onMenu={() => setMobileOpen(true)} />
          <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-6 md:px-8">
            <Outlet />
          </main>
        </div>
      </div>
    </WorkspaceProvider>
  );
}

function ShellSkeleton() {
  return (
    <div className="flex min-h-dvh">
      <div className="hidden w-60 border-r border-line bg-surface p-4 md:block">
        <Skeleton className="mb-6 h-9 w-full" />
        {Array.from({ length: 7 }).map((_, i) => <Skeleton key={i} className="mb-2 h-7 w-full" />)}
      </div>
      <div className="flex-1 p-8"><Skeleton className="h-8 w-56" /><Skeleton className="mt-6 h-40 w-full" /></div>
    </div>
  );
}
