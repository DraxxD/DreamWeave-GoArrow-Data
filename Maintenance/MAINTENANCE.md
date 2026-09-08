# Maintaining the DreamWeave locations database

This is a small workflow for keeping the DreamWeave locations database
consistent when you push new content — without changing the XML structure
GoArrow itself expects.

## The files

- `locations[DreamWeave_NNN].xml` — the master/working copy. All editing
  happens here. `NNN` is a zero-padded, ever-increasing version number
  (`001`, `002`, ...) — never reused, never lowered. This file stays local
  (this machine + delivered here in chat); it is **not** what goes in the
  GitHub repo.
- `locations.xml` — the mirror/deploy copy, with a fixed filename that never
  changes between versions. This is the only one of the two files that goes
  in the GitHub repo and the one GoArrow's own `settings.xml`
  (`edtLocationsUrl`) should point at. Don't edit it directly — it's only
  ever updated via the `sync`/`bump` commands, once the master copy is
  ready.

The two files are kept byte-identical (aside from the master's version
number/tag) by editing one place and syncing afterward, which avoids the
kind of drift that had clearly happened between some fields in the file over
time before this tooling existed. The master file's current version number
is also embedded as a `Version: DreamWeave_NNN` line inside its own
auto-generated documentation block, near the top of the file — so the file
is self-describing even if a copy ever gets renamed or an old pointer in
`settings.xml` refers to a stale one (see the "in-game doesn't match the
file" note further down).

## The tool

`goarrow_maintain.py` needs only Python 3 (no extra packages). Run it from a
command line in the folder where the XML files live.

### Before a push: check status

```
python goarrow_maintain.py check
```

Runs a full consistency report: id uniqueness, dungeonId coverage, exit
coordinates used outside portal-like types, coordinate precision,
duplicates, and empty descriptions. Use `--out report.txt` to save it. Run
it both before and after a larger push so you can see what improved or got
worse.

### Add new content

```
python goarrow_maintain.py add
```

Walks you through the fields and automatically enforces the conventions
already established across the file's existing entries:

- **id** is assigned automatically as the next free one (highest + 1) in
  the type's reserved range — you never track this yourself.
- **type** must be one of the real, verified `GoArrow.RouteFinding.
  LocationType` enum members (see `KNOWN_TYPES` in the script) — an
  unrecognized type requires confirmation, so it's a deliberate choice, not
  a typo. **Never add a new type value without first verifying it against
  the actual compiled enum by decompiling `GoArrow.dll`** — `Location.
  FromXml` calls `Enum.Parse` with no fallback, so one bad `type=` value
  crashes the load of the entire file, not just that entry. Two values that
  were guessed early in this project (`PointOfInterest`, `ExplorationMarker`)
  turned out not to exist in the real enum and crashed the game on load —
  see the incident note further down.
- **coordinates** default to 1 decimal place (the established norm across
  most of the file). If an entry needs to be more precise, you can request
  5 decimals explicitly.
- **dungeonId** — if the type is Dungeon, the script asks and reminds you
  that a large share of existing dungeons (roughly a third) already lack
  the field, so you're not making the gap worse without knowing it.
- **exitNS/exitEW** — if you set exit coordinates on a type that doesn't
  normally have them (anything other than SettlementPortal, PortalHub,
  UndergroundPortal, WildernessPortal, TownPortal, Dungeon), the script asks
  for extra confirmation.
- **duplicate check** — warns if an entry with the same name+type already
  exists near the same coordinates.
- **patch** — automatically suggests the current month (`YYYY-MM`, e.g.
  "2026-09"), but you can type something else or press Enter to skip it.
  Set on all new entries, not just custom content — see the section below.

The new line is inserted in exactly the same physical format as the rest of
the file (4-space indentation, same attribute order, CRLF, BOM preserved),
so a diff of the file shows only the one new line — not a reformat of the
whole file. A `.bak-<timestamp>` backup is taken automatically before
anything is written.

#### Only have a raw in-game `/loc`? Convert it first

In game, `/loc` gives you something like:

```
Your location is: 0x0D4A0103 [158.116852 133.179001 18.205000] 0.936529 0.000000 0.000000 -0.350590
```

That is NOT the format the file uses (it wants NS/EW as decimal numbers,
e.g. `-42.1`). `/loc` is still convenient because it always works — outdoors
as well as in caves/dungeons — so the script converts it for you instead of
writing the raw value into the file (which would break how every existing
entry, and GoArrow itself, expects coordinates to look).

There are two ways to use it:

1. Directly inside `add` — when the script asks for NS/EW, you can answer
   "yes" to having a raw `/loc` string instead, and paste it in. The script
   works out NS/EW itself and uses them, without the raw text ever ending
   up in the file.
2. As a standalone calculator, if you just want to see the numbers without
   adding anything yet:

   ```
   python goarrow_maintain.py loc "0x0D4A0103 [158.116852 133.179001 18.205000] 0.936529 0.000000 0.000000 -0.350590"
   ```

   Gives you e.g.:

   ```
   NS = -42.14509   -- 1 decimal: -42.1   5 decimals: -42.14509
   EW = -90.84118   -- 1 decimal: -90.8   5 decimals: -90.84118
   ```

The formula is not guessed — it was derived and self-tested (round-trip)
directly against [ACEmulator](https://github.com/ACEmulator/ACE)'s official,
open-source code for the game's coordinate system (`LandblockId.cs` and
`Position.cs`), the same logic the real server/client uses. The landblock id
(`0x0D4A0103`) and the first two numbers in the square brackets (continuous
local position) are all that's needed — the Z coordinate and the rotation
numbers are unused, since the file's schema has no fields for height or
facing.

## Sync the mirror file

```
python goarrow_maintain.py add --sync
```

or separately:

```
python goarrow_maintain.py sync
```

Copies the master copy over `locations.xml`, backing up the old version
first. Refuses if you accidentally point `--file` at `locations.xml` itself
— sync only ever goes master → mirror, never the other way.

## New version (release) workflow

```
python goarrow_maintain.py bump
```

Renames the master file to the next version number, regenerates its
documentation block (with the new `Version:` line baked in), and syncs
`locations.xml` — all in one step, so the filename, the embedded version
line, and the mirror can never end up disagreeing with each other. Use this
instead of renaming the master file by hand. Pass `--version N` to skip
ahead to a specific number instead of just +1.

## Recommended workflow for a push

1. `check` — see the status before starting.
2. `add` (once per new location) — or several times for a larger batch.
3. `check` again — confirm nothing new broke (e.g. a new duplicate, or a
   dungeon missing a dungeonId).
4. `bump` — once the master copy is ready for release: this both updates
   `locations.xml` and gives the master file its next version number.
5. Push the new `locations.xml` to the GitHub repo (see the main
   `README.md` for the update/backup steps for anyone installing it).
6. Keep the `.bak` files around for a while as extra safety, clean them up
   periodically (e.g. move them to the `Arkiv` folder you already use).

## ID grouping (bands) for new content

**Existing ids (1–9539) should NOT be renumbered.** GoArrow's own
`settings.xml` stores the user's "recent locations", routes, and favorites
keyed by exactly these id numbers (confirmed: `id="9291"` and `id="9359"`
appear both in `locations` and in a saved route in `settings.xml`). Changing
an existing id makes the user's saved data point at the wrong — or a
nonexistent — location. **Deleting an existing entry, verified 2026-09-08,
does not crash GoArrow either way** (see the "Removing an entry" section
below) — but it's still good practice to keep ids stable unless there's a
real reason to remove the entry, since deletion silently drops any saved
reference to it with no warning to the player.

Instead, a fixed band of 5000 ids per type is reserved, starting at 10000 —
completely free territory, since no existing entry comes close:

| Type | Band |
|---|---|
| NPC | 10000–14999 |
| Vendor | 15000–19999 |
| Landmark | 20000–24999 |
| Dungeon | 25000–29999 |
| Village | 30000–34999 |
| SettlementPortal | 35000–39999 |
| Lifestone | 40000–44999 |
| PortalHub | 45000–49999 |
| WildernessPortal | 50000–54999 |
| UndergroundPortal | 55000–59999 |
| Town | 60000–64999 |
| TownPortal | 65000–69999 |
| AllegianceHall | 70000–74999 |
| Outpost | 75000–79999 |
| Bindstone | 80000–84999 |
| Custom | 85000–89999 |
| _Unknown | 95000–99999 |

(`Any`, `AnyPortal`, `Portal`, and `PortalDevice` are real enum members too,
confirmed by decompiling GoArrow.dll, but have no reserved band yet since
nothing has needed them — prefer an already-used type where it semantically
fits before reaching for one of these.)

The `add` command automatically looks up the right band for the chosen type
and uses the next free id there. The `check` report shows how full each
band is, so you can see well in advance if a type is approaching its 5000
slots. If a band fills up, the script automatically falls back to the
globally next free id and warns you — so nothing breaks, but the grouping
becomes less clean for that type until you increase `ID_BAND_WIDTH` or give
the type a bigger band in the script's `ID_BANDS`.

The effect: a year from now you can look at an id alone (e.g. 25,042) and
know it's a Dungeon — without ever having touched a single one of the
original existing entries or players' saved references to them.

## Custom DreamWeave content (marking / metadata)

The schema has no dedicated field for "this is custom content." Two markers
are therefore used together on new entries:

1. The attribute `customized="True"` — a real, queryable marker. It's
   technically a new attribute, but it's strictly additive (only appears on
   entries you add yourself, never touches the existing entries) and
   verified in practice: it originates from another server's real, running
   GoArrow file, so we know GoArrow tolerates unknown attributes.
