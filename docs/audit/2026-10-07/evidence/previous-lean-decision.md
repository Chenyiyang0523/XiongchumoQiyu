# M3 round 3 — the lean writer

## Evidence (2026-10-07)
Pairwise, Claude judges, both orders, same cards:

| comparison | again | natural | surprise |
|---|---|---|---|
| r1 pipeline vs single-prompt baseline | 0/5 | 0/5 | 1/5 |
| r2 pipeline vs baseline | 0/5 | 0/5 | 0/5 |
| r2 pipeline vs r1 pipeline | 0.6 | 0.7 | 0.4 |
| **lean prototype vs baseline** | **0.4** | **0.5** | **0.5** |
| **lean prototype vs r2 pipeline** | **0.92** | **1.0** | **0.83** |

The lean prototype (`tools/lean_proto.py`, commit 53f9bb3 on m3-r2) keeps the game's shape — one chapter per call, the
child picks at each fork — but prompts like the baseline: the same system prompt, card, cast and exemplar blocks, the
baseline's whole-book task, and for later chapters 「【这本书已经写到这里】」 + every earlier line + 「接着往下写完这本书：现在写第N
章…第一页就让读者看到刚才选的「…」带来的后果」; it keeps only the current chapter and its fork (the stream is cut), with no
director brief, no setups/secret, no validators and no repairs. It reaches parity with the baseline and beats the r2
pipeline almost every time, at ~0.17 元 per medium book (no siblings). The obligation machinery was hurting the
stories. Decision: the engine writes the lean way; the director's obligations, setups/secret and structural
rewrites leave the writing path. Safety, script, voice, length and format protection stay.

## Lean writer — behaviour
1. **Setting** `writer.mode` = "lean" (default) | "classic" (the current Writer, kept for comparison until the lean
   writer has passed round 3, then removed in a later clean-up). sim.py, runner and the session use the setting.
2. **Opening** (one streamed call, cut after the first choice line): the baseline's messages for the card with the
   whole-book task, except the first line is an extended title line:
   `{"type":"title","title":"…","logline":"…","hero":"主角id","cast":["两到四个角色id"],"guest":{"name":"客串角色名或空","look":"它长什么样"},"places":["一到三个地点"],"want":"主角想要的具体东西"}`.
   It becomes a minimal bible (title, logline, hero, cast, guest, places, want; no setups, no secret). Then the
   chapter-1 pages and the first choice line (the model's own "chosen" field is ignored). A pool opening is the same
   call (no gate call, or a code-only gate: title + ≥2 pages + a valid fork).
3. **Chapter** (one streamed call per node, cut after the node's choice line, or its end line in the last chapter):
   system prompt + user message = card/cast/exemplar blocks, 「【这本书已经写到这里】」 with the JSON lines of the world line
   so far (title line, every page, every choice with `"chosen"` = the reader's pick), then the continuation task in
   the prototype's words (current chapter and its page count, the remaining chapters' page counts, choice after every
   chapter but the last, end line at the end, first page shows the consequence of the chosen option), then the
   baseline's 【故事要求】 lines. An idea option says 「小读者自己想到了「{label}」：{decision}——第一页就让它真的做成」.
   Siblings (speculation) are the same call with another chosen option plus one short line naming that sibling's
   outcome variant (success_with_cost / fail_but_gain / detour wording of beats.json) so the three branches differ.
   The final chapter's task adds the ending family the director picks from the path (warm/twist/funny brief, one
   line) and asks the end line to carry it: `{"type":"end","title":"结局名，十个字以内","family":"warm|twist|funny"}`.
4. **Line checks** (validate.py, lean profile): format/schema, safety (hard → one repair, then drop the line and
   continue), script purity/emoji/digits (mechanical fixes), voice matrix (mechanical), stray quotes, art.speaker,
   fork q question mark, page length (len.lines > 6 or card rows > 6.5 → mechanical split at a sentence boundary;
   otherwise ship), cast: a canon character outside the cast joins `state.cast_extra` (no repair; the guest id stays
   reserved for the book's guest), adult/kid-vocabulary lists (mechanical substitutions only where meaning is kept).
   No plant/payoff/turn/token/ack/reveal/rule checks and no structural rewrites (keep ack/token as log-only metrics).
5. **Stream mechanics** stay: continuation after a drop or a cut stream (from the last committed page, same lean
   prompt plus 「接着写第N页」), cancel, the meter, the budget hook, extra-page handling (a page beyond the chapter's
   count stops the stream; the fork follows by a fork-only tail request), events compatible with plan B1's session
   (page, choice, end, plan_meta with the family for the finale, done with usage; never truncate).
6. **Content**: the system prompt must not ask for plan lines in lean mode (or the writer drops them); remove the
   r2 「换成紧紧/牢牢」 substitutions and add 紧紧/牢牢 to tier B (≤2 per book) — the r2 panel counted 42 uses.
7. **Tools**: tools/lean_proto.py is superseded by sim.py with the lean writer (keep it as the experiment record);
   metrics/judge/transcript tolerate a bible without setups/secret (retell keys from the title line's want; turn
   from the last chapter).

## Acceptance (live, round 3)
6 medium books with siblings (same seed m3a, same personas) + the r1 baseline books: pairwise vs baseline ≥ 0.5 on
again and natural (parity; the baseline is not interactive and chooses its own path), vs the lean prototype ≥ 0.5,
divergence ≥ 80 %, consequence visible ≥ 95 %, 0 failed books, no safety-list hit in shipped text, cost per first
ending of a medium book with speculation ≤ 1.6 元 (text part).
