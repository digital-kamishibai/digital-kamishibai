# Digital Kamishibai

*Digital Kamishibai here is a picture-story show a family builds **for its own children** — written by a parent,
and often, in time, narrated by the children themselves — not a lean-management task board, and not a digitized
edition of traditional Japanese street kamishibai.*

A kamishibai is a story told aloud over a series of pictures, one picture at a time, usually with music.
This project gives you two things:

- **A skill for an AI assistant** (Claude, Codex or ChatGPT) that helps you make one: it interviews you, plans the
  show with you, writes the script in your words, checks the facts, and helps you practise.
- **A room player** — a web page where the narrator shows the pictures and plays the music, and listeners follow
  on their own devices, in the same room or in different houses.

It works for a family at home, a class, or a group of adults learning from each other.

## Why

The story itself can be borrowed — a piece of science, a moment in history, a book. What makes a family's
kamishibai work is the **holes** in it: the places only this family can fill. A child's question, a parent's own
stumble, the songs playing in the house this month, the family's own photos. The skill is built around finding those
holes and leaving them empty when nothing comes — every one of them is optional.

It is also built not to push. Nobody is asked to take part, there are no deadlines, and the maker decides every word.

## Quick start

1. **Install the skill** in the AI you use (details below). Then say something like:

   > I'd like to make a kamishibai — a picture-story show — for my two kids about why the moon changes shape.

2. **Talk it through.** The AI asks a few questions at a time, then writes a plan and a script (`script.md`)
   with you. Pictures can be family photos, children's drawings, or generated pictures.

3. **Build the work folder** on your computer (Python 3.10 or later, nothing to install):

   ```
   python skills/digital-kamishibai/scripts/build_work.py <work folder> --draft
   ```

   This writes `work.json` next to `script.md`. Words on the pictures (`[Text]`) are drawn by Microsoft Edge or
   Google Chrome, so a work with words needs this whole repository and one of those browsers on the computer.
   `python skills/digital-kamishibai/scripts/doctor.py` tells you what the computer lacks (it installs nothing).

4. **Perform** with the room player: open **https://digitalkamishibai.org** on the narrator's computer, press
   *Narrate* and choose the work folder. Listeners open the same address on their phone, tablet or computer, enter
   the six-digit code under *Listen*, and the narrator lets each device in. `--draft` gives a version for practising: the player lets you correct the narration
   and the words on the pictures, and hands you a correction sheet to give back to the AI.

No account is needed for the room player, and nothing is installed on the listeners' devices.

## Install the skill

The same repository is a plugin for Claude Code and for Codex.

**Claude Code**, inside a session:

```
/plugin marketplace add digital-kamishibai/digital-kamishibai
/plugin install digital-kamishibai@digital-kamishibai
```

Update later with `/plugin marketplace update digital-kamishibai`. At the start of a session, call the skill by
name — `/digital-kamishibai:digital-kamishibai` — so that this version is the one used.

**Codex**, in a terminal (it reads the same `.claude-plugin/` files):

```
codex plugin marketplace add digital-kamishibai/digital-kamishibai
codex plugin add digital-kamishibai@digital-kamishibai
```

Update later with `codex plugin marketplace upgrade digital-kamishibai`. Call the skill with `$digital-kamishibai`.
On Windows, Codex's sandbox stops the browser that draws the words on the pictures: let the build command run outside
the sandbox when Codex asks, or run it yourself.

**ChatGPT** (tried with a Plus plan, November 2026): in Skills, add a zip of the folder `skills/digital-kamishibai/`
(the folder itself, not its contents). Then start a new chat in **Work** mode — in Chat mode the skill is not used,
and nothing tells you so. ChatGPT can interview, plan, write and build `work.json` there; words on the pictures need
a browser it does not have, so build those on your computer.

**Claude (claude.ai)**: in Customize → Skills, upload the same zip. Code execution must be on.

A maker who keeps several works can start their own repository from [`templates/maker-repo/`](templates/maker-repo/README.md)
(the tools stay here; they are not copied in).

## Why anyone may open the player's address

The room player is a public page, and that is safe by design:

- **Your work never goes to a server.** The narrator's browser reads the work folder from the narrator's own
  computer. The page itself contains no stories.
- **Pictures, music, video and voice go straight from the narrator's device to each listener's device.** A small
  public service only introduces the devices to each other. When two devices cannot reach each other directly
  (common between different home networks), a relay server passes the traffic along, encrypted, without keeping it.
- **Only the narrator lets people in.** A listener needs the six-digit code, and then waits until the narrator
  presses *Let in* for that device. The code is not the protection; the narrator's approval is.

## Ladders (optional, not free)

The basic path needs no paid service. A ladder is a tool for families who already have what it needs.

