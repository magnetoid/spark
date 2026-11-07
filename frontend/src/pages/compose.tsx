/** Full-page composer at /compose and /posts/:id/edit, the same component as the dialog. */
import { useNavigate, useParams, useSearch } from "@tanstack/react-router";
import { PageHeader } from "@/components/page";
import { ComposerLoader } from "@/features/composer/composer-host";

export function ComposePage() {
  const navigate = useNavigate();
  const search = useSearch({ strict: false }) as { account?: string; at?: string };
  const back = () => void navigate({ to: "/publishing", search: (p: Record<string, unknown>) => p });
  return (
    <>
      <PageHeader title="New post" />
      <ComposerLoader key={`${search.account ?? ""}-${search.at ?? ""}`} compact={false}
                      opts={{ account: search.account ? Number(search.account) : undefined, at: search.at, onSaved: back }} onDone={back} />
    </>
  );
}

export function EditPostPage() {
  const { postId } = useParams({ strict: false }) as { postId: string };
  const navigate = useNavigate();
  const back = () => void navigate({ to: "/publishing", search: (p: Record<string, unknown>) => p });
  return (
    <>
      <PageHeader title="Edit post" />
      <ComposerLoader key={postId} compact={false} opts={{ postId: Number(postId), onSaved: back }} onDone={back} />
    </>
  );
}