2. The tag `[DreamWeave Custom]` as the first word of the description — so
   a human can see it immediately just by reading the text, without having
   to check attributes.

When adding an entry, the script asks: *"Is this custom DreamWeave content
(not stock AC)? (y/n)"*. If you say yes, both markers are set automatically
and consistently — you never need to remember the format yourself.

Two examples of how this ends up in the file:

```xml
<loc id="25000" name="Aetherium Vault" type="Dungeon" NS="-42.3" EW="18.7" customized="True">[DreamWeave Custom] A hidden empyrean archive hall, built specifically for the DreamWeave server. Not part of stock Asheron's Call.
Quest(s): Aetherium Fragment Hunt.
Restrictions: 1-8</loc>

<loc id="10000" name="Kaelen the Dreamweaver" type="NPC" NS="12.4" EW="-6.1" customized="True">[DreamWeave Custom] Quest giver for the Aetherium Fragment Hunt chain. Introduced with the DreamWeave content update.</loc>
```

The `check` report also shows how many entries are marked as custom content
(counted via both markers), broken down by type, and warns if an entry only
has ONE of the two (a sign of hand-editing outside the script). You can
always see the scope without searching manually, and easily filter it back
out again (e.g. for a "pure stock AC" edition of the file), if that becomes
relevant.

