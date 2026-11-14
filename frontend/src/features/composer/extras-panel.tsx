/**
 * Per-channel extras in the composer: AI label, paid partnership, collaborators, poll.
 * Each control shows only on channels whose network carries it.
 */
import { useState } from "react";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import type { AccountOut, MediaOut } from "@/features/posts/api";
import { aiLabel, cleanExtras, parsePeople, pollRules, type Extras, type Poll } from "@/features/composer/extras";

const LINK = "text-ink-2 underline-offset-2 hover:text-ink hover:underline";
const DAYS: Record<number, string> = { 1: "1 day", 3: "3 days", 7: "1 week", 14: "2 weeks" };

export function ChannelExtras({ account, value, media, onChange }: {
  account: AccountOut; value: Extras | undefined; media: MediaOut[]; onChange: (next: Extras) => void;
}) {
  const keys = account.capabilities.options ?? [];
  const extras = cleanExtras(value);
  const [people, setPeople] = useState(extras.collaborators.map((p) => `@${p}`).join(", "));
  const [peopleOpen, setPeopleOpen] = useState(extras.collaborators.length > 0);
  if (!keys.length) return null;

  const rules = pollRules(account.platform);
  const patch = (p: Partial<Extras>) => onChange({ ...extras, ...p });
  const poll = extras.poll;
  const setPoll = (p: Partial<Poll>) => poll && patch({ poll: { ...poll, ...p } });
  const auto = extras.ai_generated == null && aiLabel(extras, media);

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5">
        {keys.includes("ai_generated") && (
          <label className="flex cursor-pointer items-center gap-1.5">
            <input type="checkbox" className="accent-[var(--brand)]" checked={aiLabel(extras, media)} onChange={(e) => patch({ ai_generated: e.target.checked })} />
            Label as AI-generated{auto && <span className="text-ink-2">(your media was made with AI)</span>}
          </label>
        )}
        {keys.includes("paid_partnership") && (
          <label className="flex cursor-pointer items-center gap-1.5">
            <input type="checkbox" className="accent-[var(--brand)]" checked={extras.paid_partnership} onChange={(e) => patch({ paid_partnership: e.target.checked })} />
            Paid partnership
          </label>
        )}
        {keys.includes("collaborators") && !peopleOpen && <button type="button" className={LINK} onClick={() => setPeopleOpen(true)}>+ Collaborators</button>}
        {keys.includes("poll") && !poll && <button type="button" className={LINK} onClick={() => patch({ poll: { question: "", options: ["", ""], days: 3 } })}>+ Poll</button>}
      </div>

      {keys.includes("collaborators") && peopleOpen && (
        <div className="space-y-1">
          <div className="flex items-center justify-between">
            <label className="font-medium" htmlFor={`collab-${account.id}`}>Collaborators</label>
            <button type="button" className="text-ink-2 underline" onClick={() => { setPeople(""); setPeopleOpen(false); patch({ collaborators: [] }); }}>Remove</button>
          </div>
          <Input id={`collab-${account.id}`} className="h-8 text-sm" value={people} placeholder="@username, @another"
            onChange={(e) => { setPeople(e.target.value); patch({ collaborators: parsePeople(e.target.value) }); }} />
          <p className="text-ink-2">Up to 3 accounts. Each one gets an invitation and the post shows on their profile once they accept.</p>
        </div>
      )}

      {keys.includes("poll") && poll && (
        <div className="space-y-1.5 rounded-control border border-line p-2.5">
          <div className="flex items-center justify-between">
            <span className="font-medium">Poll</span>
            <button type="button" className="text-ink-2 underline" onClick={() => patch({ poll: null })}>Remove poll</button>
          </div>
          {rules.questionChars > 0 && (
            <Input className="h-8 text-sm" value={poll.question} maxLength={rules.questionChars} aria-label="Poll question"
              placeholder="Question (the first line of the post if left empty)" onChange={(e) => setPoll({ question: e.target.value })} />
          )}
          {poll.options.map((option, i) => (
            <div key={i} className="flex items-center gap-2">
              <Input className="h-8 text-sm" value={option} maxLength={rules.optionChars} aria-label={`Poll option ${i + 1}`} placeholder={`Option ${i + 1}`}
                onChange={(e) => setPoll({ options: poll.options.map((o, j) => (j === i ? e.target.value : o)) })} />
              <span className="w-10 text-right text-ink-2 tnum">{option.length}/{rules.optionChars}</span>
              {poll.options.length > 2 && <button type="button" className="text-ink-2 hover:text-st-failed" onClick={() => setPoll({ options: poll.options.filter((_, j) => j !== i) })}>remove</button>}
            </div>
          ))}
          <div className="flex items-center justify-between pt-0.5">
            {poll.options.length < 4 ? <button type="button" className="text-brand" onClick={() => setPoll({ options: [...poll.options, ""] })}>+ Add option</button> : <span />}
            <div className="flex items-center gap-2">
              <span className="text-ink-2">Open for</span>
              <Select value={String(rules.days.includes(poll.days) ? poll.days : 3)} onValueChange={(v) => setPoll({ days: Number(v) })}>
                <SelectTrigger className="h-6 w-24 text-xs" aria-label="How long the poll stays open"><SelectValue /></SelectTrigger>
                <SelectContent>{rules.days.map((d) => <SelectItem key={d} value={String(d)}>{DAYS[d]}</SelectItem>)}</SelectContent>
              </Select>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
