# Instructions for the AI

This repository holds one maker's kamishibai works, one folder per work under `works/`. The tools are not in here:
they come from the Digital Kamishibai skill (installed as a plugin, or a copy of its repository next to this folder).

- **Use the skill `digital-kamishibai`** for planning, writing, building, practising and correction sheets
  (`# Correction sheet: ...`). Read its `SKILL.md` first.
- **Do not change the skill's own files** (the installed plugin or the tools' repository). A wish for the tools goes
  to the maker, not into the files.
- Change `script.md`, never `work.json`: the builder writes `work.json` again every time.
- Keep what `.gitignore` leaves out (music, videos, the storyboard, the drawn pictures) out of commits.
