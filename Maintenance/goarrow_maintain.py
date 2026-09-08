#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
goarrow_maintain.py
--------------------
Vedligeholdelsesværktøj til GoArrow's locations-database.

To filer indgår (navnekonvention besluttet 2026-09-08, se
Maintenance/MAINTENANCE.md):
    locations[DreamWeave_NNN].xml -- MASTER. Det er denne fil scriptet
        redigerer. NNN er et fortløbende, aldrig-genbrugt versionsnummer
        (001, 002, ...). Kun lokal (Nico's maskine + levering her fra) --
        skal ALDRIG lægges i GitHub-repoet.
    locations.xml -- SPEJL/deploy-klar. Fast filnavn, ingen versions-tag --
        det er DEN fil der ligger i GitHub-repoet, og den GoArrow's
        settings.xml skal pege på. Opdateres kun via "sync"/"bump", aldrig
        redigeret direkte.

Formål: gøre det let at tilføje ny content og løbende holde filen konsistent,
UDEN at ændre selve arkitekturen (samme tags, samme attributter, samme
fysiske linjeformat som GoArrow selv skriver/læser).

Kommandoer:
    check   -- kører en fuld konsistens-rapport (kør denne før og efter en push)
    add     -- guidet, valideret tilføjelse af en ny <loc>-post
    loc     -- konverterer en rå /loc-tekst fra spillet til NS/EW (uden at
               tilføje noget til filen -- bare en lommeregner)
    enrich  -- forsøger at fylde TOMME beskrivelser med tekst slået op på en
               MediaWiki-wiki (fx acpedia.org), én post ad gangen med din
               godkendelse -- rører aldrig en post der allerede har tekst
    import-ace -- gennemgår kandidater udtrukket af serverens egen ACE
               world-database (portaler + points_of_interest) og
               tilføjer/beriger poster, én ad gangen med din godkendelse
               (se Maintenance/ACE_DATABASE_ANALYSE.md)
    sync    -- kopierer master-filen over spejl-filen ("locations.xml"), så
               de to holdes identiske efter en redigering
    bump    -- ny version: omdøber master-filen til næste versionsnummer,
               genindsætter docblokken (med det nye Version:-tal indbygget)
               og synkroniserer spejl-filen -- den ene kommando der bør
               bruges for hver ny "release", så filnavn, indbygget
               version-linje og spejl-fil aldrig kan komme ud af trit

Kør uden argumenter for interaktiv menu, eller brug --help for CLI-flag.

VIGTIGT: Scriptet redigerer filen med tekst-niveau indsættelse (ikke en XML-
serializer), netop for at bevare BOM, CRLF, indrykning og attribut-rækkefølge
1:1 som GoArrow selv forventer. Det tager altid en .bak-sikkerhedskopi før
det skriver noget.
"""

import argparse
import json
import re
import shutil
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import datetime
from pathlib import Path

# ----------------------------------------------------------------------------
# Kendt skema, udledt af den eksisterende fil (se analyse-rapporten).
# Opdatér disse lister HVIS I bevidst udvider skemaet -- så følger værktøjet med.
# ----------------------------------------------------------------------------

KNOWN_TYPES = [
    "NPC", "Vendor", "Landmark", "Dungeon", "Village", "SettlementPortal",
    "Lifestone", "PortalHub", "WildernessPortal", "UndergroundPortal",
    "Town", "TownPortal", "AllegianceHall", "Outpost", "Bindstone",
    # Verificeret 2026-09-02 ved at dekompilere selve GoArrow.dll'et
    # (GoArrow.RouteFinding.LocationType-enum'et, via dnfile) -- IKKE gættet.
    # Location.FromXml kalder Enum.Parse(typeof(LocationType), value) uden
    # ignoreCase, så `type=` SKAL matche et af enum'ets medlemmer PRÆCIST,
    # ellers crasher HELE fil-indlæsningen med en System.ArgumentException
    # (opdaget i praksis 2026-09-02: 115 nyoprettede poster brugte det
    # tidligere gættede "PointOfInterest", som slet ikke findes i enum'et --
    # rettet til "Custom" nedenfor, som RENT FAKTISK er et gyldigt medlem).
    # De resterende medlemmer her er reelle men uden kendt/afprøvet brug i
    # denne fil endnu -- foretræk en allerede brugt type hvor den semantisk
    # passer, men de kan trygt bruges, da de er bekræftet i selve enum'et:
    "Any", "AnyPortal", "Portal", "PortalDevice", "Custom",
    # _StartPoint/_EndPoint findes også i enum'et, men ser ud til at være
    # interne markører GoArrow selv sætter (rute-start/slut), ikke beregnet
    # til brug i en locations-fil -- udelades bevidst her.
    #
    # _Unknown holdes sidst på listen -- det er en generisk opsamlingstype
    # for poster der ikke passer i noget andet, så den hører naturligt til
    # for enden, ikke midt i de meningsfulde typer.
    "_Unknown",
]

# Typer hvor exitNS/exitEW er den etablerede konvention (>90% af forekomsterne
# i den eksisterende fil ligger her). Andre typer KAN have det, men værktøjet
# advarer, så det er et bevidst valg og ikke en tastefejl.
PORTAL_LIKE_TYPES = {
    "SettlementPortal", "PortalHub", "UndergroundPortal",
    "WildernessPortal", "TownPortal", "Dungeon",
}

# ----------------------------------------------------------------------------
# ID-bånd for NY content (fra id 10000 og opefter -- eksisterende id'er
# 1-9539 er ALDRIG i spil for omnummerering: GoArrow's settings.xml
# gemmer brugerens "recentLocations", "route" og "favoriteLocations" med
# netop disse id-værdier som nøgle. Ændres et eksisterende id, peger de
# gemte referencer på den forkerte -- eller ingen -- lokation.
#
# Bånd er derfor kun en fremadrettet konvention: alt NYT I tilføjer får et
# id der fortæller typen, uden at et eneste eksisterende id rører sig.
# Bredden (5000) kan frit øges her, hvis en type vokser sig for stor til
# sit bånd -- der er rigeligt luft mellem båndene til det.
# ----------------------------------------------------------------------------

ID_BAND_WIDTH = 5000

# Deøverste linjer i filen indeholder en (udkommenteret) EKSEMPEL-blok der
# viser hvordan en post af hver type ser ud (se build_doc_block/cmd_docblock).
# Disse eksempler bruger med vilje netop hvert bånds FØRSTE id (10000, 15000,
# 20000, 25000, 50000, 65000), fordi det er det mest naturlige eksempel-id at
# vise. Problemet: de ligger inde i en XML-kommentar, så ET.parse (som kun
# ser rigtige <loc>-elementer) aldrig opdager dem -- men vores egne
# regex-baserede tekst-funktioner (fx add_exit_coords_in_text,
# _find_loc_tag_span) arbejder direkte på rå tekst og ser IKKE forskel på en
# kommentar og en rigtig post. Uden denne liste ville next_id_for_type for et
# bånd der aldrig har haft en rigtig post endnu, roligt foreslå det samme id
# som eksempel-blokken allerede bruger -- hvilket giver "2 poster fundet"-fejl
# så snart man bagefter prøver at redigere den nye post. Opdaget i praksis
# 2026-09 ved tilføjelsen af Dungeon-bånd id 25000 (kolliderede med
# "Example Custom Dungeon").
RESERVED_EXAMPLE_IDS = {10000, 15000, 20000, 25000, 50000, 65000}

ID_BANDS = {
    "NPC": 10000,
    "Vendor": 15000,
    "Landmark": 20000,
    "Dungeon": 25000,
    "Village": 30000,
    "SettlementPortal": 35000,
    "Lifestone": 40000,
    "PortalHub": 45000,
    "WildernessPortal": 50000,
    "UndergroundPortal": 55000,
    "Town": 60000,
    "TownPortal": 65000,
    "AllegianceHall": 70000,
    "Outpost": 75000,
    "Bindstone": 80000,
    "Custom": 85000,
    "_Unknown": 95000,
}

# Tekst-konvention til custom DreamWeave-indhold (content der ikke findes i
# stock Asheron's Call). Ingen ny attribut -- tagget lever inde i det
# eksisterende beskrivelsesfelt, som første ord, så det er let at grep'e
# efter og let at filtrere fra igen, uden at skemaet ændres.
CUSTOM_TAG = "[DreamWeave Custom]"

# Attribut der viser hvilken månedlig patch/update en NY post blev tilføjet
# i (format "YYYY-MM", fx "2026-09" -- sorterer og filtrerer korrekt som
# tekst). Sat af `add` på ALLE nye poster (ikke kun custom-content), da
# spørgsmålet er generelt: "hvilken patch kom denne lokation med i". De
# eksisterende 5067 poster får den aldrig sat retroaktivt -- fravær af
# attributten betyder "tilføjet før dette blev sporet", ikke en fejl.
PATCH_DATE_FORMAT = "%Y-%m"

# Kendte MediaWiki-baserede AC-wikier til `enrich`. Begge er bekræftet at
# køre MediaWiki (via URL-mønstret /wiki/Sidenavn og index.php?...&action=edit),
# så de har i princippet en gratis, offentlig api.php -- MEN begge kan finde
# på at blokere automatiske opslag (bot-beskyttelse, fx Cloudflare), hvilket
# `enrich` selv opdager og falder tilbage til manuel indsættelse ved.
WIKI_BASES = {
    "acpedia": "https://acpedia.org",
    "fandom": "https://asheron.fandom.com",
}
DEFAULT_WIKI = "acpedia"
WIKI_USER_AGENT = "GoArrowMaintain/1.0 (personligt DreamWeave-vedligeholdelsesscript, ikke-kommercielt)"
WIKI_REQUEST_DELAY = 1.0  # sekunder mellem opslag -- høflig rate-limit mod en gratis, delt wiki

# Master (source-of-truth, det scriptet redigerer) filnavn følger mønstret
# locations[DreamWeave_NNN].xml, NNN = zero-padded, fortløbende versionsnummer
# (Nico's egen konvention, besluttet 2026-09-08). Genbrug/sænk aldrig et
# nummer -- brug altid det næste ledige. Scriptet finder selv den nyeste
# master-fil i mappen frem for at have et hardkodet filnavn, så
# DEFAULT_FILENAME aldrig går forældet ved en version-bump.
MASTER_PATTERN = re.compile(r"^locations\[DreamWeave_(\d+)\]\.xml$")
MASTER_VERSION_WIDTH = 3  # -> DreamWeave_001, _002, ...

# Spejl-/deploy-filen har ALTID dette faste navn, uden version-tag -- det er
# den eneste af de to filer der skal ligge i GitHub-repoet, og den GoArrow's
# settings.xml (edtLocationsUrl) skal pege på. Fast navn betyder download-
# links og edtLocationsUrl aldrig behøver ændres mellem versioner.
MIRROR_FILENAME = "locations.xml"


def find_latest_master(directory: Path = Path(".")):
    """Find den højest-nummererede locations[DreamWeave_NNN].xml i directory,
    eller None hvis der ikke findes nogen endnu."""
    candidates = []
    for p in directory.iterdir():
        if not p.is_file():
            continue
        m = MASTER_PATTERN.match(p.name)
        if m:
            candidates.append((int(m.group(1)), p))
    if not candidates:
        return None
    return max(candidates, key=lambda t: t[0])[1]


def default_master_filename() -> str:
    """--file-standardværdi: den nyeste master-fil der allerede ligger i
    mappen, eller version 001 hvis der slet ikke findes nogen endnu (første
    kørsel)."""
    found = find_latest_master()
    if found is not None:
        return found.name
    return f"locations[DreamWeave_{1:0{MASTER_VERSION_WIDTH}d}].xml"


DEFAULT_FILENAME = default_master_filename()

ENCODING = "utf-8-sig"   # bevarer/skriver BOM
NEWLINE = "\r\n"         # filen bruger konsekvent CRLF


# ----------------------------------------------------------------------------
# Fælles hjælpefunktioner
# ----------------------------------------------------------------------------

def load_text(path: Path) -> str:
    with open(path, "r", encoding=ENCODING, newline="") as f:
        return f.read()


def load_tree(path: Path):
    return ET.parse(path)


def xml_escape_attr(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace('"', "&quot;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def xml_escape_text(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def next_id(locs) -> int:
    return max(int(l.get("id")) for l in locs) + 1


def next_id_for_type(locs, type_: str) -> int:
    """Finder næste ledige id inden for type_'s reserverede bånd (se ID_BANDS).
    Rører aldrig eksisterende id'er -- finder blot det højeste NYE id at
    bygge videre på. Falder tilbage til global max+1 hvis typen ikke har
    et bånd, eller hvis båndet er fyldt op."""
    ids_int = [int(l.get("id")) for l in locs]
    global_next = max(ids_int) + 1

    band_start = ID_BANDS.get(type_)
    if band_start is None:
        return global_next, None  # ingen bånd defineret for denne type

    band_end = band_start + ID_BAND_WIDTH - 1
    in_band = [i for i in ids_int if band_start <= i <= band_end]
    taken = set(in_band) | RESERVED_EXAMPLE_IDS
    candidate = band_start
    while candidate in taken and candidate <= band_end:
        candidate += 1

    if candidate > band_end:
        return max(global_next, band_end + 1), (
            f"Båndet {band_start}-{band_end} for '{type_}' er fyldt op. "
            f"Bruger {max(global_next, band_end + 1)} i stedet -- overvej at "
            f"øge ID_BAND_WIDTH eller flytte '{type_}' til et eget bånd i scriptet."
        )
    return candidate, None


def parse_loc_string(raw_text: str):
    """Parser AC's rå /loc-output, fx:
    'Your location is: 0x0D4A0103 [158.116852 133.179001 18.205000] 0.936529 0.000000 0.000000 -0.350590'
    Virker uanset om "Your location is: "-prefixet er med eller ej.
    Returnerer (landblock_raw:int, position_x:float, position_y:float).
    Kaster ValueError med en forklarende besked, hvis teksten ikke genkendes."""
    m = re.search(
        r"0x([0-9A-Fa-f]{1,8})\s*\[\s*(-?[\d.]+)\s+(-?[\d.]+)\s+(-?[\d.]+)\s*\]",
        raw_text,
    )
    if not m:
        raise ValueError(
            "Genkendte ikke formatet. Forventer noget i stil med: "
            "'Your location is: 0x0D4A0103 [158.116852 133.179001 18.205000] "
            "0.936529 0.000000 0.000000 -0.350590' (kun landblock-id'et og de "
            "to første tal i den firkantede parentes bruges)."
        )
    landblock_raw = int(m.group(1), 16)
    position_x = float(m.group(2))
    position_y = float(m.group(3))
    return landblock_raw, position_x, position_y


def loc_to_ns_ew(landblock_raw: int, position_x: float, position_y: float):
    """Konverterer AC's rå /loc-format (landblock-id + kontinuerlig lokal
    position inden for blokken) til NS/EW decimalgrader, som filen bruger.

    Formlen er udledt og selvtestet (round-trip) mod ACEmulator's officielle,
    åbne kildekode -- IKKE gættet:
      - LandblockId.cs bekræfter: LandblockX = (Raw >> 24) & 0xFF,
        LandblockY = (Raw >> 16) & 0xFF (top-16-bit af Raw).
      - Position.cs's GetCellFromBase() og konstruktøren
        Position(float northSouth, float eastWest) bekræfter at et landblock
        er 192 spilenheder bredt (8 "celler" a 24 enheder), og at
        baseX/baseY = landblok-index*8 + lokal_position/24, forskudt 0x400
        (1024, kortets centrum) og skaleret med faktor 10 ift. NS/EW.
      - Denne funktion er den kontinuerlige inversion af den formel (spillets
        egen forward-konstruktør "snapper" til 8 faste under-positioner pr.
        blok til visse formål; her bruges den fulde, kontinuerlige
        PositionX/PositionY fra /loc i stedet, så intet går tabt)."""
    landblock_x = (landblock_raw >> 24) & 0xFF
    landblock_y = (landblock_raw >> 16) & 0xFF

    base_x = landblock_x * 8 + position_x / 24.0
    base_y = landblock_y * 8 + position_y / 24.0

    ew = (base_x - 0x400) / 10.0 + 0.5
    ns = (base_y - 0x400) / 10.0 + 0.5
    return ns, ew


def wiki_api_get(base_url: str, params: dict) -> dict:
    """Sender ét GET-kald til en MediaWiki-installations api.php og returnerer
    det parsede JSON-svar. Kaster RuntimeError med en letforståelig besked
    hvis kaldet fejler -- fx bot-beskyttelse (Cloudflare og lignende), som i
    praksis er den mest sandsynlige fejl her, ikke en fejl i selve koden.
    Kaldes altid inde fra en try/except i enrich, så ét blokeret opslag ikke
    stopper resten af en gennemgang."""
    url = base_url.rstrip("/") + "/api.php?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": WIKI_USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = resp.read()
    except urllib.error.HTTPError as e:
        raise RuntimeError(
            f"HTTP {e.code} fra {base_url} -- sandsynligvis bot-beskyttelse "
            f"(Cloudflare e.lign.), ikke en fejl i selve opslaget."
        )
    except urllib.error.URLError as e:
        raise RuntimeError(f"Kunne ikke nå {base_url}: {e.reason}")
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        raise RuntimeError(
            f"Fik ikke gyldigt JSON tilbage fra {base_url} -- siden viser "
            f"formentlig en bot-udfordringsside i stedet for et API-svar."
        )


def wiki_search_and_extract(base_url: str, query: str):
    """Slår `query` op via MediaWiki's søge-API og henter et kort,
    ren-tekst-uddrag (artikel-introen) af det bedste træf. Returnerer
    (titel, uddrag, side_url), eller None hvis søgningen ikke gav noget
    træf. Lader RuntimeError fra wiki_api_get boble op ved forbindelses-
    eller blokerings-fejl, så den kaldende kode kan skelne "intet fundet"
    fra "kunne slet ikke spørge wiki'en"."""
    search = wiki_api_get(base_url, {
        "action": "query", "list": "search", "srsearch": query,
        "srlimit": 1, "format": "json",
    })
    hits = search.get("query", {}).get("search", [])
    if not hits:
        return None
    title = hits[0]["title"]

    extract_data = wiki_api_get(base_url, {
        "action": "query", "prop": "extracts", "exintro": 1, "explaintext": 1,
        "titles": title, "format": "json",
    })
    pages = extract_data.get("query", {}).get("pages", {})
    for page in pages.values():
        extract = (page.get("extract") or "").strip()
        if extract:
            page_url = base_url.rstrip("/") + "/wiki/" + title.replace(" ", "_")
            return title, extract, page_url
    return None


def fmt_coord(value: float, precise: bool) -> str:
    if precise:
        # bevar op til 5 decimaler, uden overflødige nuller
        s = f"{value:.5f}".rstrip("0")
        if s.endswith("."):
            s += "0"
        return s
    return f"{value:.1f}"


# ----------------------------------------------------------------------------
# check: konsistens-rapport
# ----------------------------------------------------------------------------

def cmd_check(args):
    path = Path(args.file)
    tree = load_tree(path)
    root = tree.getroot()
    locs = root.findall("loc")

    lines = []
    lines.append(f"Konsistens-rapport for: {path.name}")
    lines.append(f"Kørt: {datetime.now().isoformat(timespec='seconds')}")
    lines.append(f"Antal poster: {len(locs)}")
    lines.append("")

    # id-tjek
    ids = [l.get("id") for l in locs]
    dup_ids = [i for i, c in Counter(ids).items() if c > 1]
    int_ids = [int(i) for i in ids]
    monotonic = all(int_ids[i] <= int_ids[i + 1] for i in range(len(int_ids) - 1))
    lines.append("== ID'er ==")
    lines.append(f"  Unikke: {'JA' if not dup_ids else 'NEJ -> ' + str(dup_ids)}")
    lines.append(f"  Monotont stigende i filen: {'JA' if monotonic else 'NEJ'}")
    lines.append(f"  Højeste id lige nu: {max(int_ids)} (næste ledige globalt: {max(int_ids)+1})")
    lines.append("")

    # id-bånd for ny content (kun relevant når poster begynder at ligge >= 10000)
    lines.append("== ID-bånd til ny content (10000+, se ID_BANDS i scriptet) ==")
    any_band_used = False
    for t, band_start in ID_BANDS.items():
        band_end = band_start + ID_BAND_WIDTH - 1
        in_band = [i for i in int_ids if band_start <= i <= band_end]
        if in_band:
            any_band_used = True
            fill = len(in_band) / ID_BAND_WIDTH * 100
            lines.append(f"  {t}: {len(in_band)}/{ID_BAND_WIDTH} brugt i {band_start}-{band_end} ({fill:.0f}%)")
    if not any_band_used:
        lines.append("  Endnu ikke i brug -- alle eksisterende id'er ligger under 10000.")
    lines.append("")

    # type-taksonomi
    types = Counter(l.get("type") for l in locs)
    unknown_types = sorted(set(types) - set(KNOWN_TYPES))
    lines.append("== Typer ==")
    for t, c in types.most_common():
        flag = "  <-- IKKE i KNOWN_TYPES" if t in unknown_types else ""
        lines.append(f"  {t}: {c}{flag}")
    lines.append("")

    # dungeonId-dækning
    dungeons = [l for l in locs if l.get("type") == "Dungeon"]
    missing_did = [l for l in dungeons if l.get("dungeonId") is None]
    lines.append("== dungeonId-dækning (type=Dungeon) ==")
    lines.append(f"  Med dungeonId: {len(dungeons) - len(missing_did)} / {len(dungeons)}")
    if missing_did:
        lines.append(f"  Mangler dungeonId ({len(missing_did)} stk), fx:")
        for l in missing_did[:15]:
            lines.append(f"    id={l.get('id')}  {l.get('name')}")
        if len(missing_did) > 15:
            lines.append(f"    ... og {len(missing_did) - 15} mere")
    lines.append("")

    # exit-koordinat scope
    exit_types = Counter(l.get("type") for l in locs if l.get("exitEW") is not None)
    outside = {t: c for t, c in exit_types.items() if t not in PORTAL_LIKE_TYPES}
    lines.append("== exitNS/exitEW brugt uden for portal-typer ==")
    if outside:
        for t, c in sorted(outside.items(), key=lambda x: -x[1]):
            lines.append(f"  {t}: {c} poster -- tjek om det er tilsigtet")
    else:
        lines.append("  Ingen -- kun portal-lignende typer bruger feltet.")
    lines.append("")

    # koordinatpræcision
    def decimals(v):
        return len(v.split(".")[1]) if v and "." in v else 0

    ns_dec = Counter(decimals(l.get("NS")) for l in locs)
    lines.append("== Koordinat-præcision (decimaler i NS) ==")
    for d, c in sorted(ns_dec.items()):
        lines.append(f"  {d} decimal(er): {c} poster")
    lines.append("")

    # duplikater
    key_counter = Counter((l.get("name"), l.get("type"), l.get("NS"), l.get("EW")) for l in locs)
    dups = {k: v for k, v in key_counter.items() if v > 1}
    lines.append("== Duplikater (samme navn+type+koordinater) ==")
    lines.append(f"  {len(dups)} grupper, {sum(dups.values())} berørte rækker")
    for k, v in list(dups.items())[:15]:
        lines.append(f"    {k} x{v}")
    lines.append("")

    # custom DreamWeave-indhold: tagget via CUSTOM_TAG i teksten OG/ELLER
    # via attributten customized="True" -- tjek begge, så vi opdager hvis
    # de to markører nogensinde kommer ud af sync med hinanden.
    tagged = {l.get("id") for l in locs if (l.text or "").strip().startswith(CUSTOM_TAG)}
    attributed = {l.get("id") for l in locs if l.get("customized") == "True"}
    custom_ids = tagged | attributed
    mismatched = tagged.symmetric_difference(attributed)
    custom_locs = [l for l in locs if l.get("id") in custom_ids]
    lines.append(f'== Custom DreamWeave-indhold ({CUSTOM_TAG} / customized="True") ==')
    lines.append(f"  {len(custom_locs)} poster i alt tagget som custom")
    by_type_custom = Counter(l.get("type") for l in custom_locs)
    for t, c in by_type_custom.most_common():
        lines.append(f"    {t}: {c}")
    if mismatched:
        lines.append(f"  ADVARSEL: {len(mismatched)} poster har kun ÉN af de to markører -- tjek id'erne: {sorted(mismatched)[:10]}")
    lines.append("")

    # retired-poster: forældede poster der bevidst er beholdt (ikke slettet)
    # med retired="True" -- se retire-kommandoen. Vises for overblik, og for
    # at minde om at de stadig tæller med i totalen ovenfor.
    retired_locs = [l for l in locs if l.get("retired") == "True"]
    lines.append('== Retired poster (retired="True") ==')
    lines.append(f"  {len(retired_locs)} poster markeret som forældede (rent bogholderi -- GoArrow læser IKKE")
    lines.append(f"  denne attribut nogen steder, verificeret 2026-09-03 ved at dekompilere Location.FromXml,")
    lines.append(f"  så de vises STADIG normalt på kortet. Skal en post faktisk væk fra kortet, er sletning")
    lines.append(f"  eneste verificerede metode -- se MAINTENANCE.md.)")
    by_type_retired = Counter(l.get("type") for l in retired_locs)
    for t, c in by_type_retired.most_common():
        lines.append(f"    {t}: {c}")
    lines.append("")

    # poster pr. patch/update (kun sat på poster tilføjet via add efter denne
    # konvention blev indført -- fravær betyder "tilføjet før dette blev
    # sporet", ikke en fejl. Sorteret så nyeste patch står øverst.
    patched = [l for l in locs if l.get("patch")]
    lines.append('== Poster pr. patch/update (patch="YYYY-MM") ==')
    lines.append(f"  {len(patched)} poster har en patch-værdi sat")
    by_patch = Counter(l.get("patch") for l in patched)
    for p, c in sorted(by_patch.items(), reverse=True):
        lines.append(f"    {p}: {c}")
    lines.append("")

    # tomme beskrivelser pr. type
    by_type_total = Counter(l.get("type") for l in locs)
    by_type_empty = Counter(l.get("type") for l in locs if not (l.text or "").strip())
    lines.append("== Tom beskrivelse pr. type ==")
    for t in by_type_total:
        e = by_type_empty.get(t, 0)
        tot = by_type_total[t]
        lines.append(f"  {t}: {e}/{tot} ({e/tot*100:.0f}%)")

    report = "\n".join(lines)
    print(report)

    if args.out:
        out_path = Path(args.out)
        out_path.write_text(report, encoding="utf-8")
        print(f"\n[Rapport gemt: {out_path}]")


# ----------------------------------------------------------------------------
# add: guidet, valideret tilføjelse
# ----------------------------------------------------------------------------

def prompt(msg, default=None, required=True):
    suffix = f" [{default}]" if default is not None else ""
    while True:
        val = input(f"{msg}{suffix}: ").strip()
        if not val and default is not None:
            return default
        if not val and not required:
            return ""
        if val:
            return val
        print("  -> Skal udfyldes.")


def prompt_float(msg, default=None):
    while True:
        raw = prompt(msg, default=str(default) if default is not None else None)
        try:
            return float(raw)
        except ValueError:
            print("  -> Skal være et tal, fx -27.8")


def prompt_multiline(msg):
    print(f"{msg} (afslut med en tom linje):")
    lines = []
    while True:
        line = input()
        if line == "":
            break
        lines.append(line)
    return "\n".join(lines)


def build_loc_line(id_, name, type_, ns, ew, description,
                    dungeon_id=None, exit_ns=None, exit_ew=None, customized=False,
                    patch=None):
    attrs = [
        f'id="{id_}"',
        f'name="{xml_escape_attr(name)}"',
        f'type="{xml_escape_attr(type_)}"',
        f'NS="{ns}"',
        f'EW="{ew}"',
    ]
    if exit_ns is not None and exit_ew is not None:
        attrs.append(f'exitNS="{exit_ns}"')
        attrs.append(f'exitEW="{exit_ew}"')
    if dungeon_id is not None:
        attrs.append(f'dungeonId="{dungeon_id}"')
    if customized:
        attrs.append('customized="True"')
    if patch:
        attrs.append(f'patch="{xml_escape_attr(patch)}"')
    attr_str = " ".join(attrs)
    body = xml_escape_text(description)
    return f'    <loc {attr_str}>{body}</loc>'


def cmd_add(args):
    path = Path(args.file)
    tree = load_tree(path)
    root = tree.getroot()
    locs = root.findall("loc")

    print(f"=== Tilføj ny post til {path.name} ===\n")

    name = prompt("Navn")

    print(f"\nKendte typer: {', '.join(KNOWN_TYPES)}")
    type_ = prompt("Type")
    if type_ not in KNOWN_TYPES:
        confirm = prompt(
            f"  '{type_}' findes ikke i det kendte type-sæt. Fortsæt alligevel? (j/n)",
            default="n",
        )
        if confirm.lower() != "j":
            print("Afbrudt.")
            return

    use_loc = prompt(
        "Har du i stedet en rå /loc-tekst fra spillet (fx 'Your location is: 0x... [...] ...')? (j/n)",
        default="n",
    ).lower() == "j"
    if use_loc:
        while True:
            raw_loc_text = prompt("Indsæt /loc-teksten")
            try:
                landblock_raw, pos_x, pos_y = parse_loc_string(raw_loc_text)
            except ValueError as e:
                print(f"  -> {e}")
                continue
            ns, ew = loc_to_ns_ew(landblock_raw, pos_x, pos_y)
            print(f"  -> Udregnet: NS={ns:.5f}  EW={ew:.5f}  (landblock 0x{landblock_raw:08X})")
            break
    else:
        ns = prompt_float("NS (fx -27.8)")
        ew = prompt_float("EW (fx 65.1)")
    precise = prompt("Brug høj præcision (5 decimaler) i stedet for standard 1 decimal? (j/n)", default="n").lower() == "j"
    ns_s = fmt_coord(ns, precise)
    ew_s = fmt_coord(ew, precise)

    # duplikat-tjek (navn+type inden for ~0.2 koordinat-enheder)
    for l in locs:
        if l.get("name") == name and l.get("type") == type_:
            try:
                d = abs(float(l.get("NS")) - ns) + abs(float(l.get("EW")) - ew)
            except (TypeError, ValueError):
                d = 999
            if d < 0.3:
                print(f"\n  ADVARSEL: ligner en eksisterende post (id={l.get('id')}, "
                      f"NS={l.get('NS')} EW={l.get('EW')}).")
                if prompt("  Fortsæt alligevel? (j/n)", default="n").lower() != "j":
                    print("Afbrudt.")
                    return

    dungeon_id = None
    if type_ == "Dungeon":
        did = prompt("dungeonId (Enter for at springe over -- men opslå den om muligt!)", required=False)
        dungeon_id = did or None
        if not dungeon_id:
            print("  Bemærk: allerede 232/727 Dungeon-poster mangler dungeonId. "
                  "Undgå at gøre hullet større hvis du kan finde id'et.")

    exit_ns = exit_ew = None
    wants_exit = prompt("Har posten exit-koordinater (portal-destination)? (j/n)", default="n").lower() == "j"
    if wants_exit:
        if type_ not in PORTAL_LIKE_TYPES:
            print(f"  Bemærk: '{type_}' er ikke en af de typer der normalt har exit-koordinater "
                  f"({', '.join(sorted(PORTAL_LIKE_TYPES))}).")
            if prompt("  Fortsæt alligevel? (j/n)", default="n").lower() != "j":
                wants_exit = False
        if wants_exit:
            exit_ns = fmt_coord(prompt_float("exitNS"), precise)
            exit_ew = fmt_coord(prompt_float("exitEW"), precise)

    description = prompt_multiline("Beskrivelse")

    is_custom = prompt("Er dette custom DreamWeave-indhold (ikke stock AC)? (j/n)", default="n").lower() == "j"
    if is_custom and not description.startswith(CUSTOM_TAG):
        description = f"{CUSTOM_TAG} {description}".rstrip()

    if args.patch:
        patch = args.patch
    else:
        default_patch = datetime.now().strftime(PATCH_DATE_FORMAT)
        patch = prompt("Hvilken patch/update kommer denne lokation med i? (Enter for at springe over)",
                        default=default_patch, required=False)
    if patch and not re.match(r"^\d{4}-\d{2}$", patch):
        print(f'  Bemærk: "{patch}" følger ikke det anbefalede format YYYY-MM (fx "2026-09") -- '
              f"gemmes alligevel som skrevet, men bliver sværere at sortere/filtrere på.")

    new_id, band_warning = next_id_for_type(locs, type_)
    if band_warning:
        print(f"\n  ADVARSEL: {band_warning}")
    new_line = build_loc_line(new_id, name, type_, ns_s, ew_s, description,
                               dungeon_id, exit_ns, exit_ew, customized=is_custom,
                               patch=patch or None)

    print("\n--- Ny linje ---")
    print(new_line)
    print("----------------")
    if prompt("Indsæt i filen? (j/n)", default="j").lower() != "j":
        print("Afbrudt -- intet skrevet.")
        return

    insert_loc_line(path, new_line)
    print(f"\nTilføjet som id={new_id}.")

    if args.sync:
        do_sync(path)


def insert_loc_line(path: Path, new_line: str):
    """Indsætter en ny <loc>-linje lige før </locations>, bevarer BOM/CRLF 1:1."""
    text = load_text(path)

    # sikkerhedskopi
    backup = path.with_suffix(path.suffix + f".bak-{datetime.now():%Y%m%d%H%M%S}")
    shutil.copy2(path, backup)

    closing = "</locations>"
    idx = text.rfind(closing)
    if idx == -1:
        raise RuntimeError("Kunne ikke finde </locations> i filen -- afbrudt uden ændringer.")

    # find start af linjen med </locations>, og om der er en linjeskift lige før
    before = text[:idx]
    after = text[idx:]
    if not before.endswith(NEWLINE):
        before += NEWLINE
    new_text = before + new_line + NEWLINE + after

    with open(path, "w", encoding=ENCODING, newline="") as f:
        f.write(new_text)

    print(f"[Sikkerhedskopi: {backup.name}]")


# ----------------------------------------------------------------------------
# loc: ren omregner fra rå /loc-tekst til NS/EW (skriver ikke i filen)
# ----------------------------------------------------------------------------

def cmd_loc(args):
    raw_text = args.text
    if not raw_text:
        raw_text = prompt("Indsæt /loc-teksten")
    try:
        landblock_raw, pos_x, pos_y = parse_loc_string(raw_text)
    except ValueError as e:
        print(f"FEJL: {e}")
        return

    ns, ew = loc_to_ns_ew(landblock_raw, pos_x, pos_y)
    landblock_x = (landblock_raw >> 24) & 0xFF
    landblock_y = (landblock_raw >> 16) & 0xFF

    print(f"\nLandblock: 0x{landblock_raw:08X}  (landblockX={landblock_x}, landblockY={landblock_y})")
    print(f"NS = {ns:.5f}   -- 1 decimal: {fmt_coord(ns, False)}   5 decimaler: {fmt_coord(ns, True)}")
    print(f"EW = {ew:.5f}   -- 1 decimal: {fmt_coord(ew, False)}   5 decimaler: {fmt_coord(ew, True)}")
    print("\nBrug disse værdier som NS/EW i 'add' -- gem aldrig selve /loc-teksten i filen.")


# ----------------------------------------------------------------------------
# enrich: fyld TOMME beskrivelser med tekst fra en MediaWiki-wiki (fx ACPedia)
# ----------------------------------------------------------------------------

def _find_loc_element_span(text: str, id_: str):
    """Ligesom _find_loc_tag_span, men finder HELE elementet (åbningstag +
    tekstindhold + lukketag) -- også når beskrivelsen strækker sig over flere
    fysiske linjer. Bruges af enrich, som (modsat retire) skal erstatte selve
    tekstindholdet, ikke kun tilføje en attribut i åbningstagget. Den lukkende
    '</loc>' kan trygt findes ikke-grådigt: '<' og '>' er altid XML-escapet i
    teksten (se xml_escape_text), så en rå '</loc>'-streng kan aldrig optræde
    midt i en beskrivelse."""
    pattern = re.compile(r'<loc id="' + re.escape(str(id_)) + r'"[^>]*>.*?</loc>', re.S)
    matches = list(pattern.finditer(text))
    if len(matches) == 0:
        return None
    if len(matches) > 1:
        raise RuntimeError(
            f"Fandt {len(matches)} poster med id=\"{id_}\" -- det bør være "
            f"unikt. Stopper uden at ændre noget, undersøg filen manuelt."
        )
    return matches[0].start(), matches[0].end()


def replace_loc_description_in_text(text: str, id_: str, new_description: str) -> str:
    """Ren tekst-erstatning: bytter kun selve beskrivelsen (elementets
    tekstindhold) ud for posten med det angivne id, uden at røre en eneste
    attribut. Ingen fil-I/O her -- kaldes flere gange i træk på samme
    in-memory tekst under en enrich-kørsel, og skrives til disk af den
    kaldende kode."""
    span = _find_loc_element_span(text, id_)
    if span is None:
        raise RuntimeError(f'Fandt ingen post med id="{id_}" -- intet ændret.')
    start, end = span
    element = text[start:end]

    m = re.match(r'(<loc id="' + re.escape(str(id_)) + r'"[^>]*>).*(</loc>)$', element, re.S)
    open_tag, close_tag = m.group(1), m.group(2)
    new_element = open_tag + xml_escape_text(new_description) + close_tag
    return text[:start] + new_element + text[end:]


def cmd_enrich(args):
    path = Path(args.file)
    tree = load_tree(path)
    root = tree.getroot()
    locs = root.findall("loc")

    base_url = WIKI_BASES.get(args.wiki, args.wiki)  # tillad også en rå URL
    targets = [l for l in locs if not (l.text or "").strip()]
    if args.type:
        targets = [l for l in targets if l.get("type") == args.type]

    print(f"=== Berig tomme beskrivelser i {path.name} via {base_url} ===")
    print(f"{len(targets)} post(er) med tom beskrivelse at gennemgå "
          f"{'(type=' + args.type + ')' if args.type else '(alle typer)'}.\n")
    if not targets:
        print("Intet at lave.")
        return

    text = load_text(path)
    backed_up = False

    def ensure_backup():
        nonlocal backed_up
        if not backed_up:
            backup = path.with_suffix(path.suffix + f".bak-{datetime.now():%Y%m%d%H%M%S}")
            shutil.copy2(path, backup)
            print(f"[Sikkerhedskopi: {backup.name}]")
            backed_up = True

    changed = 0
    skipped = 0
    blocked = False  # sat hvis wiki'en viser sig at være utilgængelig -- så
                      # spørger vi ikke igen og igen resten af kørslen

    for l in targets:
        id_, name, type_ = l.get("id"), l.get("name"), l.get("type")
        print(f"--- id={id_}  {name}  ({type_}) ---")

        result = None
        if not blocked:
            try:
                result = wiki_search_and_extract(base_url, name)
                time.sleep(WIKI_REQUEST_DELAY)
            except RuntimeError as e:
                print(f"  FEJL: {e}")
                if prompt(
                    "  Wiki'en ser ud til at være utilgængelig herfra lige nu. "
                    "Skift til manuel indsætning for resten af listen? (j/n)",
                    default="j",
                ).lower() == "j":
                    blocked = True

        if not blocked:
            if result is None:
                print("  Intet træf.")
                skipped += 1
                continue
            title, extract, page_url = result
            print(f"  Fundet: \"{title}\" -- {page_url}")
            preview = extract if len(extract) <= 500 else extract[:500] + "..."
            print(f"  Uddrag: {preview}")
            choice = prompt(
                "  Brug denne tekst? (j=ja, r=redigér selv, n=spring over)", default="n"
            ).lower()
            if choice == "n":
                skipped += 1
                continue
            text_to_use = extract if choice != "r" else prompt_multiline("  Skriv/ret beskrivelsen")
            source_note = f"(Kilde: {title}, {page_url})"
        else:
            search_url = base_url.rstrip("/") + "/index.php?" + urllib.parse.urlencode(
                {"search": name}
            )
            print(f"  Slå evt. selv op: {search_url}")
            text_to_use = prompt_multiline(
                "  Indsæt beskrivelse herfra (tom for at springe over)"
            )
            if not text_to_use.strip():
                skipped += 1
                continue
            source_note = "(Kilde: indsat manuelt fra wiki)"

        ensure_backup()
        full_text = f"{text_to_use.strip()}{NEWLINE}{source_note}"
        text = replace_loc_description_in_text(text, id_, full_text)
        with open(path, "w", encoding=ENCODING, newline="") as f:
            f.write(text)
        print("  -> Gemt.")
        changed += 1

    print(f"\nFærdig: {changed} opdateret, {skipped} sprunget over (ud af {len(targets)}).")
    if args.sync and changed:
        do_sync(path)


# ----------------------------------------------------------------------------
# import-ace: forslag udtrukket af serverens egen ACE world-database
# (landblock_instance / points_of_interest / weenie_properties_*) -- se
# Maintenance/ACE_DATABASE_ANALYSE.md for hvordan kandidat-filen laves.
# Samme grundprincip som enrich: ALDRIG stille ændringer -- hver kandidat
# vises og skal godkendes én ad gangen, før noget skrives.
# ----------------------------------------------------------------------------

def add_exit_coords_in_text(text: str, id_: str, exit_ns: str, exit_ew: str) -> str:
    """Tilføjer exitNS/exitEW-attributter til en EKSISTERENDE posts åbningstag
    (rører ikke tekstindholdet). Indsættes lige efter EW="...", som er den
    faste attribut-rækkefølge build_loc_line også bruger. Fejler tydeligt hvis
    posten allerede har exitNS -- vi skal aldrig overskrive en eksisterende
    værdi stille."""
    span = _find_loc_tag_span(text, id_)
    if span is None:
        raise RuntimeError(f'Fandt ingen post med id="{id_}" -- intet ændret.')
    start, end = span
    tag = text[start:end]
    if 'exitNS=' in tag:
        raise RuntimeError(f'id="{id_}" har allerede exitNS -- springer over for ikke at overskrive.')

    m = re.search(r'EW="[^"]*"', tag)
    if not m:
        raise RuntimeError(f'Kunne ikke finde EW-attributten i taggen for id="{id_}" -- uventet format.')
    insert_at = m.end()
    new_tag = tag[:insert_at] + f' exitNS="{exit_ns}" exitEW="{exit_ew}"' + tag[insert_at:]
    return text[:start] + new_tag + text[end:]


def _load_ace_candidates(path):
    with open(path, encoding="utf-8") as f:
        candidates = json.load(f)
    return candidates


def cmd_import_ace(args):
    path = Path(args.file)
    tree = load_tree(path)
    root = tree.getroot()
    locs = root.findall("loc")
    by_id = {l.get("id"): l for l in locs}

    candidates = _load_ace_candidates(args.candidates)

    actions_wanted = set(args.action.split(",")) if args.action != "all" else {
        "new", "enrich_description", "enrich_exit"
    }
    filtered = [c for c in candidates if c["action"] in actions_wanted]
    if "new" in actions_wanted and not args.include_low_confidence:
        filtered = [c for c in filtered if c["action"] != "new" or c.get("confidence") == "high"]
    if args.limit:
        filtered = filtered[: args.limit]

    print(f"=== Gennemgå ACE-kandidater fra {args.candidates} mod {path.name} ===")
    print(f"{len(filtered)} kandidat(er) at gennemgå "
          f"(actions={','.join(sorted(actions_wanted))}"
          f"{', inkl. lav tillid' if args.include_low_confidence else ', kun høj tillid for nye poster'}).\n")
    if not filtered:
        print("Intet at lave.")
        return

    text = load_text(path)
    backed_up = False

    def ensure_backup():
        nonlocal backed_up
        if not backed_up:
            backup = path.with_suffix(path.suffix + f".bak-{datetime.now():%Y%m%d%H%M%S}")
            shutil.copy2(path, backup)
            print(f"[Sikkerhedskopi: {backup.name}]")
            backed_up = True

    added = updated = skipped = 0

    for c in filtered:
        src = c.get("source", "")

        if c["action"] == "new":
            print(f"--- NY POST  {c['name']!r}  (tillid: {c.get('confidence')}, "
                  f"{'custom' if c.get('is_custom') else 'stock'}) ---")
            print(f"  NS={c['ns']}  EW={c['ew']}"
                  + (f"  exitNS={c['exit_ns']} exitEW={c['exit_ew']}" if c.get("exit_ns") is not None else ""))
            if c.get("description"):
                preview = c["description"] if len(c["description"]) <= 300 else c["description"][:300] + "..."
                print(f"  Beskrivelse: {preview}")
            if c.get("nearby_note"):
                print(f"  OBS: {c['nearby_note']}")
            print(f"  Kilde: {src}")

            choice = prompt("  Tilføj denne post? (j=ja, r=redigér type/navn først, n=spring over)", default="n").lower()
            if choice == "n":
                skipped += 1
                continue

            name, type_ = c["name"], c.get("suggested_type", "_Unknown")
            if choice == "r":
                name = prompt("  Navn", default=name)
                print(f"  Kendte typer: {', '.join(KNOWN_TYPES)}")
                type_ = prompt("  Type", default=type_)
            if type_ not in KNOWN_TYPES:
                if prompt(f"  '{type_}' findes ikke i det kendte type-sæt. Fortsæt alligevel? (j/n)", default="n").lower() != "j":
                    skipped += 1
                    continue

            if c.get("exit_ns") is not None and type_ not in PORTAL_LIKE_TYPES:
                print(f"  Bemærk: '{type_}' er ikke en af de typer der normalt har exit-koordinater "
                      f"({', '.join(sorted(PORTAL_LIKE_TYPES))}) -- ACE-data siger den har en destination alligevel.")

            description = c.get("description") or ""
            if c.get("is_custom") and not description.startswith(CUSTOM_TAG):
                description = f"{CUSTOM_TAG} {description}".rstrip()
            description = f"{description}{NEWLINE}(Kilde: {src})".strip() if description else f"(Kilde: {src})"

            patch = args.patch or datetime.now().strftime(PATCH_DATE_FORMAT)
            new_id, band_warning = next_id_for_type(locs, type_)
            if band_warning:
                print(f"  ADVARSEL: {band_warning}")
            ns_s = fmt_coord(c["ns"], True) if c["ns"] is not None else "0.0"
            ew_s = fmt_coord(c["ew"], True) if c["ew"] is not None else "0.0"
            exit_ns_s = fmt_coord(c["exit_ns"], True) if c.get("exit_ns") is not None else None
            exit_ew_s = fmt_coord(c["exit_ew"], True) if c.get("exit_ew") is not None else None

            new_line = build_loc_line(new_id, name, type_, ns_s, ew_s, description,
                                       exit_ns=exit_ns_s, exit_ew=exit_ew_s,
                                       customized=bool(c.get("is_custom")), patch=patch)
            print(f"  --- Ny linje ---\n  {new_line}\n  ----------------")
            if prompt("  Bekræft indsættelse? (j/n)", default="j").lower() != "j":
                skipped += 1
                continue

            ensure_backup()
            closing = "</locations>"
            idx = text.rfind(closing)
            before, after = text[:idx], text[idx:]
            if not before.endswith(NEWLINE):
                before += NEWLINE
            text = before + new_line + NEWLINE + after
            # ny post skal selv tælle med, hvis der slås et nyt id op igen senere i samme kørsel
            locs.append({"id": str(new_id), "type": type_})
            with open(path, "w", encoding=ENCODING, newline="") as f:
                f.write(text)
            print(f"  -> Tilføjet som id={new_id}.")
            added += 1

        elif c["action"] == "enrich_description":
            entry = by_id.get(str(c["existing_id"]))
            print(f"--- BERIG BESKRIVELSE  id={c['existing_id']}  {c.get('existing_name')!r} ---")
            if entry is not None and (entry.text or "").strip():
                print(f"  Posten har allerede en beskrivelse -- springer automatisk over.")
                skipped += 1
                continue
            preview = c["description"] if len(c["description"]) <= 300 else c["description"][:300] + "..."
            print(f"  Foreslået: {preview}")
            print(f"  Kilde: {src}")
            if prompt("  Brug denne beskrivelse? (j/n)", default="n").lower() != "j":
                skipped += 1
                continue
            full_text = f"{c['description'].strip()}{NEWLINE}(Kilde: {src})"
            try:
                ensure_backup()
                text = replace_loc_description_in_text(text, str(c["existing_id"]), full_text)
            except RuntimeError as e:
                print(f"  FEJL: {e}")
                skipped += 1
                continue
            with open(path, "w", encoding=ENCODING, newline="") as f:
                f.write(text)
            print("  -> Opdateret.")
            updated += 1

        elif c["action"] == "enrich_exit":
            print(f"--- TILFØJ EXIT-KOORDINATER  id={c['existing_id']}  {c.get('existing_name')!r} "
                  f"({c.get('existing_type')}) ---")
            print(f"  exitNS={c['exit_ns']}  exitEW={c['exit_ew']}")
            print(f"  Kilde: {src}")
            if c.get("existing_type") not in PORTAL_LIKE_TYPES:
                print(f"  Bemærk: '{c.get('existing_type')}' er ikke en af de typer der normalt har "
                      f"exit-koordinater -- men ACE-data siger denne post har en destination.")
            if prompt("  Tilføj disse exit-koordinater? (j/n)", default="n").lower() != "j":
                skipped += 1
                continue
            exit_ns_s = fmt_coord(c["exit_ns"], True)
            exit_ew_s = fmt_coord(c["exit_ew"], True)
            try:
                ensure_backup()
                text = add_exit_coords_in_text(text, str(c["existing_id"]), exit_ns_s, exit_ew_s)
            except RuntimeError as e:
                print(f"  FEJL: {e}")
                skipped += 1
                continue
            with open(path, "w", encoding=ENCODING, newline="") as f:
                f.write(text)
            print("  -> Opdateret.")
            updated += 1

    print(f"\nFærdig: {added} nye poster, {updated} eksisterende poster beriget, "
          f"{skipped} sprunget over (ud af {len(filtered)}).")
    if args.sync and (added or updated):
        do_sync(path)


# ----------------------------------------------------------------------------
# retire / unretire: sætter/fjerner en attribut retired="True" på en
# EKSISTERENDE post, oprindeligt tænkt som Darktorizo's <retired>Y/N</retired>
# i data_cod.xml (som en attribut i stedet, siden vores skema er
# attribut-baseret), for at markere en post forældet uden at slette den.
#
# VERIFICERET 2026-09-03 ved at dekompilere GoArrow.dll's Location.FromXml:
# GoArrow læser IKKE en "retired"-attribut nogen steder. Sætter I den, sker
# der intet i spillet -- posten vises præcis som før, med det samme ikon,
# på samme kort. Dette er altså IKKE en fungerende "skjul post"-mekanisme,
# kun et rent bogholderi-flag for jeres egen `check`-rapport (se ovenfor).
#
# Skal en post rent faktisk væk fra kortet, er sletning i praksis den eneste
# verificerede metode. Er I bekymrede for at bryde en spillers gemte
# favorit/rute/seneste-lokation-reference (settings.xml kan indeholde id'er
# fra denne fil, se ID-bånd-sektionen ovenfor): også det er nu verificeret
# ved at dekompilere LoadSettings -- opslaget der matcher en gemt reference
# mod databasen (GetLocation) er null-sikret to steder, så en reference til
# et id der ikke længere findes i filen bliver stille sprunget over, ikke en
# fejl/crash. Sletning er derfor sikkert i den forstand; spilleren mister
# blot den specifikke gemte reference uden varsel.
# ----------------------------------------------------------------------------

def _find_loc_tag_span(text: str, id_: str):
    """Finder span'et for netop <loc id="id_" ...>'s ÅBNINGS-tag (ikke hele
    elementet, kun op til første '>'). Returnerer (start, end) eller None."""
    pattern = re.compile(r'<loc id="' + re.escape(str(id_)) + r'"[^>]*>')
    matches = list(pattern.finditer(text))
    if len(matches) == 0:
        return None
    if len(matches) > 1:
        raise RuntimeError(
            f"Fandt {len(matches)} poster med id=\"{id_}\" -- det bør være "
            f"unikt. Stopper uden at ændre noget, undersøg filen manuelt."
        )
    m = matches[0]
    return m.start(), m.end()


def cmd_retire(args):
    path = Path(args.file)
    text = load_text(path)

    span = _find_loc_tag_span(text, args.id)
    if span is None:
        print(f"Fandt ingen post med id=\"{args.id}\" i {path.name}. Intet ændret.")
        return
    start, end = span
    tag = text[start:end]

    if args.undo:
        if 'retired="True"' not in tag:
            print(f"id=\"{args.id}\" er ikke markeret som retired. Intet ændret.")
            return
        new_tag = re.sub(r'\s*retired="True"', "", tag)
        action = "un-retired (bogholderi-markeringen fjernet)"
    else:
        if 'retired="True"' in tag:
            print(f"id=\"{args.id}\" er allerede markeret som retired. Intet ændret.")
            return
        # sæt attributten lige inden det afsluttende '>'
        new_tag = tag[:-1].rstrip() + ' retired="True">'
        action = "retired (kun bogholderi-markering -- posten vises STADIG uændret på kortet)"

    backup = path.with_suffix(path.suffix + f".bak-{datetime.now():%Y%m%d%H%M%S}")
    shutil.copy2(path, backup)
    new_text = text[:start] + new_tag + text[end:]
    with open(path, "w", encoding=ENCODING, newline="") as f:
        f.write(new_text)

    print(f"[Sikkerhedskopi: {backup.name}]")
    print(f"id=\"{args.id}\" er nu {action} i {path.name}.")
    if not args.undo:
        print("OBS: 'retired' er IKKE en attribut GoArrow selv læser (verificeret ved at")
        print("dekompilere Location.FromXml) -- dette skjuler ikke posten i spillet. Skal")
        print("den faktisk væk fra kortet, brug sletning i stedet. Se MAINTENANCE.md.")

    if args.sync:
        do_sync(path)


# ----------------------------------------------------------------------------
# docblock: selvdokumenterende kommentar i selve filen
# ----------------------------------------------------------------------------

# De to markør-strenge herunder er den STABILE nøgle scriptet bruger til at
# genkende "det er vores blok" ved en senere opdatering -- de må aldrig
# ændres, heller ikke selvom sproget/ordlyden i selve blokken laves om
# (som lige er sket: dansk -> engelsk). Ændres disse to strenge, mister
# scriptet evnen til at genkende og opdatere en tidligere indsat blok, og
# vil i stedet indsætte en ny ved siden af den gamle.
DOC_MARKER_BEGIN = "BEGIN DREAMWEAVE CUSTOM ID DOCS"
DOC_MARKER_END = "END DREAMWEAVE CUSTOM ID DOCS"

DOC_BEGIN = f"    <!-- {DOC_MARKER_BEGIN} (auto-generated, edit ID_BANDS in goarrow_maintain.py, not this text by hand) -->"
DOC_END = f"    <!-- {DOC_MARKER_END} -->"

EXAMPLE_ENTRIES = [
    # (type, navn, har_exit)
    ("Dungeon", "Example Custom Dungeon", False),
    ("Landmark", "Example Custom Landmark", False),
    ("NPC", "Example Custom NPC", False),
    ("Vendor", "Example Custom Vendor", False),
    ("WildernessPortal", "Example Custom Wilderness Portal", True),
    ("TownPortal", "Example Custom Town Portal", True),
]


def build_doc_block(version: str = None) -> str:
    lines = [DOC_BEGIN]
    lines.append("    <!-- CUSTOM ID RANGES: see Maintenance/MAINTENANCE.md for full background.")
    lines.append("")
    if version:
        lines.append(f"         Version: DreamWeave_{version} (this master file's own version tag,")
        lines.append("         embedded here so the file is self-describing even if a copy gets")
        lines.append("         renamed or an old settings.xml points at a stale one). Bump to a new")
        lines.append("         version using the bump command in goarrow_maintain.py, pointed at")
        lines.append("         this file; never by hand-renaming, so the filename, this line and")
        lines.append("         the locations.xml mirror can never drift out of sync.")
        lines.append("")
    lines.append("         Existing ids (1-9539) should NOT be changed or reused: GoArrow's")
    lines.append("         settings.xml stores the user's recent locations, routes and favorites")
    lines.append("         using these exact id values as the key. Deleting an entry is verified")
    lines.append("         safe (GoArrow.dll's LoadSettings null-checks the id lookup and simply")
    lines.append("         drops a stale reference, no crash) but silently loses that one saved")
    lines.append("         reference with no warning to the player; prefer keeping ids stable")
    lines.append("         when there's no strong reason to remove the entry entirely.")
    lines.append("")
    lines.append("         Reserved ranges for NEW content (5000 ids per type):")
    for t, start in ID_BANDS.items():
        end = start + ID_BAND_WIDTH - 1
        lines.append(f"           {start}-{end} = Custom {t}")
    lines.append("")
    lines.append("         Use only the existing GoArrow type values above. Custom content is")
    lines.append(f'         marked with BOTH: the attribute customized="True" AND "{CUSTOM_TAG}"')
    lines.append("         as the first word of the description. Always add new entries via")
    lines.append("         Maintenance/goarrow_maintain.py add, never by hand, so the id, range")
    lines.append("         and markers are always set correctly and consistently.")
    lines.append("")
    lines.append("         retired=\"True\" (set via the retire command in")
    lines.append("         Maintenance/goarrow_maintain.py) is bookkeeping only; GoArrow does NOT")
    lines.append("         read this attribute (verified by decompiling Location.FromXml), so it")
    lines.append("         does NOT hide the entry from the map. If an entry genuinely needs to")
    lines.append("         stop showing (e.g. an NPC that no longer exists in the game), deletion")
    lines.append("         is the only verified way to do that; see the note above about what")
    lines.append("         deletion costs (a silently dropped saved reference, no crash) before")
    lines.append("         deciding.")
    lines.append("")
    lines.append("         Every entry added via the add command also gets a patch=\"YYYY-MM\"")
    lines.append("         attribute recording which monthly update introduced it (any type,")
    lines.append("         not only custom content). The original entries never have this")
    lines.append("         attribute; its absence means \"added before this was tracked\", not")
    lines.append("         an error.")
    lines.append("")
    lines.append("         EXAMPLES (reference only, commented out below, never loaded by")
    lines.append("         GoArrow so they can never appear as real locations):")
    lines.append("")
    for type_, name, has_exit in EXAMPLE_ENTRIES:
        band_start = ID_BANDS[type_]
        desc = (f"{CUSTOM_TAG} Replace name, coordinates and description with a real "
                f"location. Source: DreamWeave Custom Content.")
        if has_exit:
            line = build_loc_line(band_start, name, type_, "0.0", "0.0", desc,
                                   exit_ns="0.0", exit_ew="0.0", customized=True,
                                   patch="YYYY-MM")
        else:
            line = build_loc_line(band_start, name, type_, "0.0", "0.0", desc,
                                   customized=True, patch="YYYY-MM")
        lines.append("         " + line.strip())
    lines.append("    -->")
    lines.append(DOC_END)
    block = NEWLINE.join(lines)

    # XML-kommentarer må ALDRIG indeholde "--" nogen steder i selve INDHOLDET
    # (mellem hvert par <!-- og -->) -- ellers bliver filen ugyldig XML, og
    # hverken GoArrow eller andre parsere kan læse den. Blokken består af
    # tre separate kommentarer (BEGIN, den store midterste, END), så vi
    # tjekker hver af dem for sig, ikke blokken som én sammenhængende streng.
    for match in re.finditer(r"<!--(.*?)-->", block, re.S):
        if "--" in match.group(1):
            raise RuntimeError(
                "Intern fejl: en af kommentarerne i dokumentationsblokken "
                "indeholder '--' i selve indholdet, hvilket gør XML'en ugyldig. "
                "Ret teksten i build_doc_block()."
            )
    return block


def cmd_docblock(args):
    path = Path(args.file)
    text = load_text(path)
    m_version = MASTER_PATTERN.match(path.name)
    if m_version:
        version = m_version.group(1)
    else:
        version = None
        print(f"[Advarsel: '{path.name}' matcher ikke locations[DreamWeave_NNN].xml -- "
              f"docblokken skrives uden en Version:-linje.]")
    block = build_doc_block(version)

    # KRITISK (opdaget 2026-09-02 -- se PROGRESS.md "Tooling fixes"): GoArrow's
    # egen LoadLocationsXml caster ALLE børn af <locations> direkte til
    # XmlElement uden at tjekke node-typen først. Ethvert XML-kommentar-barn
    # (System.Xml.XmlComment) giver derfor et hårdt InvalidCastException og
    # forhindrer HELE filen i at loade -- dette gjaldt allerede FØR denne
    # session (blokken lå der fra den tidligste tilgængelige backup), men blev
    # først opdaget nu, da Nico rent faktisk prøvede at loade filen i GoArrow.
    # Blokken må derfor ALDRIG stå som barn af <locations>...</locations> --
    # den eneste sikre placering er FØR <locations>'s åbningstag (en
    # kommentar der er søskende til rod-elementet, ikke barn af det, er
    # fuldt lovlig XML og bliver aldrig set af GoArrow's børn-iteration).

    # Find en evt. TIDLIGERE indsat blok via de stabile markører (uanset
    # sprog/ordlyd på selve teksten, og uanset om den fejlagtigt står inde i
    # <locations> fra før denne rettelse) og fjern den helt -- vi geninsætter
    # den altid på den ene sikre plads herunder, så en forkert placering
    # bliver selv-helende i stedet for at blive stående.
    b_idx = text.find(DOC_MARKER_BEGIN)
    e_idx = text.find(DOC_MARKER_END)

    if b_idx != -1 and e_idx != -1 and e_idx > b_idx:
        line_start = text.rfind(NEWLINE, 0, b_idx)
        line_start = 0 if line_start == -1 else line_start + len(NEWLINE)
        line_end = text.find(NEWLINE, e_idx)
        line_end = len(text) if line_end == -1 else line_end + len(NEWLINE)
        text = text[:line_start] + text[line_end:]
        action = "opdateret"
    else:
        action = "indsat"

    m = re.search(r"<locations[^>]*>\r\n", text)
    if not m:
        raise RuntimeError("Kunne ikke finde <locations ...> aabningstag -- afbrudt uden aendringer.")
    insert_at = m.start()
    new_text = text[:insert_at] + block + NEWLINE + text[insert_at:]

    backup = path.with_suffix(path.suffix + f".bak-{datetime.now():%Y%m%d%H%M%S}")
    shutil.copy2(path, backup)
    with open(path, "w", encoding=ENCODING, newline="") as f:
        f.write(new_text)

    print(f"[Sikkerhedskopi: {backup.name}]")
    print(f"Dokumentationsblok {action} i {path.name}.")

    if args.sync:
        do_sync(path)


# ----------------------------------------------------------------------------
# sync: kopier redigeret fil over spejl-filen
# ----------------------------------------------------------------------------

def do_sync(edited_path: Path):
    if edited_path.name == MIRROR_FILENAME:
        raise RuntimeError(
            f"'{edited_path.name}' ER spejl-filen -- sync går kun én vej, fra "
            f"master (locations[DreamWeave_NNN].xml) til '{MIRROR_FILENAME}', "
            f"aldrig omvendt. Kør sync med --file pegende på master-filen."
        )
    mirror = edited_path.parent / MIRROR_FILENAME
    if mirror.exists():
        backup = mirror.with_suffix(mirror.suffix + f".bak-{datetime.now():%Y%m%d%H%M%S}")
        shutil.copy2(mirror, backup)
        print(f"[Sikkerhedskopi af spejl-fil: {backup.name}]")
    shutil.copy2(edited_path, mirror)
    print(f"[Synkroniseret: {edited_path.name} -> {mirror.name}]")


def cmd_sync(args):
    do_sync(Path(args.file))


# ----------------------------------------------------------------------------
# bump: ny version -- omdøb master, opdatér indbygget Version:-linje, sync
# ----------------------------------------------------------------------------

def cmd_bump(args):
    path = Path(args.file)
    m = MASTER_PATTERN.match(path.name)
    if not m:
        raise RuntimeError(
            f"'{path.name}' matcher ikke locations[DreamWeave_NNN].xml -- "
            "bump virker kun på master-filen."
        )
    current_version = int(m.group(1))
    new_version = args.version if args.version is not None else current_version + 1
    if new_version <= current_version:
        raise RuntimeError(
            f"Nyt versionsnummer ({new_version}) skal være højere end det "
            f"nuværende ({current_version}) -- afbrudt uden ændringer."
        )
    new_name = f"locations[DreamWeave_{new_version:0{MASTER_VERSION_WIDTH}d}].xml"
    new_path = path.parent / new_name
    if new_path.exists():
        raise RuntimeError(f"'{new_name}' findes allerede -- afbrudt uden ændringer.")

    path.rename(new_path)
    print(f"[Omdøbt: {path.name} -> {new_name}]")

    # Genindsæt docblokken (med det nye versionsnummer indbygget) og
    # synkronisér spejl-filen -- genbruger cmd_docblock's egne sikkerheds-
    # tjek (XML-kommentar "--"-guarden osv.) frem for at duplikere dem her.
    args.file = str(new_path)
    args.sync = True
    cmd_docblock(args)


# ----------------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="GoArrow location-database vedligeholdelse.")
    sub = parser.add_subparsers(dest="command")

    p_check = sub.add_parser("check", help="Kør konsistens-rapport")
    p_check.add_argument("--file", default=DEFAULT_FILENAME)
    p_check.add_argument("--out", default=None, help="Gem rapporten som tekstfil")
    p_check.set_defaults(func=cmd_check)

    p_add = sub.add_parser("add", help="Tilføj en ny lokation interaktivt")
    p_add.add_argument("--file", default=DEFAULT_FILENAME)
    p_add.add_argument("--sync", action="store_true", help="Synkronisér spejl-filen bagefter")
    p_add.add_argument("--patch", default=None,
                        help='Sæt patch-attributten direkte (fx "2026-09") uden at blive spurgt -- '
                             "praktisk når I tilføjer flere lokationer til samme patch i træk")
    p_add.set_defaults(func=cmd_add)

    p_loc = sub.add_parser(
        "loc",
        help="Omregn en rå /loc-tekst fra spillet til NS/EW (tilføjer intet til filen)",
    )
    p_loc.add_argument(
        "text", nargs="?", default=None,
        help='Hele /loc-teksten i citationstegn, fx "0x0D4A0103 [158.116852 133.179001 18.205000] '
             '0.936529 0.000000 0.000000 -0.350590". Udelades den, bliver du spurgt interaktivt.',
    )
    p_loc.set_defaults(func=cmd_loc)

    p_enrich = sub.add_parser(
        "enrich",
        help="Forsøg at fylde tomme beskrivelser med tekst fra en wiki (fx ACPedia), post for post med din godkendelse",
    )
    p_enrich.add_argument("--file", default=DEFAULT_FILENAME)
    p_enrich.add_argument(
        "--wiki", default=DEFAULT_WIKI,
        help=f'Hvilken wiki der slås op i: en af {list(WIKI_BASES)}, eller en rå URL til en anden MediaWiki-installation (standard: "{DEFAULT_WIKI}")',
    )
    p_enrich.add_argument("--type", default=None, help="Begræns til én type, fx Landmark (udelad for alle typer)")
    p_enrich.add_argument("--sync", action="store_true", help="Synkronisér spejl-filen bagefter")
    p_enrich.set_defaults(func=cmd_enrich)

    p_import_ace = sub.add_parser(
        "import-ace",
        help="Gennemgå kandidater fra serverens ACE world-database (portaler/POI) og tilføj/berig, post for post",
    )
    p_import_ace.add_argument("--file", default=DEFAULT_FILENAME)
    p_import_ace.add_argument(
        "--candidates", default="ace_import_candidates.json",
        help="Sti til kandidat-JSON-filen fra build_candidates.py (standard: \"ace_import_candidates.json\")",
    )
    p_import_ace.add_argument(
        "--action", default="all",
        help="Kommasepareret liste: new,enrich_description,enrich_exit (standard: alle tre)",
    )
    p_import_ace.add_argument(
        "--include-low-confidence", action="store_true",
        help="Vis også 'new'-kandidater med lav tillid (generiske navne uden egen beskrivelse) -- udeladt som standard",
    )
    p_import_ace.add_argument("--limit", type=int, default=None, help="Stop efter N kandidater (til at tage det i bidder)")
    p_import_ace.add_argument("--patch", default=None, help='Patch-værdi for nye poster (standard: indeværende måned)')
    p_import_ace.add_argument("--sync", action="store_true", help="Synkronisér spejl-filen bagefter")
    p_import_ace.set_defaults(func=cmd_import_ace)

    p_sync = sub.add_parser("sync", help="Kopiér denne fil over spejl-filen")
    p_sync.add_argument("--file", default=DEFAULT_FILENAME)
    p_sync.set_defaults(func=cmd_sync)

    p_doc = sub.add_parser("docblock", help="Indsæt/opdatér selvdokumenterende kommentarblok i filen")
    p_doc.add_argument("--file", default=DEFAULT_FILENAME)
    p_doc.add_argument("--sync", action="store_true", help="Synkronisér spejl-filen bagefter")
    p_doc.set_defaults(func=cmd_docblock)

    p_bump = sub.add_parser(
        "bump",
        help="Ny version: omdøb master-filen til næste versionsnummer, opdatér "
             "docblokkens Version:-linje og synkronisér spejl-filen",
    )
    p_bump.add_argument("--file", default=DEFAULT_FILENAME)
    p_bump.add_argument(
        "--version", type=int, default=None,
        help="Eksplicit versionsnummer (standard: nuværende + 1)",
    )
    p_bump.set_defaults(func=cmd_bump)

    p_retire = sub.add_parser("retire", help="Markér en eksisterende post som forældet (eller fortryd det)")
    p_retire.add_argument("--id", required=True, help="id på posten der skal retires/un-retires")
    p_retire.add_argument("--file", default=DEFAULT_FILENAME)
    p_retire.add_argument("--undo", action="store_true", help="Fjern retired-markeringen igen (un-retire)")
    p_retire.add_argument("--sync", action="store_true", help="Synkronisér spejl-filen bagefter")
    p_retire.set_defaults(func=cmd_retire)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        return
    args.func(args)


if __name__ == "__main__":
    main()