Note for the Dungeon type: `dungeonId` for genuinely custom dungeons can't
be looked up in `data_cod.xml`, since the dungeon doesn't exist in the stock
game — that id would have to come from your own server-side content, if it
even has one.

### Self-documenting comment block inside the file itself

```
python goarrow_maintain.py docblock
```

Inserts (or updates, if it already exists) a plain XML comment at the top of
the file, right after the `<locations ...>` tag. It explains all the id
bands, the rule that existing ids should never be changed, and the
custom-content convention — generated directly from `ID_BANDS` in the
script, so the documentation can never drift out of sync with what the
script actually does. The comment also contains one example line per main
type as plain text inside the comment — these are NEVER loaded by GoArrow
as real locations, so they can't show up as visible, unexplained points on
the map, but they're there as a template for anyone who opens the file in a
text editor.

Run it once now, and again whenever you change `ID_BANDS` or
`ID_BAND_WIDTH` in the script — so the comment in the file automatically
stays in sync. Use `--sync` to update the mirror file at the same time.

Note: XML comments must never contain two consecutive hyphens ("--")
anywhere in the text — that makes the file invalid. The script checks for
this itself and stops with an error if any future edit to the text in
`build_doc_block()` breaks the rule, rather than writing a broken file.

## Removing an entry — deletion vs. `retired=`

