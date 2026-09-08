# DreamWeave GoArrow Locations Database

Curated GoArrow (Asheron's Call navigation plugin) locations file for the
DreamWeave private server, plus the maintenance tooling used to keep it
consistent as new content is added.

## What's in this repo

- **`locations.xml`** — the live locations database, ready to use as-is.
  Loaded by the [GoArrow](https://github.com/PhatAC/GoArrow) plugin
  (`VirindiPlugins/GoArrowVVSEdition`) to show map pins for towns, dungeons,
  portals, vendors, lifestones, and other navigation points across the
  DreamWeave world. This filename is always stable — it never carries a
  version number — so it's always safe to point GoArrow's `settings.xml`
  (`edtLocationsUrl`) at it and just replace the file on every update (see
  "Installing / updating" below). The file's own maintenance history is
  tracked separately, not in its name — open it in a text editor and the
  very first lines carry a `Version: DreamWeave_NNN` tag along with the full
  documentation block, so it's still possible to tell which revision you
  have even without relying on the filename.
- **`goarrow_maintain.py`** — a Python 3 command-line tool (no external
  dependencies) for adding, checking, and enriching entries in the XML file
  without breaking GoArrow's expected format (attribute order, CRLF line
  endings, BOM, id numbering, etc.).
- **`PROGRESS.md`** — a running log of what's been added or fixed and why,
  including lessons learned about GoArrow's actual (reverse-engineered)
  behavior — e.g. which `type=` values are valid, what crashes the loader,
  and what data GoArrow actually reads from each `<loc>` entry.

## Installing / updating

1. Download `locations.xml` from this repo.
2. If you already have a locations file GoArrow is using, rename your
   current one to `Backup_YYMMDD_locations.xml` (today's date) first, so you
   can always roll back.
3. Put the new `locations.xml` in its place, make sure GoArrow's
   `settings.xml` (`edtLocationsUrl`) points at it, and restart GoArrow —
   it only reads this setting once, at startup, so a running instance won't
   pick up the new file on its own.

## Background

Asheron's Call encodes every in-world position as a single opaque
`/loc` value (a landblock id plus a local X/Y/Z position and rotation).
GoArrow's locations file instead stores each point as human-readable
NS/EW coordinates. `goarrow_maintain.py` includes a verified conversion
between the two, cross-checked against
[ACEmulator](https://github.com/ACEmulator/ACE)'s own open-source
`LandblockId`/`Position` code — so a raw `/loc` string copied from the game
can be converted and added correctly without guessing at the format.

Several details about GoArrow's actual behavior in this repo were
determined by decompiling the plugin's compiled `GoArrow.dll` (not by
guessing or by copying another server's file) — see `PROGRESS.md` for the
specifics. This matters because GoArrow's XML loader has **zero tolerance**
for malformed input: one bad `type=` value or one misplaced XML comment
crashes the load for every location in the file, not just the bad entry.

## Status

Actively maintained. Locations are added/updated as the DreamWeave server's
content changes (new zones, destroyed/altered areas, new portals). See
`PROGRESS.md` for the current history and any open questions.
