/** The signing secret is shown once, for the webhook that was just added. */
export type FreshSecret = { id: number; url: string; secret: string };

/** What is left to show after a webhook is deleted: the secret goes with its webhook. */
export function secretAfterDelete(fresh: FreshSecret | null, deletedId: number): FreshSecret | null {
  return fresh && fresh.id === deletedId ? null : fresh;
}
