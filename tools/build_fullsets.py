#!/usr/bin/env python3
"""Construit les listes complètes de jeux (full sets) de chaque console à partir des pages
« List of … games » de Wikipédia.

Usage :
    python3 tools/build_fullsets.py --cache build/wiki --out build/raw [console ...]

Pour chaque console : <out>/<console>.json, puis <out>/index.json. Les jaquettes sont ajoutées
ensuite par FullSetEnricher (dans l'app, en debug) à partir d'IGDB.
Données Wikipédia sous licence CC BY-SA 4.0 : l'app crédite la source.
"""
import argparse
import json
import os
import re
import sys
import time
import unicodedata
import urllib.parse
import urllib.request

REGIONS = ["JP", "NA", "PAL"]
ALL = REGIONS

# pages : pages Wikipédia ; tables : titres de section (regex) des tableaux à lire, sinon le plus grand de chaque page ;
# default : régions quand le tableau n'a pas de colonne de région ; exclude_tags : marqueurs de jeux dématérialisés ;
# default_if_empty : régions supposées quand toutes les cases de région sont vides ;
# digital : la liste mélange jeux physiques et dématérialisés ; split : répartit une page sur plusieurs consoles.
CONSOLES = {
    "atari2600": {"pages": ["List of Atari 2600 games"], "tables": [r"^Retail game releases"], "igdb": [59]},
    "atari5200": {"pages": ["List of Atari 5200 games"], "tables": [r"^Games$"], "default": ["NA"], "igdb": [66]},
    "atari7800": {"pages": ["List of Atari 7800 games"], "tables": [r"^Commercially released"], "igdb": [60]},
    "colecoVision": {"pages": ["List of ColecoVision games"], "tables": [r"^U\.S\.$"], "default": ["NA"], "igdb": [68]},
    "intellivision": {"pages": ["List of Intellivision games"], "tables": [r"^Master component releases"],
                      "default": ["NA"], "igdb": [67]},
    "vectrex": {"pages": ["List of Vectrex games"], "igdb": [70]},
    "odyssey2": {"pages": ["List of Magnavox Odyssey 2 games"], "igdb": [133]},
    "nes": {"pages": ["List of Nintendo Entertainment System games"], "igdb": [18, 99]},
    "famicomDisk": {"pages": ["List of Famicom Disk System games"], "tables": [r"^Games$"], "default": ["JP"],
                    "igdb": [51]},
    "masterSystem": {"pages": ["List of Master System games"], "tables": [r"^Games$"], "igdb": [64]},
    "sg1000": {"pages": ["List of SG-1000 games"], "tables": [r"^Sega SG-1000/SC-3000 series"], "default": ["JP"],
               "igdb": [84]},
    "snes": {"pages": ["List of Super Nintendo Entertainment System games"], "igdb": [19, 58]},
    "megaDrive": {"pages": ["List of Sega Genesis games"], "tables": [r"^Licensed games"], "igdb": [29]},
    "megaCD": {"pages": ["List of Sega CD games"], "tables": [r"^Games$"], "igdb": [78]},
    "sega32X": {"pages": ["List of 32X games"], "tables": [r"^Games$"], "igdb": [30, 482]},
    "pcEngine": {"pages": ["List of TurboGrafx-16 games"], "tables": [r"^List of games"], "igdb": [86, 128],
                 "split": {"column": "format", "rule": "cd", "cd": "pcEngineCD"}},
    "pcEngineCD": {"pages": [], "igdb": [150]},
    "neoGeoAES": {"pages": ["List of Neo Geo games"], "tables": [r"^Games$"], "default": ALL, "igdb": [80, 79],
                  "formats": {"aes": "neoGeoAES", "cd": "neoGeoCD"}},
    "neoGeoCD": {"pages": [], "igdb": [136]},
    "gameBoy": {"pages": ["List of Game Boy games"], "tables": [r"^List of games"], "igdb": [33]},
    "gameGear": {"pages": ["List of Game Gear games"], "igdb": [35]},
    "lynx": {"pages": ["List of Atari Lynx games"], "tables": [r"^Commercially released"], "igdb": [61]},
    "cdi": {"pages": ["List of CD-i games"], "tables": [r"^Games$"], "default_if_empty": ["NA", "PAL"], "igdb": [117]},
    "ps1": {"pages": ["List of PlayStation (console) games (A–L)", "List of PlayStation (console) games (M–Z)"],
            "igdb": [7]},
    "saturn": {"pages": ["List of Sega Saturn games"], "tables": [r"^Games$"], "igdb": [32]},
    "n64": {"pages": ["List of Nintendo 64 games"], "tables": [r"^Games$"], "igdb": [4, 416]},
    "threeDO": {"pages": ["List of 3DO games"], "tables": [r"^Commercially released"], "igdb": [50]},
    "jaguar": {"pages": ["List of Atari Jaguar games"], "tables": [r"^Cartridge$", r"^CD$"], "igdb": [62, 410]},
    "virtualBoy": {"pages": ["List of Virtual Boy games"], "igdb": [87]},
    "gameBoyColor": {"pages": ["List of Game Boy Color games"], "tables": [r"^List of games"], "igdb": [22]},
    "neoGeoPocketColor": {"pages": ["List of Neo Geo Pocket games"], "tables": [r"^Neo Geo Pocket"],
                          "default": ["JP"], "igdb": [120, 119]},
    "wonderSwan": {"pages": ["List of WonderSwan games"], "default": ["JP"], "igdb": [57]},
    "wonderSwanColor": {"pages": ["List of WonderSwan Color games"], "default": ["JP"], "igdb": [123]},
    "ps2": {"pages": ["List of PlayStation 2 games (A–K)", "List of PlayStation 2 games (L–Z)"],
            "tables": [r"^Games list"], "igdb": [8]},
    "gameCube": {"pages": ["List of GameCube games"], "tables": [r"^Games$"], "igdb": [21]},
    "xbox": {"pages": ["List of Xbox games"], "igdb": [11]},
    "dreamcast": {"pages": ["List of Dreamcast games"], "tables": [r"^Licensed games"], "igdb": [23]},
    "gameBoyAdvance": {"pages": ["List of Game Boy Advance games"], "tables": [r"^List of games"], "igdb": [24]},
    "nGage": {"pages": ["List of N-Gage games"], "tables": [r"^Games$"], "igdb": [42]},
    "ps3": {"pages": [f"List of PlayStation 3 games ({r})" for r in ["A–C", "D–I", "J–P", "Q–Z"]],
            "exclude_tags": ["D", "F2P"], "igdb": [9]},
    "xbox360": {"pages": ["List of Xbox 360 games (A–L)", "List of Xbox 360 games (M–Z)"],
                "exclude_tags": ["XBLA", "XBLIG", "DL"], "igdb": [12]},
    "wii": {"pages": ["List of Wii games"], "tables": [r"^Games$"], "igdb": [5]},
    "ds": {"pages": [f"List of Nintendo DS games ({r})" for r in ["0–C", "D–I", "J–P", "Q–Z"]],
           "tables": [r"^Games$"], "igdb": [20, 159]},
    "psp": {"pages": ["List of PlayStation Portable games"], "tables": [r"^Released"], "digital": True, "igdb": [38]},
    "threeDS": {"pages": ["List of Nintendo 3DS games (0–M)", "List of Nintendo 3DS games (N–Z)"],
                "tables": [r"^Games$"], "digital": True, "igdb": [37, 137]},
    "wiiU": {"pages": ["List of Wii U games"], "tables": [r"^Games$"], "digital": True, "igdb": [41]},
    "psVita": {"pages": [f"List of PlayStation Vita games ({r})" for r in
                         ["A–D", "E–H", "I–L", "M–O", "P–R", "S", "T–V", "W–Z"]], "digital": True, "igdb": [46]},
    "ps4": {"pages": ["List of PlayStation 4 games (A–L)", "List of PlayStation 4 games (M–Z)"], "digital": True,
            "igdb": [48]},
    "xboxOne": {"pages": ["List of Xbox One games (A–L)", "List of Xbox One games (M–Z)"], "tables": [r"^List$"],
                "digital": True, "igdb": [49]},
    "nSwitch": {"pages": [f"List of Nintendo Switch games ({r})" for r in
                          ["0–9", "A–Am", "An–Az", "B", "C–G", "H–P", "Q–Z"]],
                "default": ALL, "exclude_tags": ["D"], "digital": True, "igdb": [130]},
    "ps5": {"pages": ["List of PlayStation 5 games"], "digital": True, "igdb": [167]},
    "xboxSeries": {"pages": ["List of Xbox Series X and Series S games"], "digital": True, "igdb": [169]},
    "nSwitch2": {"pages": ["List of Nintendo Switch 2 games"], "default": ALL, "digital": True, "igdb": [508]},
}