| Ladder | Makes | Costs and needs |
|---|---|---|
| [`ladder/images/`](ladder/images/README.md) | pictures from the plan's prompt table, with Google's Gemini | **paid per picture** (about US$0.134 each, October 2026) to the owner of a Gemini API key; Python 3.10+ and Pillow |
| [`ladder/ending-video/`](ladder/ending-video/README.md) | the ending video: the family's photos and videos on one song, from a storyboard you point at | free; Python 3.10+, Pillow and ffmpeg |

## Questions and problems

- **Questions, ideas, and how your family filled the holes**: [Discussions](https://github.com/digital-kamishibai/digital-kamishibai/discussions).
- **Something does not work**: [Issues](https://github.com/digital-kamishibai/digital-kamishibai/issues).
  Please describe the problem in general terms — no family names, no story contents, no photos.

This is maintained by a small team in its spare time. We read everything, but we cannot promise when we will answer.

## Who runs it

Digital Kamishibai is built and maintained by Fast Focus Technologies, a small independent team with no outside
investors. The code is MIT-licensed and your works stay in your own folder, so the project can always be continued
by anyone.

## License

Code: MIT — see [LICENSE](LICENSE). Documents (the skill and its references, the templates and the example): CC BY 4.0 —
see [LICENSE-docs](LICENSE-docs) for exactly which files. Third-party code in `player/vendor/` keeps its own license.

---

## For developers

| Path | What |
|---|---|
| `skills/digital-kamishibai/` | The skill: how to interview, plan, write and perform a family kamishibai, with templates and references. Self-contained: hand over the whole folder. |
| `.claude-plugin/` | Makes this repository a Claude Code plugin (and its own marketplace); Codex reads the same files. |
| `docs/work-format.md` | The only definition of a work (`script.md` → `work.json` + media). Change it first, then the tools. |
| `examples/sample-story/` | A fictional work. The shared test fixture for the builder, the player and exporters. |
| `tests/` | `npm test` (Node 22, no dependencies): the player's logic — the work format and who-gets-what between narrator and listeners. `python -m pytest tests/builder tests/ladder` (Python 3.10+, pytest; Pillow for the ladder): the builder and the ladders (no paid service is called). `python tests/e2e/family_basic.py` and `python tests/e2e/ending_seat.py` (run by hand; Edge and ffmpeg, and the internet for the room): the whole way through on a copy of the example — open the room, a second browser joins, practise, correct, write back, open again; point at a seat of the ending video. `python tests/e2e/agent_sheet.py codex` (or `claude`; uses the agent's plan): an AI agent with only the skill writes a correction sheet back into a copy of the example, from a maker's own words. |
| `src/` | The Worker: `/api/ice` only. Pictures, video and voice never pass through it. |
| `ladder/` | Optional tools that cost money or need extra software. Nothing else depends on them. |
| `templates/maker-repo/` | A starting point for one maker's own repository of works. `AGENTS.md` holds the instructions for the AI; `CLAUDE.md` only points to it. |
| `player/` | Room player — a static page served over HTTPS. Narrator and listeners in different rooms, browser only, no accounts. Contains no stories. |

### Builder options

`--check` checks without writing; `--media DIR` when the pictures, music and videos are in another folder;
`--draft` builds a version for practising and correcting in the player; `--skip-text` leaves the words on the
pictures out. Words are drawn into copies of the pictures (`pictures/_built/`) by a headless Edge or Chrome, with the
player's own drawing code; the original pictures are never changed. `doctor.py` takes `--for ending-video`,
`--for pictures`, `--for claude` or `--for codex` to check for more.

### Deploy (player)

Cloudflare Workers. `wrangler.jsonc` serves `player/` as static files; `src/worker.js` answers only `/api/ice`
(short-lived TURN credentials, so devices on different home networks can still connect).

Secrets (Worker → Settings → Variables and Secrets, type *Secret*; never in this repository):
`TURN_KEY_ID` and `TURN_KEY_API_TOKEN` from Cloudflare Realtime → TURN, and `CF_ANALYTICS_TOKEN`
(an API token with only *Account Analytics: Read*). Without the TURN key the player uses STUN only.

The relay has a loss ceiling: a Cron Trigger (every 5 minutes, `src/watch.js`) reads TURN usage (`egressBytes`, UTC)
and writes a mark to Workers KV. A credential over its own cap is revoked; over the daily or monthly cap, `/api/ice`
stops handing out the relay and the player tells the narrator. If the mark is more than 30 minutes old, the relay is
not handed out either. Caps are plain variables (see `src/guard.js` and `wrangler.jsonc`; `--env staging` uses tiny caps for testing).

`--env public` is the public site (https://digitalkamishibai.org). GitHub Actions deploys it on every push to `main`
once the tests pass (`.github/workflows/ci.yml`, secret `CLOUDFLARE_API_TOKEN`).
