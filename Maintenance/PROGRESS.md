# DreamWeave GoArrow — Progress tracker

Running list of open workstreams for the DreamWeave locations database
project. Kept in English (per project convention — see MAINTENANCE.md
language note below).

## File naming/versioning convention finalized + tooling support added (2026-09-08)

Nico wanted a clearer naming scheme before the first GitHub push, worked out
together over a few rounds:

- **Master file**: renamed from `locations -DreamWeave_Claude.xml` to
  `locations[DreamWeave_NNN].xml`, `NNN` a zero-padded, ever-increasing
  version number, never reused/lowered. Nico's own choice, continuing the
  spirit of his earlier manual "rename every delivered test copy" habit
  (`_Claude_9`, `_Claude_12`, ...) but formalized. Starts fresh at `001` —
  the old ad hoc numbering wasn't tracking a documented "master version" (no
  changelog behind what changed between `_9` and `_12`), so restarting
  cleanly at the same moment this proper version-tracking begins avoids
  implying versions 1-11 exist and are documented somewhere when they
  aren't. This file stays local only (this machine's working folder + this
  machine's Maintenance folder) — it does **not** go in the GitHub repo.
- **Mirror/deploy file**: renamed from `locations -DreamWeave.xml` to a
  fixed `locations.xml`, no version tag, never changes name between
  versions. This is the only one of the two files that goes in the GitHub
  repo and the one a `settings.xml` `edtLocationsUrl` should point at —
  fixed name means download links and settings never need to change on an
  update, and it can just be overwritten in place in the repo each release
  (git's own history covers old versions, no need to keep every past
  revision as a separate file cluttering the repo tree).