HEADER_REGIONS = {
    "JP": {"jp", "japan", "asia/japan", "jpn", "jp (japan)"},
    "NA": {"na", "north america", "u.s. release", "us", "usa", "na (north america)"},
    "PAL": {"pal", "eu", "europe", "eu/pal", "europe/pal", "europe / pal", "pal region", "eu release", "eur"},
}
REGION_TOKENS = {"NA": "NA", "US": "NA", "USA": "NA", "EU": "PAL", "PAL": "PAL", "UK": "PAL", "EUR": "PAL",
                 "JP": "JP", "JPN": "JP", "WW": "ALL"}


def fetch_wikitext(page, cache):
    path = os.path.join(cache, re.sub(r"[^\w]+", "_", page) + ".txt")
    if os.path.exists(path):
        return open(path).read()
    url = ("https://en.wikipedia.org/w/api.php?action=parse&prop=wikitext&format=json&formatversion=2&page="
           + urllib.parse.quote(page))
    request = urllib.request.Request(url, headers={"User-Agent": "RetroShelfDataset/0.1 (full set builder)"})
    for attempt in range(6):
        try:
            with urllib.request.urlopen(request) as response:
                text = json.load(response)["parse"]["wikitext"]
            break
        except urllib.error.HTTPError as error:
            if error.code != 429:
                raise
            time.sleep(15 * (attempt + 1))
    os.makedirs(cache, exist_ok=True)
    open(path, "w").write(text)
    time.sleep(1.5)
    return text


