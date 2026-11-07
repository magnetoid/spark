import { Link } from "@tanstack/react-router";
import {
  BarChart3, Check, ChevronsUpDown, Inbox, LayoutGrid, Lightbulb, Link2, LogOut, Megaphone, Moon,
  PanelLeftClose, PanelLeftOpen, Plug, Settings, Sun, SunMoon, Sunrise, Users, type LucideIcon,
} from "lucide-react";
import { readTheme, setTheme, useWorkspace, type ThemeMode } from "@/app/session";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import { useState } from "react";

interface NavItem { to: string; label: string; icon: LucideIcon }

const WORK: NavItem[] = [
  { to: "/", label: "Today", icon: Sunrise },
  { to: "/publishing", label: "Publishing", icon: LayoutGrid },
  { to: "/inbox", label: "Inbox", icon: Inbox },
  { to: "/ideas", label: "Ideas", icon: Lightbulb },
  { to: "/library", label: "Library", icon: Plug },
  { to: "/analytics", label: "Analytics", icon: BarChart3 },
];
const GROW: NavItem[] = [
  { to: "/campaigns", label: "Campaigns", icon: Megaphone },
  { to: "/links", label: "Links", icon: Link2 },
  { to: "/audience", label: "Audience", icon: Users },
];
const SETUP: NavItem[] = [
  { to: "/channels", label: "Channels", icon: Plug },
  { to: "/settings", label: "Settings", icon: Settings },
];

export function Sidebar({ collapsed, onToggle }: { collapsed: boolean; onToggle: () => void }) {
  const { brand, brands, setBrand, user, signOut } = useWorkspace();
  const client = brand?.role === "client";
  const only = (items: NavItem[]) => client ? items.filter((i) => ["/", "/publishing", "/analytics", "/settings"].includes(i.to)) : items;
  const [theme, setThemeState] = useState<ThemeMode>(readTheme);
  const changeTheme = (m: ThemeMode) => { setTheme(m); setThemeState(m); };

  return (
    <nav aria-label="Main" className="flex h-full flex-col">
      <div className="p-2">
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <button type="button" className={cn("flex w-full items-center gap-2.5 rounded-card px-2 py-2 text-left hover:bg-hover", collapsed && "justify-center px-0")}
                    aria-label={brand ? `Workspace: ${brand.name}` : "Workspaces"}>
              <span className="size-7 shrink-0 rounded-control" style={{ background: brand?.color ?? "var(--brand)" }} aria-hidden />
              {!collapsed && (
                <>
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-sm font-medium">{brand?.name ?? "No brand yet"}</span>
                    <span className="block truncate text-xs text-ink-2">{brands.length} {brands.length === 1 ? "brand" : "brands"}</span>
                  </span>
                  <ChevronsUpDown className="size-4 text-ink-2" />
                </>
              )}
            </button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="start" className="w-60">
            <DropdownMenuLabel>Switch brand</DropdownMenuLabel>
            {brands.map((b) => (
              <DropdownMenuItem key={b.id} onSelect={() => setBrand(b.slug)}>
                <span className="size-3 rounded-full" style={{ background: b.color }} aria-hidden />
                <span className="flex-1 truncate">{b.name}</span>
                {b.id === brand?.id && <Check className="size-4" />}
              </DropdownMenuItem>
            ))}
            <DropdownMenuSeparator />
            {user.role === "owner" && <DropdownMenuItem asChild><Link to="/brands/new">Add a brand</Link></DropdownMenuItem>}
          </DropdownMenuContent>
        </DropdownMenu>
      </div>

      <div className="flex-1 space-y-4 overflow-y-auto px-2">
        <Group items={only(WORK)} collapsed={collapsed} />
        {!client && <Group items={GROW} collapsed={collapsed} label="Grow" />}
        <Group items={only(SETUP)} collapsed={collapsed} label={client ? undefined : "Set up"} />
      </div>

      <div className="border-t border-line p-2">
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <button type="button" className={cn("flex w-full items-center gap-2.5 rounded-card px-2 py-1.5 text-left hover:bg-hover", collapsed && "justify-center px-0")} aria-label="Account menu">
              <span className="grid size-7 shrink-0 place-items-center rounded-full bg-hover text-xs font-semibold">{initials(user.name)}</span>
              {!collapsed && <span className="min-w-0 flex-1"><span className="block truncate text-sm">{user.name}</span><span className="block truncate text-xs text-ink-2">{brand?.role ?? user.role}</span></span>}
            </button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="start" side="top" className="w-56">
            <DropdownMenuItem asChild><Link to="/settings" search={(p) => ({ ...p, tab: "me" })}>Preferences</Link></DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuLabel className="text-xs font-normal text-ink-2">Theme</DropdownMenuLabel>
            <DropdownMenuItem onSelect={() => changeTheme("light")}><Sun className="size-4" />Light {theme === "light" && <Check className="ml-auto size-4" />}</DropdownMenuItem>
            <DropdownMenuItem onSelect={() => changeTheme("dark")}><Moon className="size-4" />Dark {theme === "dark" && <Check className="ml-auto size-4" />}</DropdownMenuItem>
            <DropdownMenuItem onSelect={() => changeTheme("system")}><SunMoon className="size-4" />System {theme === "system" && <Check className="ml-auto size-4" />}</DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem onSelect={() => void signOut()}><LogOut className="size-4" />Sign out</DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
        <Button variant="ghost" size="sm" className="mt-1 hidden w-full justify-center text-ink-2 md:flex" onClick={onToggle}
                aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}>
          {collapsed ? <PanelLeftOpen className="size-4" /> : <PanelLeftClose className="size-4" />}
        </Button>
      </div>
    </nav>
  );
}

function Group({ items, collapsed, label }: { items: NavItem[]; collapsed: boolean; label?: string }) {
  return (
    <div>
      {label && !collapsed && <div className="px-2.5 pb-1 pt-2 text-[11px] font-medium text-ink-2">{label}</div>}
      {label && collapsed && <div className="mx-2 my-2 border-t border-line" />}
      <ul className="space-y-0.5">
        {items.map((it) => (
          <li key={it.to}>
            <Tooltip>
              <TooltipTrigger asChild>
                <Link to={it.to} search={(prev) => prev} className={cn("nav-item", collapsed && "justify-center px-0")}
                      activeOptions={{ exact: it.to === "/" }} activeProps={{ "aria-current": "page" }}>
                  <it.icon className="size-4 shrink-0" aria-hidden />
                  {!collapsed && <span>{it.label}</span>}
                </Link>
              </TooltipTrigger>
              {collapsed && <TooltipContent side="right">{it.label}</TooltipContent>}
            </Tooltip>
          </li>
        ))}
      </ul>
    </div>
  );
}

function initials(name: string) {
  return name.split(/\s+/).filter(Boolean).slice(0, 2).map((p) => p[0]?.toUpperCase()).join("") || "?";
}
