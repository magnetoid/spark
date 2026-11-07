/**
 * Routes, written in code rather than generated from files: one place to read the whole
 * map of the app, and no codegen step before typecheck.
 *
 * Paths mirror the server-rendered app (/publishing, /posts/:id/edit …) so links in
 * emails and MCP answers keep working after the cutover.
 */
import { createRootRouteWithContext, createRoute, createRouter, Outlet, redirect } from "@tanstack/react-router";
import type { QueryClient } from "@tanstack/react-query";
import { AppShell } from "@/components/shell/app-shell";
import { LoginPage } from "@/pages/login";
import { SetupPage } from "@/pages/setup";
import { TodayPage } from "@/pages/today";
import { ClassicPage } from "@/pages/classic";
import { sessionQuery } from "@/app/session";

interface RouterContext {
  queryClient: QueryClient;
}

const rootRoute = createRootRouteWithContext<RouterContext>()({
  component: () => <Outlet />,
  validateSearch: (s: Record<string, unknown>): { brand?: string } =>
    typeof s.brand === "string" && s.brand ? { brand: s.brand } : {},
});

const loginRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/login",
  validateSearch: (s: Record<string, unknown>): { next?: string } =>
    typeof s.next === "string" && s.next ? { next: s.next } : {},
  component: LoginPage,
});

const setupRoute = createRoute({ getParentRoute: () => rootRoute, path: "/setup", component: SetupPage });

const shellRoute = createRoute({
  id: "shell",
  getParentRoute: () => rootRoute,
  beforeLoad: async ({ context, location }) => {
    const session = await context.queryClient.ensureQueryData(sessionQuery);
    if (session.needs_setup) throw redirect({ to: "/setup" });
    if (!session.user) throw redirect({ to: "/login", search: { next: location.href } });
    return { session };
  },
  component: AppShell,
});

const page = <P extends string>(path: P, component: () => React.JSX.Element) =>
  createRoute({ getParentRoute: () => shellRoute, path, component });

/** Pages that still live in the server-rendered app, one card each until their phase lands. */
const classic = <P extends string>(path: P, title: string, href: string, blurb: string) =>
  createRoute({
    getParentRoute: () => shellRoute,
    path,
    component: () => <ClassicPage title={title} href={href} blurb={blurb} />,
  });

export const routeTree = rootRoute.addChildren([
  loginRoute,
  setupRoute,
  shellRoute.addChildren([
    page("/", TodayPage),
    classic("/publishing", "Publishing", "/queue", "Queue, calendar, drafts, approvals and sent posts."),
    classic("/inbox", "Inbox", "/inbox", "Comments and replies across your channels."),
    classic("/ideas", "Ideas", "/ideas", "The idea board, from a note to a ready post."),
    classic("/library", "Library", "/media", "Media, templates and hashtag groups."),
    classic("/analytics", "Analytics", "/analytics", "Impressions, engagement, best times and link clicks."),
    classic("/campaigns", "Campaigns", "/campaigns", "Group posts under a goal and track them together."),
    classic("/links", "Links", "/links", "Tracked short links, UTM tags and your bio page."),
    classic("/audience", "Audience", "/contacts", "Contacts, lists and email campaigns."),
    classic("/channels", "Channels", "/accounts", "Connected social accounts."),
    classic("/settings", "Settings", "/settings", "Brand, team, connectors and your preferences."),
  ]),
]);

export function makeRouter(queryClient: QueryClient) {
  return createRouter({
    routeTree,
    context: { queryClient },
    basepath: import.meta.env.BASE_URL.replace(/\/$/, "") || "/",
    defaultPreload: "intent",
    scrollRestoration: true,
  });
}

declare module "@tanstack/react-router" {
  interface Register {
    router: ReturnType<typeof makeRouter>;
  }
}