def split_top_level(text, separator):
    """Découpe sur `separator` en ignorant ce qui est dans {{ }} et [[ ]]."""
    parts, depth, start, i = [], 0, 0, 0
    while i < len(text):
        pair = text[i:i + 2]
        if pair in ("{{", "[["):
            depth += 1
            i += 2
            continue
        if pair in ("}}", "]]"):
            depth = max(0, depth - 1)
            i += 2
            continue
        if depth == 0 and text.startswith(separator, i):
            parts.append(text[start:i])
            i += len(separator)
            start = i
            continue
        i += 1
    parts.append(text[start:])
    return parts


def strip_markup(text):
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    text = re.sub(r"<ref[^>]*/>|<ref[^>]*>.*?</ref>", "", text, flags=re.S)
    text = re.sub(r"<span[^>]*display:\s*none[^>]*>.*?</span>", "", text, flags=re.S)
    text = re.sub(r"\[\[(?:[^|\]]*\|)?([^\]]*)\]\]", r"\1", text)
    text = re.sub(r"\{\{ill\|[^{}]*?\blt=([^|}]*)[^{}]*\}\}", r"\1", text)
    text = re.sub(r"\{\{(?:ill|nihongo|nowrap|vgy|lang|abbr|sort)\|([^|}]*)[^}]*\}\}", r"\1", text)
    text = re.sub(r"\{\{(?:hlist|vgrtbl|ubl|plainlist|unbulleted list)\|(.*?)\}\}", lambda m: ", ".join(dict.fromkeys(
        p.strip() for p in m.group(1).split("|")
        if p.strip() and not re.fullmatch(r"[A-Z]{2,3}(/[A-Z]{2,3})*", p.strip()))), text)
    while re.search(r"\{\{[^{}]*\}\}", text):
        text = re.sub(r"\{\{[^{}]*\}\}", "", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = text.replace("'''", "").replace("''", "").replace("&nbsp;", " ")
    return re.sub(r"\s+", " ", text).strip(" •,|")


class Cell:
    def __init__(self, raw, header):
        self.header = header
        self.rowspan = self.colspan = 1
        if raw.lstrip().startswith("!"):   # cellule d'en-tête de ligne écrite « |! style=… | Titre »
            raw = raw.lstrip()[1:]
            self.header = True
        parts = split_top_level(raw, "|")
        if len(parts) > 1 and re.match(r'^\s*(?:[\w-]+\s*=\s*("[^"]*"|\S+)\s*)+$', parts[0]):
            attrs, raw = parts[0], "|".join(parts[1:])
            self.rowspan = int((re.search(r'rowspan\s*=\s*"?(\d+)', attrs) or [0, 1])[1])
            self.colspan = int((re.search(r'colspan\s*=\s*"?(\d+)', attrs) or [0, 1])[1])
            self.row_header = bool(re.search(r"scope\s*=\s*\"?row\b", attrs))
        else:
            self.row_header = False
        self.raw = raw.strip()


def parse_rows(table):
    """Retourne (lignes d'en-tête, lignes de données), chaque ligne étant une liste de Cell."""
    headers, data = [], []
    chunks = table.split("\n|-")
    chunks[0] = chunks[0].split("\n", 1)[1] if "\n" in chunks[0] else ""   # retire la ligne « {| class=… »
    for chunk in chunks:
        cells, current = [], None
        for line in chunk.split("\n"):
            if line.startswith("|+") or line.startswith("|}"):
                continue
            if line.startswith("!") or line.startswith("|"):
                marker = line[0]
                separator = "!!" if marker == "!" else "||"
                for piece in split_top_level(line[1:], separator):
                    current = Cell(piece, marker == "!")
                    cells.append(current)
            elif current is not None:
                current.raw += "\n" + line
        if not cells:
            continue
        if all(c.header and not c.row_header for c in cells) and not data:
            headers.append(cells)
        else:
            data.append(cells)
    return headers, data


def expand(rows):
    """Applique rowspan / colspan pour obtenir une grille régulière."""
    pending, grid = {}, []
    for cells in rows:
        out, col, queue = [], 0, list(cells)
        while queue or col in pending:
            if col in pending:
                remaining, cell = pending[col]
                out.append(cell)
                if remaining <= 1:
                    del pending[col]
                else:
                    pending[col] = (remaining - 1, cell)
                col += 1
                continue
            cell = queue.pop(0)
            for _ in range(max(1, cell.colspan)):
                out.append(cell)
                if cell.rowspan > 1:
                    pending[col] = (cell.rowspan - 1, cell)
                col += 1
        grid.append(out)
    return grid


def classify_columns(header_rows):
    grid = expand(header_rows)
    width = max((len(r) for r in grid), default=0)
    columns = []
    for i in range(width):
        labels = [strip_markup(r[i].raw).lower() for r in grid if i < len(r)]
        labels = [re.sub(r"\s+", " ", l).strip() for l in labels if l]
        leaf = labels[-1] if labels else ""
        kind = None
        for region, names in HEADER_REGIONS.items():
            if leaf in names:
                kind = region
        if kind is None:
            if "title" in leaf:
                kind = "title"
            elif "developer" in leaf:
                kind = "developer"
            elif "publisher" in leaf or "distributor" in leaf:
                kind = "publisher"
            elif "region" in leaf and "released" in leaf:
                kind = "regionlist"
            elif leaf in ("format",):
                kind = "format"
            elif "first released" in leaf or leaf.startswith("release date") or leaf in ("released", "year"):
                kind = "date"
            elif leaf in ("mvs", "aes", "cd"):
                kind = "fmt:" + leaf
        columns.append(kind)
    if "title" not in columns and columns:
        columns[0] = "title"
    return columns


def release_year(cell_raw):
    lowered = cell_raw.lower()
    if re.search(r"unreleased|\{\{\s*(?:no|na|n|dunno)\s*\}\}|\bn/a\b|\{\{n/a|\{\{dtba|\btba\b|cancel", lowered):
        return None
    if re.search(r"\{\{\s*(?:ya|y|yes|check|tick)\s*\}\}", lowered):
        return 0
    match = (re.search(r"\{\{\s*(?:dts|start date|#invoke:date table sorting\|main)\|(\d{4})", cell_raw, re.I)
             or re.search(r"\b(19[789]\d|20[0-4]\d)\b", cell_raw))
    if match:
        return int(match.group(1))
    if re.search(r"\{\{\s*yes|✓|\byes\b|released", lowered):
        return 0
    return None


def parse_title(raw):
    lines = re.split(r"<br\s*/?>", raw)
    title = strip_markup(lines[0])
    regional = {}
    for line in lines[1:]:
        sup = re.search(r"<sup>(.*?)</sup>|\{\{sup\|(.*?)\}\}", line)
        name = strip_markup(re.sub(r"<sup>.*?</sup>|\{\{sup\|.*?\}\}", "", line))
        if not sup or not name:
            continue
        for token in re.split(r"[,/ ]+", sup.group(1) or sup.group(2)):
            region = REGION_TOKENS.get(token.strip().upper())
            if region in REGIONS:
                regional.setdefault(region, name)
    return title, regional


def slug(text):
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def tables_of(wikitext, patterns):
    found = []
    for match in re.finditer(r"\{\|[^\n]*wikitable", wikitext):
        start = match.start()
        end = wikitext.find("\n|}", start)
        heading = list(re.finditer(r"\n(=+)\s*([^=\n]+?)\s*\1", wikitext[:start]))
        heading = strip_markup(heading[-1].group(2)) if heading else ""
        found.append((heading, wikitext[start:end]))
    if patterns:
        return [table for heading, table in found if any(re.search(p, heading) for p in patterns)]
    return [max(found, key=lambda item: item[1].count("\n|-"))[1]] if found else []


def build(key, config, cache, results):
    for page in config["pages"]:
        wikitext = fetch_wikitext(page, cache)
        for table in tables_of(wikitext, config.get("tables")):
            headers, rows = parse_rows(table)
            columns = classify_columns(headers)
            for row in expand(rows):
                values = {}
                for kind, cell in zip(columns, row):
                    if kind and kind not in values:
                        values[kind] = cell.raw
                if "title" not in values:
                    continue
                if any(f"&nbsp;{tag}&nbsp;" in "".join(c.raw for c in row) for tag in config.get("exclude_tags", [])):
                    continue
                title, regional = parse_title(values["title"])
                if not title:
                    continue

                release = {}
                for region in REGIONS:
                    if region in values:
                        year = release_year(values[region])
                        if year is not None:
                            release[region] = year
                if "regionlist" in values:
                    year = release_year(values["regionlist"]) or 0
                    for token in re.findall(r"[A-Za-z]{2,3}", strip_markup(values["regionlist"])):
                        region = REGION_TOKENS.get(token.upper())
                        for r in (REGIONS if region == "ALL" else [region] if region else []):
                            release.setdefault(r, year)
                if (not release and config.get("default_if_empty")
                        and not any(strip_markup(values.get(r, "")) for r in REGIONS)):
                    release = {r: release_year(values.get("date", "")) or 0 for r in config["default_if_empty"]}
                if not release and config.get("default") and not any(r in columns for r in REGIONS):
                    year = release_year(values["date"]) if "date" in values else 0
                    if year is not None:
                        release = {r: year for r in config["default"]}
                if not release:
                    continue
                if 0 in release.values() and "date" in values:
                    first = re.search(r"\b(19[789]\d|20[0-4]\d)\b", values["date"])
                    if first:
                        release = {r: (y or int(first.group(1))) for r, y in release.items()}

                target = key
                if config.get("split") and "format" in values:
                    if "cd" in strip_markup(values["format"]).lower():
                        target = config["split"]["cd"]
                if config.get("formats"):
                    for fmt, fmt_target in config["formats"].items():
                        cell = values.get("fmt:" + fmt, "")
                        if release_year(cell) is not None or re.search(r"\{\{\s*yes|✓|✔", cell, re.I):
                            add(results, fmt_target, title, regional, values, release)
                    continue
                add(results, target, title, regional, values, release)


def add(results, key, title, regional, values, release):
    games = results.setdefault(key, {})
    game_id = f"{key}-{slug(title) or 'game'}"
    if game_id in games:
        existing = games[game_id]
        for region, year in release.items():
            existing["release"].setdefault(region, year)
        return
    game = {"id": game_id, "title": title}
    if regional:
        game["titles"] = regional
    if values.get("developer"):
        game["developer"] = strip_markup(values["developer"])
    if values.get("publisher"):
        game["publisher"] = strip_markup(values["publisher"])
    game["release"] = release
    games[game_id] = game


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cache", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("consoles", nargs="*")
    args = parser.parse_args()

    results = {}
    for key in args.consoles or CONSOLES:
        build(key, CONSOLES[key], args.cache, results)

    os.makedirs(args.out, exist_ok=True)
    index = []
    for key, config in CONSOLES.items():
        if key not in results:
            continue
        games = sorted(results[key].values(), key=lambda g: g["title"].lower())
        pages = config["pages"] or next(c["pages"] for c in CONSOLES.values()
                                         if key in (c.get("split", {}).get("cd"), *c.get("formats", {}).values()))
        payload = {
            "platform": key,
            "source": "Wikipédia — " + ", ".join(pages) + " (CC BY-SA 4.0)",
            "includesDigital": bool(config.get("digital")),
            "regionsDistinguished": config.get("default") != ALL,
            "igdbPlatforms": config["igdb"],
            "games": games,
        }
        json.dump(payload, open(os.path.join(args.out, f"{key}.json"), "w"), ensure_ascii=False, indent=1)
        counts = {r: sum(1 for g in games if r in g["release"]) for r in REGIONS}
        index.append({"platform": key, "counts": counts, "includesDigital": payload["includesDigital"],
                      "regionsDistinguished": payload["regionsDistinguished"]})
        print(f"{key:18} {len(games):5} jeux  {counts}", file=sys.stderr)
    json.dump(index, open(os.path.join(args.out, "index.json"), "w"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