Background: this approach was originally compared against Darktorizo's
`data_cod.xml` (a separate, unrelated database — see the README/Update
instructions.txt in [GoArrow_Data_CoD](https://github.com/Darktorizo/GoArrow_Data_CoD)
on GitHub), which uses a dedicated `<retired>Y/N</retired>` field to hide
obsolete entries without deleting them. This project reused the idea as an
attribute instead, since this schema is attribute-based, not element-based
like theirs — but see the important caveat below: it turned out not to
actually do anything in GoArrow.

```
python goarrow_maintain.py retire --id 12345
```

Sets `retired="True"` on the entry with the given id. Run again with
`--undo` to reverse it:

```
python goarrow_maintain.py retire --id 12345 --undo
```

Both take an automatic backup first, and work whether the entry is one of
the original entries or something you added yourself. The `check` report
shows an overview of all retired entries, by type, so you can see how many
are marked without searching manually. Use `--sync` to update the mirror
file too. The docblock itself (`docblock`) also documents this convention
for anyone who opens the file directly.

**Important, verified 2026-09-03 by decompiling `GoArrow.dll`'s
`Location.FromXml`: `retired="True"` does NOT hide the entry.** GoArrow
never reads a `retired` attribute at all — `FromXml` only ever looks at
`id, name, type, NS, EW, exitNS, exitEW, dungeonId, customized, use, icon`.
Setting `retired="True"` is purely bookkeeping for your own `check` report;
the entry displays exactly as before, with the same icon, on the same map.
(An earlier version of this document, and of the tool's own console
output, incorrectly claimed this attribute hides the entry — that was
wrong and has been corrected everywhere, including the file's own docblock
comment, as of 2026-09-08.)

**If an entry genuinely needs to stop showing on the map** (e.g. an NPC
that no longer exists in the current game state), the only verified way to
do that is **deletion**. This raises the obvious concern from the ID
banding section above: is it safe to delete an entry whose id might be
saved in some player's `settings.xml` (favorites, recent locations, or a
saved route)? **Verified safe, 2026-09-08**, by decompiling `MainForm.
LoadSettings` (the code that resolves a saved id against the loaded
database via `LocationDatabase.GetLocation`): both call sites null-check
the result before using it, and `GetLocation` itself returns null
gracefully (not an exception) when no entry matches the id. So deleting an
entry does not crash GoArrow — a stale saved reference to it is just
silently skipped on the next load. The only real cost is that the specific
player who had it saved loses that one shortcut, with no warning. Prefer
keeping ids stable when there's no strong reason to remove an entry, but
don't let an unfounded fear of crashing hold you back from deleting an
entry that genuinely needs to go — see `Maintenance/PROGRESS.md`'s Tou-Tou
cleanup entries for a worked example.

## Patch/update tracking

Since monthly updates to the game are expected, `add` sets a
`patch="YYYY-MM"` attribute on **all** new entries (not just custom
content — "which patch did this come in with" applies to anything new, not
only what DreamWeave itself created). It's an attribute, not a text tag,
because it's structured data you'll want to count and sort on — unlike
`[DreamWeave Custom]`, which is meant for a human to see just by reading
the text.

The script automatically suggests the current month as a default, so you
typically just press Enter. If you're adding several locations for the same
patch in a row, you can set it directly and skip being asked every time:

```
python goarrow_maintain.py add --patch "2026-09"
```

The `YYYY-MM` format is a recommendation, not a requirement — the script
warns but doesn't block if you write something else (e.g. the name of a
larger update). The recommendation exists because `YYYY-MM` sorts correctly
as plain text, and it avoids ambiguity between different languages'
month abbreviations.

The entries that predate this tracking never get `patch` set retroactively —
the attribute's absence means "added before this was tracked," not an
error. The `check` report shows a breakdown of entry count per patch value,
newest first, and the `docblock` comment in the file itself explains the
convention for anyone who opens the file directly.

## Enrich empty descriptions from a wiki (ACPedia etc.)

