import { ArrowUpRight } from "lucide-react";
import { PageHeader } from "@/components/page";
import { Button } from "@/components/ui/button";

/** A page that still lives in the server-rendered app. Honest, one click away, no dead ends. */
export function ClassicPage({ title, href, blurb }: { title: string; href: string; blurb: string }) {
  return (
    <>
      <PageHeader title={title} description={blurb} />
      <div className="rounded-card border border-line bg-surface p-6">
        <p className="text-sm text-ink-2">This page moves into the new app in an upcoming release. Until then it opens in the current Spark, with the same data.</p>
        <Button asChild className="mt-4"><a href={href}>Open {title}<ArrowUpRight className="size-4" /></a></Button>
      </div>
    </>
  );
}
