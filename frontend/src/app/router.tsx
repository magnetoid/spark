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
import { TwoFactorPage } from "@/pages/two-factor";
import { ReviewPage } from "@/pages/review";
import { ReportPage } from "@/pages/report";
import { TodayPage } from "@/pages/today";
import { PublishingPage } from "@/pages/publishing";
import { IdeasPage } from "@/pages/ideas";
import { LibraryPage } from "@/pages/library";
import { ComposePage, EditPostPage } from "@/pages/compose";
import { AnalyticsPage } from "@/pages/analytics";
import { CampaignsPage } from "@/pages/campaigns";
import { LinksPage } from "@/pages/links";
import { AudiencePage } from "@/pages/audience";
import { ChannelsPage } from "@/pages/channels";
import { SettingsPage } from "@/pages/settings";
import { InboxPage } from "@/pages/inbox";
import { NewBrandPage } from "@/pages/new-brand";
import { sessionQuery } from "@/app/session";

interface RouterContext {
  queryClient: QueryClient;
}

const rootRoute = createRootRouteWithContext<RouterContext>()({
  component: () => <Outlet />,
  validateSearch: (s: Record<string, unknown>): { brand?: string; view?: string; account?: string; cal?: string; month?: string; campaign?: string; tab?: string; at?: string; connector?: string; notice?: string; kind?: string } =>
    Object.fromEntries(Object.entries(s).filter(([k, v]) => ["brand", "view", "account", "cal", "month", "campaign", "tab", "at", "connector", "notice", "kind"].includes(k) && typeof v === "string" && v)) as { brand?: string },
});

const loginRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/login",
  validateSearch: (s: Record<string, unknown>): { next?: string } =>
    typeof s.next === "string" && s.next ? { next: s.next } : {},
  component: LoginPage,
});

const setupRoute = createRoute({ getParentRoute: () => rootRoute, path: "/setup", component: SetupPage });
const twoFactorRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/two-factor",
  beforeLoad: async ({ context }) => {
    // asked fresh: a cached session may predate the owner switching the rule on
    const session = await context.queryClient.fetchQuery({ ...sessionQuery, staleTime: 0 });
    if (!session.user) throw redirect({ to: "/login", search: { next: "/two-factor" } });
    if (session.user.two_factor) throw redirect({ to: "/" });
  },
  component: TwoFactorPage,
});
const reviewRoute = createRoute({ getParentRoute: () => rootRoute, path: "/review/$token", component: ReviewPage });
const reportRoute = createRoute({ getParentRoute: () => rootRoute, path: "/brands/$brandId/reports/$reportId", component: ReportPage });

const shellRoute = createRoute({
  id: "shell",
  getParentRoute: () => rootRoute,
  beforeLoad: async ({ context, location }) => {
    const session = await context.queryClient.ensureQueryData(sessionQuery);
    if (session.needs_setup) throw redirect({ to: "/setup" });
    if (!session.user) throw redirect({ to: "/login", search: { next: location.href } });
    if (session.two_factor_setup_required) throw redirect({ to: "/two-factor" });
    if (session.brands.length === 0 && !location.pathname.startsWith("/brands/new")) throw redirect({ to: "/brands/new" });
    return { session };
  },
  component: AppShell,
});

const page = <P extends string>(path: P, component: () => React.JSX.Element) =>
  createRoute({ getParentRoute: () => shellRoute, path, component });

export const routeTree = rootRoute.addChildren([
  loginRoute,
  setupRoute,
  twoFactorRoute,
  reviewRoute,
  reportRoute,
  shellRoute.addChildren([
    page("/", TodayPage),
    page("/brands/new", NewBrandPage),
    page("/publishing", PublishingPage),
    page("/compose", ComposePage),
    page("/posts/$postId/edit", EditPostPage),
    page("/inbox", InboxPage),
    page("/ideas", IdeasPage),
    page("/library", LibraryPage),
    page("/analytics", AnalyticsPage),
    page("/campaigns", CampaignsPage),
    page("/links", LinksPage),
    page("/audience", AudiencePage),
    page("/channels", ChannelsPage),
    page("/settings", SettingsPage),
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