A large share of entries have an empty description (mostly SettlementPortal,
Lifestone, Vendor, Landmark — see the `check` report's "Empty description
by type" section for the current count). `data_cod.xml` (the Warcry atlas,
see the removal section above) was already investigated as a source and is
a dead end: every entry with the same id either has the same description or
already has a *different* (edited) one — none of the empty ones can be
filled from it, and the file is additionally marked "All rights reserved"
by Warcry.

Instead, `enrich` can look up the name on a public wiki (e.g.
[acpedia.org](https://acpedia.org), the AC Community Wiki, or
[asheron.fandom.com](https://asheron.fandom.com)) and suggest a short
excerpt as the description — one entry at a time, with your approval:

```
python goarrow_maintain.py enrich
```

- Only goes through entries with an **empty** description — never touches
  an entry that already has text, regardless of source.
- For each entry: looks up the name via the wiki's search API, shows you
  the best match and an excerpt, and you answer **y** (use it), **e** (edit
  the text yourself before saving), or **n** (skip).
- The saved text automatically gets a source note on the last line, e.g.
  `(Source: Al-Arqas, https://acpedia.org/wiki/Al-Arqas)`, so it's always
  visible afterward which descriptions come from a wiki and which were
  written by you (same idea as the `[DreamWeave Custom]` tag).
- `--type Landmark` limits it to one type at a time (handy for working
  through it in manageable chunks); omit it to go through all of them.
- `--wiki fandom` switches to the Fandom wiki instead of ACPedia;
  `--wiki https://en.uesp.net` (or any other URL) also works if you find
  another MediaWiki-based source. Default is ACPedia.
- `--sync` updates the mirror file afterward, like the other commands.

**Important caveat:** both wikis are confirmed to run MediaWiki (so they
have, in principle, a free, public `api.php`), but it was **not** confirmed
that it works in practice from this environment — the test environment's
own connection was refused entirely, and a browser hit a Cloudflare
bot-verification page trying to open acpedia.org. It may still work fine in
practice — many wikis exempt the `api.php` endpoint itself from that kind
of challenge even though the front page shows it — but that's not confirmed
for these two specifically. `enrich` detects for itself if a lookup fails
(network error, bot blocking, anything) and immediately offers to switch to
**manual entry**: it shows you a search URL, you open it in your own
browser, and paste in the text you find — same approval and source-marking
as an automatic match. The tool works either way; the only question is
whether you look it up yourself or the script can do it for you. Run
`enrich --type Landmark` as a small test first to see which of the two
paths actually works for you.

**License/copyright:** wiki text isn't yours to redistribute — use it as
background knowledge for a short, rewritten description rather than copying
long passages verbatim, especially if the file is shared with others.
Fandom content is typically CC BY-SA (requires attribution, which the
source note above gives you for free); check acpedia.org's own terms if you
use it extensively.

## Enrich from the server's own ACE database (preferred over a wiki)

A better source than an external wiki: the DreamWeave server's own
`ace_world` database knows the name, description, AND precise coordinates
for each portal — see **`ACE_DATABASE_ANALYSE.md`** for the full analysis
(method, numbers, caveats). In short:

```
python goarrow_maintain.py import-ace
```

Goes through an already-extracted candidate dataset
(`ace_import/ace_import_candidates.json`) from the server's
`landblock_instance`/`points_of_interest` tables: suggestions for brand-new
entries, missing `exitNS/exitEW` on existing entries, and missing
descriptions — each shown for your approval, just like `enrich`.
`--action`, `--include-low-confidence`, `--limit`, and `--sync` control the
scope. Never touches an entry that already has the value in question.

For a new database dump: unpack the `.sql.gz`, load it into MySQL/MariaDB,
and re-run `ace_import/extract_portals.py` and `ace_import/build_candidates.py`
for a fresh candidate file.

## Correcting existing data

The tool doesn't automatically fix the pre-existing entries — that's
deliberate, because several of the issues (missing dungeonId, low-precision
coordinates) require a human judgment call about what the right value is.
The `check` report gives you the full list to work through, at your own
pace, separate from the ongoing work of adding new content.