- **Version embedded in the file itself, not just the filename**: the
  master file's version number is now also written as a `Version:
  DreamWeave_NNN` line inside the auto-generated documentation block
  (`build_doc_block()`), so the file is self-describing even if a copy gets
  renamed or a stale `settings.xml` pointer is being debugged — directly
  reusable for the same kind of "which file is GoArrow actually loading"
  confusion recorded in `goarrow-notes.md`'s LESSON section from
  2026-09-02.
- **New `bump` command** in `goarrow_maintain.py`: renames the master file
  to the next version, regenerates its docblock (new version line baked
  in), and syncs `locations.xml` — one command instead of a manual
  rename-then-docblock-then-sync sequence, removing the exact kind of place
  a manual step could be forgotten or done in the wrong order. `--file`'s
  default is no longer a hardcoded literal filename (which would have gone
  stale at the very next version bump); `default_master_filename()` /
  `find_latest_master()` scan the working directory for the
  highest-numbered `locations[DreamWeave_*].xml` file instead.
- Corrected: this file naming plan clarifies (does not change) the earlier
  plan — the *original* first-push guide had the working-copy file itself
  going into the repo root; since nothing had actually been pushed yet when
  this was raised, no repo cleanup was needed, just a rename of the local
  copies before the first push happens. README.md's "What's in this repo"
  and new "Installing / updating" section, and MAINTENANCE.md's "The
  files"/sync/release-workflow sections, were rewritten to match (see the
  section below for the MAINTENANCE.md rewrite specifically).

Locally renamed and re-verified: `locations[DreamWeave_001].xml` and
`locations.xml`, both 5207 entries, byte-identical after sync, 0 bad
`<locations>` children, 0 bare LF, `Version: DreamWeave_001` line present.
Also test-ran `bump` in a scratch copy (not the real files) to confirm the
rename + docblock + sync sequence works end-to-end before trusting it on
the real data.

## MAINTENANCE.md rewritten: translated + corrected (2026-09-08)

Followed up on the fix below by rewriting `Maintenance/MAINTENANCE.md`
entirely in English (per the standing language rule — it was Danish-only)
and correcting everything that was stale or disproven: the type list no
longer mentions `PointOfInterest`/`ExplorationMarker` (never real enum
members, see the CRITICAL note in `goarrow-notes.md`); the ID-band table
matches the script's real `ID_BANDS` (Custom at 85000-89999, no
ExplorationMarker band); the "Removing an entry" section now correctly
explains that `retired="True"` is bookkeeping-only and deletion is the
verified way to actually remove an entry, including the deletion-safety
finding below; stale entry/description counts (the old doc said "5067
existing entries", "881 empty descriptions") were replaced with either
current figures pulled from a fresh `check` run (5207 entries) or softened
to "see the check report" where a hardcoded number would just go stale
again. Delivered alongside the other four files, ready to add to the
GitHub repo as a follow-up push once the first one is confirmed live.

## `retired=` tool bug fixed + deletion-safety verified (2026-09-08)

While preparing this repo's first GitHub push, re-checked `goarrow_maintain.py`'s
`retire` command and the in-file docblock comment against the 2026-09-03
`Location.FromXml` finding (see the Tou-Tou correction below) that GoArrow
never reads a `retired` attribute at all. Found the tool's own `retire`
command, its `check` report line, and the docblock text it writes into the
XML file all still claimed `retired="True"` "hides" the entry — that was
never true and should have been fixed on 2026-09-03. Fixed now: `retire`'s
console output, the `check` report's retired-count line, and the docblock
comment generator (`build_doc_block`) all now correctly describe `retired=`
as bookkeeping-only, and point at deletion as the only verified way to
actually remove an entry from the map. Regenerated the docblock comment in
`locations -DreamWeave_Claude.xml` via `python goarrow_maintain.py docblock`
so the live file's own embedded documentation matches, then re-synced the
mirror file. File entry count unchanged (5207) — this was a documentation/
tooling-output fix only, no `<loc>` entries touched.

**Also verified, resolving an open risk from the 2026-09-03 Tou-Tou NPC
deletions:** the project's standing rule ("existing ids must never be
deleted or renumbered, because GoArrow's `settings.xml` can reference them
by id for recent-locations/favorites/route") raised the question of whether
deleting those 15 entries could crash GoArrow for a player with one of them
saved. Decompiled `MainForm.LoadSettings` (the code that resolves a saved
id against the loaded location database via `LocationDatabase.GetLocation`)
and confirmed both call sites null-check the result before using it — a
saved reference to a since-deleted id is silently skipped, not a crash.
**Conclusion: deleting an entry is safe (verified, not assumed) — GoArrow
will not error — but it does silently drop that one saved favorite/recent/
route reference for any player who had it, with no warning.** This softens
the "never delete" rule from an absolute to a judgment call: prefer keeping
ids stable when there's no strong reason to remove an entry, but deletion
(as was done for the Tou-Tou NPCs) is a safe option when the entry
genuinely needs to stop appearing and no better mechanism exists.

## Tou-Tou destruction cleanup — correction/follow-up (2026-09-03, same day)

Nico caught two problems with the initial cleanup below and asked for a
follow-up:

1. **id=2821 "Tou Tou Settlement Portals" was a pure duplicate, not a moved
   entry.** Nico realized the "relocated" generic hub (id=2821) covers the
   exact same 9 destinations as the already-detailed "Tou-Tou to X Portal"
   band (ids 1452, 1453, 1454, 1850-1854, 2195 — Ariake, Dame Tolani Villas,
   Dryreach Beach Cottages, Nan-Zari, Ong-Hau Village, Snowy Valley, Tou-Tou
   Penninsula Cottages, Tou-Tou Road Villas, Westshore Cottages), confirmed
   by grep against the Archive wiki's Settlement Portals table — exact
   9-for-9 match. **Deleted id=2821 entirely**, superseding the earlier
   in-place relocation edit (that edit should not have happened; the fix was
   deletion, not a coordinate update). The detailed 9-entry band was left
   untouched — it already sits at the correct post-destruction spot.

2. **All 14 old-town-district Tou-Tou NPCs/Vendors needed to go, not just
   get a historical note.** Nico clarified that a historical note is right
   for a *place/record* entry (the Tou-Tou `type="Town"` entry itself,
   id=113, explicitly kept per his instruction) but wrong for *individual
   NPCs* that are simply dead — those should be deleted or deactivated.
   Before choosing, decompiled GoArrow.dll's `Location.FromXml(XmlElement,
   bool)` (method token 0x0600037C, resolving the `FromXml(XmlElement)`
   wrapper at method idx 891) to get the authoritative list of every XML
   attribute the loader actually reads: `id, name, type, NS, EW, exitNS,
   exitEW, dungeonId, customized, use, icon`. No `retired` attribute exists
   anywhere in the binary (confirmed again — no such string literal in the
   whole DLL). The `use` attribute does exist and maps to
   `set_UseInRouteFinding` (method 881) — but cross-referencing every call
   site of `get_UseInRouteFinding` (method 880) across the entire DLL shows
   it is read only from `ShowDetails` (edit panel), `ToXml` (serialization),
   and `FindRoute` (987, the pathfinding/auto-travel calculator) — **never**
   from any map-drawing/render method. Same result for `IsRetired`/
   `IsInternalLocation`: their only callers are a one-time XML-format
   migration worker and the recent-locations/favorites UI, again nothing in
   the draw path. **Conclusion: GoArrow has no attribute that hides a pin
   from the map while keeping the entry loaded — `use="False"` only
   excludes it from route-finding, the pin still renders.** Since the goal
   is "these dead NPCs shouldn't show up," and there is no verified
   "invisible but present" mechanism, the safe and verified choice is
   deletion, consistent with this project's standing rule to never guess at
   unverified DLL behavior for anything that risks visibly wrong or crashy
   output. **Deleted all 14 entries** (which also removes the now-
   inappropriate `HIST_NOTE` text that had been added to 5 of them, since
   the entries themselves are gone): ids 3222 (Armorer Xao Fen), 3233
   (Bai-Nu Ru the Weaponsmith), 3360 (Healer Rili Sou), 3388 (Jeweler Lo
   Dai-Ou), 3411 (Lai Jhong the Archmage), 3443 (Mi Chi the Barkeep), 3502
   (Rou Beh the Bowyer), 3975-3978 (the 4 Scriveners), 1015 (Leather Crafter,
   old-town instance), 3980 and 3982 (Town Crier x2). Explicitly NOT
   touched: id=86 (Leather Crafter, Outpost/Outskirts instance — still
   alive at the new hub), id=113 (Tou-Tou town entry — kept as historical
   reference per Nico's original instruction), and all current
   quest/invasion NPCs (Black Ferah, Shadow Captain/Soldier, Royal/Umbral
   Guard) which are not part of the dead old town.

**Refined takeaway** (replaces the premature one from the same-day initial
cleanup below): an area being destroyed/changed by a game event does not
have one universal treatment. A *place/record* entry (a town, a historical
landmark) can reasonably be kept with a historical note if Nico wants it
preserved as a reference point. A *living NPC/vendor* entry that no longer
exists in the current game state should be deleted outright — GoArrow has
no verified mechanism to keep an entry loaded but hidden from the map, so
"deactivate" is not currently a real option; if that ever changes (e.g. a
future GoArrow version adds a real hide flag), re-verify via decompilation
before using it, per the project's standing "never guess" rule.

File went 5222 -> 5207 (15 deletions: 1 duplicate portal hub + 14 dead
NPCs/vendors). Verified: 0 duplicate ids, 0 bare LF, 0 bad `<locations>`
children, 0 type values outside the verified `LocationType` enum, all 15
target ids confirmed absent.

## Tou-Tou destruction cleanup (2026-09-03)

Nico supplied the "Tou-Tou" and "Tou-Tou/Archive" AC Community Wiki pages and
asked to check our DB against them for deviations. The Archive page is the
pre-destruction town (Sho village); the current page confirms Tou-Tou "has
now been destroyed and taken over by the Shadows" (Cloak of Darkness event)
and is now a 180+ hunting ground, with "The lifestone at the Tou-Tou Outpost
... now the only one in the area" reached via "the Sho (east) wing" of the
Town Network.

Checked against the live file:
- **Scrivener of War/Life/Item/Creature Magic (Tou-Tou)** (ids 3975-3978,
  NS=-27.5 EW=96.2) and **Lai Jhong the Archmage** (id=3411, NS=-27.5
  EW=96.5) — coordinates match Nico's figures and the Archive wiki page
  exactly. Since the buildings these shops sat in no longer exist, appended
  a short historical note to all 5 descriptions (destroyed during Cloak of
  Darkness, kept for historical reference alongside the Tou-Tou town entry)
  rather than deleting or retiring them, mirroring Nico's explicit
  instruction to keep the Tou-Tou `type="Town"` entry (id=113) for
  historical reference. Extended the same treatment to all 4 Scrivener
  siblings even though Nico only named Creature Magic as the example.
- **Tou Tou Settlement Portals** (id=2821, `type="SettlementPortal"`) —
  Nico supplied its new real `/loc` (0xF5590023, landblock_x=0xF5, a real
  outdoor landblock) which converts to NS=-30.41767, EW=94.58505. Updated
  the entry in place (was NS=-27.1 EW=96, the old town-center spot) and
  noted in its description that it relocated near the new Outpost. The new
  coordinate lands almost exactly where the file's existing "Tou-Tou to X
  Portal" destination-specific SettlementPortal band (ids 1452-2195,
  NS=-30.5 EW=94.5) and the "Outskirts" amenities (Bathhouse Lifestone,
  Bind Stone, Leather Crafter, all ~NS=-30.3/-30.4 EW=94.7/94.8) already
  sit — strong independent confirmation this is the right spot.
- **New: Tou-Tou Outpost** (id=75000, `type="Outpost"` — a real, already-
  used LocationType, band 75000 was still empty) at NS=-30.27964,
  EW=94.82006 (from Nico's `/loc` 0xF559003D). Description cross-references
  the lifestone/bathhouse/bind stone/leather crafter cluster already in the
  file and the Town Network route.
- **Found and fixed a pre-existing data bug while checking, unrelated to
  Nico's specific ask:** id=8969 was named "Scrivener of War Magic
  (Tou-Tou)" but sat at NS=13.6 EW=0.7 — Zaikhal's coordinates, sandwiched
  between ids 8970-8972 which are correctly labeled "(Zaikhal)" siblings of
  the same Journeyman/tier set, and an exact duplicate of id=3975's name
  (which correctly IS the real Tou-Tou one). Renamed to "Scrivener of War
  Magic (Zaikhal)" — a straightforward copy-paste mislabel, not a guess.

File went 5221 -> 5222 (net: 1 new entry, 7 in-place corrections, no
deletions). Verified: 0 duplicate ids, 0 bare LF, 0 bad `<locations>`
children, 0 type values outside the verified `LocationType` enum.

**Not yet resolved, flagged for Nico rather than acted on:** the more
detailed "Tou-Tou to Ariake/Snowy Valley/etc." SettlementPortal band (ids
1452-1454, 1850-1854, 2195) already sits at NS=-30.5 EW=94.5 — close to but
not identical to the new hub coordinate, and it's unclear whether those
entrance points also moved or were already at the post-destruction spot
independent of this cleanup. Left untouched pending confirmation.

## Rynthid Infested Plains — remaining portals + Dark Tusker Shrine (2026-09-02)

Nico supplied real `/loc` data (converted with the same verified
`loc_to_ns_ew()` as always) for the rest of the Rynthid Infested Plains
portal list plus some related dungeon content not on the wiki page at all.
All 8 new coordinates cluster tightly with the Rynthid entries added
earlier the same day (Rynthid Foundry/Genesis, Path of Torment, Rynthid
Encampment) — consistent, no conflicts. None matched an *existing* entry by
name within the coordinate-dedup check (closest hits were 0.2-2.0 units
from a DIFFERENTLY-named dungeon, expected in a densely-packed wilderness
zone with 8 distinct named portals per the wiki) — all confirmed genuinely
new. Added, all `type="Dungeon"`, ids 25020-25026:
- **Fear Factory** (id 25020) — entrance only, no exit data supplied.
- **Path of Sorrow** (id 25021) — exit = Platforms of Sorrow.
- **Path of Rage** (id 25022) — exit = Platforms of Rage.
- **Catacombs of Torment** (id 25023) — exit = its surface drop point.
  Description notes it only opens after all 4 "Sanctum Warding Crystal"
  objects are destroyed.
- **Bah'Ktar's Tower** (id 25024) — entrance + a real, distinct (not
  interior-artifact) nearby surface exit.
- **Presk's Bunker** (id 25025) — same pattern.
- **Rynthid Access Dungeon** (id 25026) — entrance only; near (not
  containing) the Seed of Anger/Misery/Hatred quest objects.

**Correction, same day:** the 4 Sanctum Warding Crystals and the 3 Seed
objects were initially folded into their parent dungeons' descriptions
(treated as in-place puzzle furniture, per the 6-lever-cluster restraint
convention). Nico corrected this — he wanted them as their own standalone
pins, and pointed out the Seeds are not physically inside Rynthid Access
Dungeon but sit beside it/each other outdoors. Reversed: descriptions on
25023 and 25026 trimmed back to remove the folded-in detail, and 7 new
`type="Custom"` entries added instead (ids 85115-85121, continuing the
statue/hatch extraction's Custom band):
- Sanctum Warding Crystal (Ground Level) — id 85115
- Sanctum Warding Crystal (Platforms of Sorrow) — id 85116
- Sanctum Warding Crystal (Platforms of Rage) — id 85117
- Sanctum Warding Crystal (Platforms of Torment) — id 85118
- Seed of Anger — id 85119
- Seed of Misery — id 85120
- Seed of Hatred — id 85121

Each crystal's description cross-references the other 3 (destroying all 4
opens the portal to Catacombs of Torment); each seed's description
cross-references the other 2 and notes it sits near Rynthid Access Dungeon.
**Takeaway:** the "fold puzzle furniture into the parent's description"
restraint convention is a default, not a rule — it applies to items that
are genuinely inline set-dressing, not to named, individually-quest-relevant
objects the player needs to find one by one. When in doubt, ask rather than
assume restraint is wanted; Nico's Frozen Valley/lever precedent doesn't
generalize to every multi-object cluster automatically.

Also added **Dark Tusker Shrine** (id 20006, `type="Landmark"`, near
Whispering Caverns — id 4267, ~0.13 units away, a different object at
essentially the same spot) — Nico asked for this one only if it's
permanent. Checked: it's a normal `landblock_instance` placement (the same
mechanism as every other confirmed-permanent object this whole project) with
no entry in `weenie_properties_event_filter` tying it to a quest/event gate
— nothing in the DB suggests it's a removed or time-limited seasonal prop,
so added as permanent content. Description is the object's own in-game
lore text pulled from `weenie_properties_string`.

File went 5206 -> 5214 -> 5221 (7 more after Nico's correction). Verified
after each step: 0 duplicate ids, 0 bare LF, 0 bad `<locations>` children,
and every `type=` value re-checked against the verified `LocationType` enum
from the earlier `PointOfInterest` fix (see below) — all clean.

## Other DB angles investigated (2026-09-02) — mostly dead ends, noted for the record

Nico asked for more ideas after the statue/hatch win, so the same
coordinate-dedup methodology was run against several more DB angles:
- Any other `weenie_properties_emote_action` type besides 99 (TeleportSelf)
  that ever carries position data: only `type=63`, 9 rows — turned out to
  be the standard Academy "newbie exit" portals to Yaraq/Holtburg/Sanamar/
  Shoushi. Certainly already covered. Not actioned.
- Any weenie with a real `weenie_properties_position` Destination
  (position_Type=2) OTHER than the 3269 type=7 Portals: only 4 hits, all
  portable "Stamped Gem" items (Marketplace/Town Network/Drift/Mines) —
  carried items, not fixed map locations. Not actioned.
- **Bindstones** (type=25 in DB... wait, type=65): 25 DB placements vs 26
  existing file entries — essentially fully covered, negligible gap. Not
  actioned.
- **Lifestones** (type=25): 256 DB placements vs 223 existing file entries.
  The ~46 apparently-uncovered ones cluster suspiciously at a fixed
  landblock-edge column regardless of which town they're near (looks like
  duplicate/test placements, not real distinct towns) — flagged as
  ambiguous, needs manual eyeballing rather than a blind batch add. Not
  actioned; parked.
- **Vendor NPCs** (type=12, 1196 total, ~786 of which are the file's
  existing `Vendor` type): 182 outdoor placements don't match an existing
  NPC/Vendor entry, but the overwhelming majority are roaming/patrol
  vendors (Peddler, Roaming Bowyer, Merchant, Farmer, seasonal Snowman
  event vendors — by nature not tied to one fixed spot) or Academy/tutorial
  NPCs sitting in a similar reserved edge-column as the lifestone
  duplicates. A small handful of real, uniquely-named, non-roaming hits
  stood out (Dark Tusker Shrine — actioned above; Olthoi Matron x2; Kaneth
  al-Evv; two Purser+Archmage pairs near Aerlinthe) — not yet reviewed
  individually, parked pending Nico's direction.

Verdict communicated to Nico: no second goldmine like the statues: this
pass. Housing (type=53, 6275 instances) also sampled and confirmed to be
individual player houses, not something to enumerate.

## CRITICAL FIX #2 (2026-09-02): `type="PointOfInterest"` isn't a real GoArrow type — crashed the load again

Nico hit a second load-crashing bug the same day, right after the statue/
hatch extraction: `System.ArgumentException: Den ønskede værdi
'PointOfInterest' blev ikke fundet` at `Location.FromXml` ->
`Enum.Parse(typeof(LocationType), value)`.

Root cause: `type=` is parsed with a plain, case-sensitive `Enum.Parse`
against GoArrow's own `LocationType` enum — no fallback, no tolerance for
an unrecognized string. `"PointOfInterest"` (and `"ExplorationMarker"`,
never actually used) were added to `KNOWN_TYPES` earlier this project on a
guess — reasoning that `_Unknown` being tolerated meant *any* unrecognized
string would be tolerated. That reasoning was wrong: `_Unknown` isn't a
generic fallback, it's just its own specific, real enum member.

Fixed properly this time, with ground truth instead of another guess:
decompiled `GoArrow.dll` itself (already had a local copy from the earlier
`retired="True"` investigation) with `dnfile`, found the `TypeDef` for
`GoArrow.RouteFinding.LocationType`, and read its actual field list. The
complete, real enum:
`_Unknown, Any, AnyPortal, AllegianceHall, Bindstone, Dungeon, Landmark,
Lifestone, NPC, Outpost, Portal, PortalHub, SettlementPortal, Village,
Town, TownPortal, UndergroundPortal, Vendor, WildernessPortal,
PortalDevice, Custom, _StartPoint, _EndPoint`. Every type value already in
use elsewhere in the file (17 distinct values, 5091 pre-existing entries)
checks out against this list — only the just-added, guessed
`"PointOfInterest"` was ever invalid.

Fix: all 115 statue/hatch entries (ids 85000-85114) changed from
`type="PointOfInterest"` to `type="Custom"` (a real, valid member — good
semantic fit for "not a dungeon/portal/NPC, but a notable interactive
marker"). `goarrow_maintain.py`'s `KNOWN_TYPES`/`ID_BANDS` updated to match
the verified enum (`PointOfInterest`/`ExplorationMarker` removed; `Any`,
`AnyPortal`, `Portal`, `PortalDevice`, `Custom` added as confirmed-real,
though only `Custom` has entries using it so far; `_StartPoint`/`_EndPoint`
deliberately excluded — they look like GoArrow's own internal route
markers, not something a locations file should set). Verified again after
the fix: 5206 entries, 0 duplicate ids, 0 bare LF, 0 bad `<locations>`
children, and every `type=` value in the file now cross-checked against the
real decompiled enum, not just against KNOWN_TYPES (which was itself the
thing that was wrong).

**Takeaway for future type additions:** never add a new `type=` value to
`KNOWN_TYPES` based on "GoArrow probably tolerates it" reasoning — always
verify against the actual `LocationType` enum in `GoArrow.dll` (via
`dnfile`, same method as above) before it's ever written into a real
`<loc>` entry, not just before using it "at scale". A local copy of
`GoArrow.dll` is at `/mnt/user-data/uploads/GoArrowVVSEdition/GoArrow.dll`
in the analysis environment.

## CRITICAL FIX (2026-09-02): the file could not actually load in GoArrow

Nico hit `System.InvalidCastException: ... 'System.Xml.XmlComment' ... cannot
... be cast to ... 'System.Xml.XmlElement'` at `GoArrow.RouteFinding.
LocationDatabase.LoadLocationsXml` when trying to load the file in-game.

Root cause: GoArrow's own XML loader iterates the direct children of
`<locations>` and casts every one straight to `XmlElement`, with no check for
node type first. The file's auto-generated documentation block (the
"BEGIN/END DREAMWEAVE CUSTOM ID DOCS" `<!-- -->` comment, explaining the
ID_BANDS convention) sat as a *child* of `<locations>` — three comment nodes
right after the opening tag, before the first real `<loc>`. Any XML parser
tolerates that structurally, but GoArrow's loader does not: the very first
comment node it hits throws. This predates the whole session — the same
comment block already sat in that exact spot in the earliest available
backup — so **the file has likely never actually been loadable in real
GoArrow this whole project**, and nobody had tried loading it in-game to
notice until now.

Fixed in both `locations -DreamWeave_Claude.xml` and the mirror
`locations -DreamWeave.xml`: the doc-block comment now sits *before* the
`<locations ...>` opening tag (between the `<?xml ?>` declaration and the
root element) — a comment there is a sibling of the root, never a child, so
GoArrow's loader never sees it. Verified with a structural check (walked
`<locations>`'s direct children via `xml.dom.minidom` and confirmed zero
non-element/non-text nodes) on both files, not just re-parsing with
`ElementTree` (which would have passed even on the broken version, since
comments are perfectly valid XML — this bug is about GoArrow's loader being
stricter than the XML spec, not about validity).

Also fixed at the source: `cmd_docblock` in `goarrow_maintain.py` used to
insert the block right after `<locations ...>`'s opening tag — that's the
exact bug. It now always removes any existing block (wherever it is) and
re-inserts it before `<locations`, so this is self-healing on the next
`docblock` run even if something reintroduces the old placement.

**Filename mystery resolved:** Nico renames the downloaded file himself on
purpose, for his own version control — not because GoArrow is configured to
a different literal filename. No tooling change needed there.

**Still open:** the mirror file `locations -DreamWeave.xml` was very stale
(last touched 2026-08-31, before this whole session's ACE import work) —
only its comment placement was fixed, its *content* was not resynced from
`_Claude.xml`, and it has drifted further since (today's additions below
went only into `_Claude.xml`). Needs a decision on whether/when to run a
full `sync`.

## Missing content follow-up (2026-09-02)

Nico reported 5 possibly-missing locations (Viridian Rise, Hoshino Fortress
(area), Dark Isle, Rynthid Infested Plains, Hoshino Fortress (area) again)
plus a hypothesis that the original ACE extraction needed extending to
statues/hatches/etc. Investigated each:

- **Dark Isle** — already fully covered (id 3860 "The Deep (Dark Isle)",
  id 3862 "Dark Isle Portal"). Not actioned; flagged to Nico in case
  something more specific was meant.
- **Frozen Valley** and **Tou-Tou** (2 more wiki PDFs Nico sent to check the
  same way) — both already essentially 100% covered by pre-existing
  entries, confirmed by coordinate match against every point on both wiki
  pages (Frozen Valley: ids 9402-9405, 9434, 9444-9445, 9448, 9515-9516;
  Tou-Tou: ids 9454, 9495-9498, 87, 2694, 2760, 9303, 679/9075, and more,
  including "Shadow Vortex" at id=9514 matching the wiki's dungeon list
  entry within 0.22 coordinate units). No action needed.
- **Rynthid Foundry / Rynthid Genesis / Hoshino Tower** — NOT a DB
  extraction gap. These already existed as unreviewed low-confidence `new`
  candidates in `ace_import_candidates.json` from the original extraction
  (weenie classes 51669/51615/46619+46620), just never applied. Coordinates
  cross-checked against the wiki PDFs and matched. Enriched with real
  descriptions and applied as new `Dungeon` entries: id=25015 (Rynthid
  Foundry), id=25016 (Rynthid Genesis), id=25017 + id=25018 (Hoshino Tower
  — two separate real spawn points, both leading to the same destination,
  same pattern as the existing "Direlands Portal" multi-entry precedent).
- **Rynthid Infested Plains** / **Hoshino Fortress (area)** — these are
  region/zone labels, not individual DB weenies (same category as
  "Direlands"/"Obsidian Plains" elsewhere in the file). Added as new
  `Landmark`/`Dungeon` entries from the wiki's own coordinates, after
  confirming no existing coverage within 3 map units: id=20002 (Rynthid
  Encampment), id=25019 (Path of Torment, Dungeon — no destination given by
  the wiki, added with no exit), id=20003 (Royal Tent), id=20004 (Hoshino
  Town #2), id=20005 (Hoshino Town #3). The wiki's route note ("Stonehold
  portal → Desolation Beach at 69.7N 20.2W") was already fully covered by
  existing ids 1451/1216 — nothing new needed there.
- **Viridian Rise / statue-hatch hypothesis — confirmed, and now built.**
  The original ACE extraction filtered on `weenie_Type=7` (Portal) only.
  Live-queried the still-loaded `ace_world` MariaDB: 153 distinct `type=10`
  weenies (statues, altars, gatestones, colored levers, hatches, a
  sarcophagus, etc.) use a completely different, script-driven teleport
  mechanism instead — a `weenie_properties_emote` "quest emote" whose
  `weenie_properties_emote_action` (`type=99`, `TeleportSelf`) carries the
  real destination `obj_Cell_Id`/`origin_X`/`origin_Y`, decoded with the
  same verified `loc_to_ns_ew()` used everywhere else. Some (e.g. "Ancient
  Statue of the Viridian Rise") have more than one possible destination
  (a random-teleport puzzle mechanic).

  Nico's design call: plot every one of these in, but only set an
  `exitNS`/`exitEW` when there is exactly one possible destination — leave
  it off when there are 0 or multiple. Type chosen: `PointOfInterest`
  (already reserved in `KNOWN_TYPES`/`ID_BANDS` for exactly this kind of
  case, previously unused — first real-scale use of it; `_Unknown` already
  proves GoArrow tolerates an unrecognized type string without crashing, so
  risk is judged low, but Nico should confirm a reload still works).

  Of the 153: 27 have no static `landblock_instance` placement at all
  (Viridian Portal x12, Gauntlet Stage 5 x5, Zenith x4, Sarcophagus of the
  Recluse, Deewain's Chamber, Escape Portal — all look encounter/instance-
  spawned rather than fixed map points) — skipped, no coordinate to plot.
  15 more turned out to be sitting at (or within ~1 unit of) an existing
  entry with the same name — e.g. "Summoning Cave", "Shadow Vortex",
  "Dark Cavern", "Ancient Portal", the "Resonating Crystal" pair — these are
  puzzle furniture *inside* dungeons we already have a portal entry for, so
  skipped per the standing coordinate-proximity dedup rule. The remaining
  **115 were added** as new `PointOfInterest` entries, ids 85000-85114
  (that whole band was empty before today). Noteworthy cluster worth a
  second look: 6 colored levers (Blue/Green/Orange/Red/White/Yellow, ids in
  that range) sit within ~0.08 EW of each other and all resolve to the same
  single destination — likely one physical puzzle room; kept as 6 separate
  entries per Nico's "just plot them in" instruction, but flagged in case
  he'd rather collapse them to one.

  Not yet done: no wiki-sourced descriptions were available for these 115
  (unlike the Rynthid/Hoshino items above), so each just got a generic,
  accurate one-liner ("teleports you to a fixed destination" / "randomly
  teleports you to one of N possible destinations"). Could be enriched
  individually later if worth the effort.

File went from 5067 -> 5091 (quick wins) -> 5206 (statue/hatch extraction)
entries this pass. Verified after each step: 0 duplicate ids, 0 bare LF,
0 non-element/non-text children of `<locations>`.

## Active

- **ACE database import review** — working through
  `ace_import/ace_import_candidates.json` (2,273 candidates extracted from
  the DreamWeave server's own ACE database) per the recommended order in
  `ACE_DATABASE_ANALYSE.md`:
  1. `import-ace --action enrich_exit` (681 items) — **DONE** for 608 of 633
     unique targets:
     - 4 entries where all proposed exits agreed exactly — applied
       (ids 9238, 4288, 4365, 4400).
     - 604 entries with one single, unambiguous proposed exit — Nico
       reviewed `Maintenance/ace_import/review_enrich_exit_clean.csv` and
       confirmed (any candidate with a source weenie class = trusted) —
       all 604 applied.
     - 25 entries (66 rows) where proposals genuinely disagreed — NOT run
       through plain enrich_exit. Of these, the 10 "X Settlement Portals"
       clusters are now handled (see below, DONE). The other 15
       (non-Settlement dungeons/landmarks) are still open — see below.
  2. `import-ace --action enrich_description` (23 items) — not started (next up)
  3. `import-ace --action new`, high-confidence only (513 items) — not started
  4. `import-ace --action new --include-low-confidence` (1,056 more) — decision pending
  5. ~~Add `Dungeon` to `PORTAL_LIKE_TYPES`~~ — **DONE**, Nico confirmed.

- **Settlement Portals split — retype kept, new entries REVERTED (mistake
  found and corrected same session).** Nico confirmed these are a real,
  distinct existing type (`SettlementPortal`, outdoor), so the retype of all
  26 "X Settlement Portals" entries (ids 2800-2825) from `PortalHub` to
  `SettlementPortal` stands. But the 28 new child entries added for the 10
  ACE multi-destination clusters (ids 35000-35027) turned out to be exact
  duplicates: Nico later shared the AC Community Wiki's "Settlement Portals"
  page (all 26 towns, 378 named destinations with coordinates), and
  cross-checking it against the file surfaced a pre-existing, far more
  complete network of 377 `SettlementPortal` entries (ids roughly
  1300-2000, e.g. "Al-Arqas to Al-Hatar Settlement") already covering
  essentially all 378 wiki entries, each already correctly typed with real
  `exitNS`/`exitEW`. This network predates this whole session (present in
  the earliest available backup) and was missed during the original ACE
  extraction/matching pass — an oversight worth remembering: always check
  for a same-concept pre-existing entry by coordinate proximity, not just by
  the specific name pattern being searched for. The 28 duplicate entries
  were deleted outright (not retired — they were only minutes old, nothing
  could reference them yet). Net effect of the whole Settlement Portals
  thread: 26 entries retyped PortalHub->SettlementPortal, net 0 new entries,
  file back to 5067 total (403 SettlementPortal entries: 377 original + 26
  retyped).
  **Open question for Nico:** now that the full 377-entry "Town to
  Destination" network is known, are the 26 generic "X Settlement Portals"
  hub markers still worth keeping alongside it, or are they themselves
  redundant with the more detailed network? Not acted on either way yet.

- **15 non-Settlement multi-exit entries** (same "one entry, multiple real
  destinations" shape). Root cause finally understood: a dungeon-interior
  destination's landblock always has `landblock_x = 0` (a quirk of how AC
  numbers dungeon interiors, confirmed against ACEmulator's own LandblockId
  logic), which the standard NS/EW formula mechanically decodes to
  `exitEW` in roughly the -99 to -102 band regardless of where inside the
  dungeon the point actually is. This is NOT a deliberate "void-grid" design
  like Town Network's legend grid (that earlier framing was wrong and has
  been retracted to Nico) — it's a byproduct of AC's own coordinate system.
  It also turns out to be the file's own long-standing, pre-session
  convention: 559 pre-existing `type="Dungeon"` entries already store
  exactly this kind of value in exitNS/exitEW, so the 104 (of the 608
  already-applied `enrich_exit` results) that show this pattern are correct
  as they stand, not a data-quality bug — no revert needed.

  Status of the 15:
  - **DONE — Path of the Blind (dungeonId=42) + Egg Orchard (dungeonId=43):**
    Nico confirmed both are three real, physically distinct entrances (Main/
    East/West) that all lead to visibly-identical mirrored dungeons. Each
    now has its own `<loc>` with its own real entrance NS/EW and its own
    exit (Egg Orchard's is the dungeon-interior-decode value; Path of the
    Blind's happens to share one exitEW across all three, consistent with
    the pattern above). New ids: Egg Orchard East=25002, Egg Orchard
    West=25001, Path of the Blind West=25003, Path of the Blind East=25004.
  - **DONE — Cells of the Black Book, Forgotten Tunnels, Arena, Sand Caves:**
    Nico confirmed/supplied exact per-weenie `/loc` data for each. These are
    multiple real, close-together physical entrances to the *same* named
    dungeon (no East/West-style distinguishing names exist for them), so —
    matching the file's own established precedent for this shape (e.g. the
    8 identically-named "Mannikin Foundry Portal" entries sharing
    `dungeonId="21594"`) — each became multiple `<loc>` entries with the
    *same* name, each with its own real entrance coordinate. Exits applied
    where known (Cells of the Black Book, Arena, Sand Caves); Forgotten
    Tunnels has none, per Nico ("There's no exit portals"). `dungeonId` was
    only set where already known from an existing sibling (Arena=738); left
    unset for the other three groups, since dungeonId values are real
    external dungeon-catalog numbers and there was no reliable way to look
    theirs up. New ids: Cells of the Black Book 25005/25006/25007, Forgotten
    Tunnels 25008/25009, Arena 25010, Sand Caves 25011/25012.
  - **DONE — the rest ("Pattern D" extraction-match fixes), all confirmed with
    Nico's own `/loc` data 2026-09-02:**
    - **Coral Tunnels East/West Harbor** (2827/2829, `dungeonId="748"`):
      confirmed as two entrances to one underwater tunnel connecting the two
      harbors at Aerlinthe — a shortcut loop, so each side's exit lands you
      right back in front of that same entrance. Both now have their real
      exitNS/exitEW (no NS/EW change needed, those were already correct).
    - **Abandoned Shops Portal (1299) / Nor's Folly Portal (new, id=25013):**
      confirmed as two different dungeons standing near but not on top of
      each other (wrongly merged into one ACE match originally). 1299 kept
      its identity/dungeonId=345 with a corrected NS/EW and real exit; Nor's
      Folly Portal is a new, separate entry with no dungeonId (different
      dungeon, real value unknown) and an empty description (no ACE
      long_desc available — leave for a future `enrich_description` pass
      rather than inventing quest lore).
    - **Temple of Xik Minru (3680) / Upper Sanctum of Xik Minru (new,
      id=25014):** confirmed as two different dungeons with different
      content sitting at nearly the same spot (Upper Sanctum is up on a
      floating islet, hence the very different Z originally noted). 3680
      kept dungeonId=240 with a corrected NS/EW and its real (non-artifact)
      surface exit; Upper Sanctum is new, no dungeonId, exit falls back to
      the dungeon-interior-decode value since Nico didn't have a real
      surface exit for that one specifically (consistent with the file's
      established convention for that case — see the LESSON above).
    - **Karlun's Fort (3006, `type="Landmark"`) / Exit Karlun's Fort (new,
      id=20001, also Landmark):** confirmed as a fort atop a mountain — one
      portal up (real "entrance" position + a real exit into the fort
      interior, both now on 3006), and a second, separate portal inside the
      fort that takes you back down (now its own entry, exit sourced from
      the earlier ACE candidate since Nico's new data only covered its own
      in-fort position).
    - **Renegade Fortress (2738):** resolved the original two-candidate
      conflict — Nico's fresh `/loc` chain (outer gate → entrance portal →
      dungeon interior → surface exit) confirms the dungeon-interior
      destination (-45.09414, -23.125) is the correct, REAL one (not an
      artifact, landblock_x≠0 for this one) matching the `portalrenegadefortress`
      candidate; the other conflicting candidate (`ace40349-renegadefortress`,
      artifact-band -101.775) was stale/wrong and is disregarded. NS/EW
      updated to the real entrance-portal position, exit set to the real
      dungeon-interior value.
  - **Pattern C — parked, revisit after the above:** Frost Ziggurat /
    Prismatic Ziggurat (2294), Proving Grounds Extreme / Proving Grounds
    Uber (9089), Eldrytch Web Stronghold / Eldrytch Web Gauntlet (4368),
    Celestial Hand Stronghold / Celestial Hand Gauntlet (4367) — each pair
    sits at virtually the identical spot (normal-mode/hard-mode portal
    choice, not two physical doors), so the plan is one entry per location
    with both portal names/exits folded into the description rather than
    duplicate map pins. Not yet applied — Nico asked to come back to this
    after the two items above.

## Paused

- **DreamWeave-GoArrow-Data GitHub repo**
  (https://github.com/DraxxD/DreamWeave-GoArrow-Data) — created by Nico, not
  yet populated. Paused until the ACE import review above is done, so the
  repo's first upload is the cleaned-up result rather than a moving target.
  No GitHub connector is available to Claude in this environment; populating
  it will need either a manual web upload or Claude driving the browser —
  to be decided when we get back to it.

## Open design questions (not blocking the ACE import review)

- **Marae Lassel realm overlap** — confirmed old/new Marae Lassel share exact
  coordinates and both stay permanently accessible (not a cutover). No
  solution built yet; likely needs two location files (one per Realm), since
  GoArrow has no per-entry world/realm attribute and loads only one file at a
  time. Needs a concrete design pass once the current import work is done.
- **`retired="True"` behavior unverified** — static analysis of GoArrow.dll
  found no evidence the plugin actually hides `retired="True"` entries
  in-game. Needs an empirical in-game test (mark a throwaway entry, reload,
  check). Matters for the Marae Lassel question above, and for the general
  retire convention's usefulness.
- **Drift Network hub entries** — not yet added; plan is to mirror the
  existing Town Network two-tier pattern (real-coordinate "front door" entries
  + a synthetic legend grid in unused void space), per the discussion on
  2026-09-02.
- **data_cod.xml (Darktorizo's GoArrow_Data_CoD repo)** — superseded by Nico's
  own DreamWeave-GoArrow-Data repo; no plan to push to or pull from it.

## Housekeeping flag

- **MAINTENANCE.md is currently written in Danish.** This conflicts with the
  English-only rule for project files (Dev team and end users don't read
  Danish). Not yet translated — flagging so it doesn't get missed; will need
  a dedicated pass since it's a large document.

## Tooling fixes (found and fixed 2026-09-02, while adding the Dungeon
## multi-entrance entries above)

- **`next_id_for_type` could collide with the doc-block's own example ids.**
  The file's auto-generated documentation comment (top of file, "EXAMPLES")
  shows one sample `<loc>` per type using that type's very first band id
  (10000, 15000, 20000, 25000, 50000, 65000). `next_id_for_type` only scans
  real, ET-parsed `<loc>` elements, so it never saw those commented-out
  examples as "taken" — meaning the FIRST real entry ever added to an
  untouched band would be assigned the same id as the example, and the
  tool's own regex-based edit functions (which work on raw text, not
  parsed XML, and can't tell a comment from a real tag) would then find two
  matches and refuse to proceed. Hit in practice adding the first-ever
  `Dungeon`-band entry (id 25000, "Egg Orchard East") this session. Fixed:
  added a `RESERVED_EXAMPLE_IDS` set and made `next_id_for_type` skip it.
  The one real entry that had already been assigned id 25000 before the fix
  was renamed to 25002.
- **A one-off rename script corrupted the file's CRLF line endings.** Used
  `Path.read_text()` (Python's default universal-newlines mode) instead of
  `goarrow_maintain.load_text()` to fix the id-25000 collision above — that
  silently converted every `\r\n` in the whole file to a bare `\n` on read,
  and the subsequent `newline=''` write preserved the damage. Caught by the
  project's own bare-LF consistency check (`data.replace(b'\r\n', b'').count(b'\n')`
  should always be 0) before delivery, and fixed by normalizing the whole
  file back to CRLF. Lesson: never touch this file with a plain
  `Path.read_text()`/`.write_text()` or any file op that doesn't explicitly
  pass `newline=''` — always go through `goarrow_maintain.py`'s own
  `load_text`/`ENCODING`/`NEWLINE` constants, even for a "trivial" one-line
  fix.
