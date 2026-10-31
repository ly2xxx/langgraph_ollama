# Brag plan: Coding Engineer (`coding_agent/`)

**What it is:** An autonomous coding agent (LangGraph + Ollama). You give it a folder and a goal; it writes the definition of done first, locks it, then plans, codes, tests and gets audited by a second model until the goal is verifiably met, or stops and tells you why.
**Who it's for:** Developers who want an unattended code→test→fix loop that can't grade its own homework.
**What sets it apart:** Frozen BDD contract + maker/checker split + failure fingerprints that stop runaway loops.
**Most impressive / funniest claim:** The maker AI said "All 6 tests pass. The migration is already complete." The gate said ModuleNotFoundError. (Real quote, README case study.) And the agent has already rewritten part of its own engine (commit `ea1bfa1`, outcome: done).
**Visual hook:** A confident AI chat bubble, contradicted instantly by a red gate failure.
**Real UI shown:** The Streamlit Coding Engineer panel (budgets sidebar, live graph, goal box), cropped from `coding_agent/image/README/1785337898562.png`. The Grafana half is cropped out (its log pane shows a local filesystem path). Real strings: `[bdd_gate] FAIL`, the jail refusal, `st.error`/`st.success` messages, the real feature file.
**Tone:** default: punchy, playful, clean, dark terminal look.
**Share caption:** "My coding agent doesn't take its own word for it."

## Angle
"The coding agent that doesn't take its own word for it." Open on the lie, then show the three mechanisms that make lying useless: locked exam, independent reviewer, same-failure-twice stop. Punchline: it already rewrote its own engine.

## Visual identity
Background #0E131C navy-charcoal; accent teal #2AB3C7; pass green #3DD68C; fail red #FF4B4B (Streamlit red); text #E8EEF5. Fonts: Segoe UI Variable (display/body), Cascadia Mono (code). All local system fonts.

## Music
120 BPM (beat = 0.5s, bar = 2s), A minor, Am–F–C–G, one bar per chord. Synthesized: soft kick on beats, closed hat 8ths, sub bass roots, plucked arp. Cut SFX: in-key soft whoosh/low thump at every scene cut, a muted "stamp" at the FAIL moments. All on the beat grid from frame 0.

## Storyboard (24.5s, every cut on a beat)
| # | Time | Scene | On-screen | Motion | Sound |
|---|---|---|---|---|---|
| 1 | 0.0–3.5 | Hook | Maker bubble types "All 6 tests pass. The migration is already complete." Then terminal line `[bdd_gate] FAIL — ModuleNotFoundError: No module named 'rag_agent'` | Typing; red line slams in at 1.5s with a little shake; bubble dims | Stamp at 1.5 |
| 2 | 3.5–7.0 | Reveal | **Coding Engineer** / "The coding agent that doesn't take its own word for it." + real Streamlit panel | Title rises; panel slides in from right | Whoosh at 3.5 |
| 3 | 7.0–11.0 | Highlight 1 | "It writes the exam first. Then locks it." Real feature file, lock, jail refusal `write refused: … is frozen and cannot be modified` | File lines appear; lock snaps at 8.5; maker write attempt → red refusal at 9.0 | Whoosh 7.0, click at 8.5 |
| 4 | 11.0–15.0 | Highlight 2 | "Plans. Codes. Tests. Then a second model audits it." Node graph lights intake → … → review | Nodes light on beats | Whoosh 11.0 |
| 5 | 15.0–19.0 | Highlight 3 | "Same failure twice? It stops." `aa7cc6bd == aa7cc6bd` → `⚠️ escalated — two_plans_exhausted (a human decides what happens next)` | Hashes slide together, equals pops, red box | Whoosh 15.0, stamp 16.5 |
| 6 | 19.0–22.0 | Punchline | "It already rewrote its own engine." `coding-engineer: # Migrate _run_maker…` commit `ea1bfa1` + `✅ Done — review verdict: approve_with_notes` | Commit card, then green box | Whoosh 19.0 |
| 7 | 22.0–24.5 | Outro | **Coding Engineer** · LangGraph + Ollama · "Runs on its own branch. You merge." | Fade up, hold | Final chord ring-out |

No personal data: only model names and repo-relative paths appear.

## Delivered
- Poster / frame 0: t=6.5s (reveal: title + real Streamlit panel).
- Built with: HTML + headless Chromium (playwright-core) for frames, numpy synth + ffmpeg master for audio, ffmpeg H.264/AAC encode. Sources in work/.
