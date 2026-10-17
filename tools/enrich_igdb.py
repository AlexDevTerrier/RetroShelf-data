#!/usr/bin/env python3
"""Associe chaque jeu des full sets à sa fiche IGDB (jaquette, jaquettes régionales), puis écrit
les fichiers publiés et leur index.

Usage :
    IGDB_CLIENT_ID=… IGDB_CLIENT_SECRET=… python3 tools/enrich_igdb.py --raw build/raw --out data

- Lit <raw>/<console>.json produits par build_fullsets.py.
- Réutilise les identifiants de jeux de l'ancienne version de <out> quand la fiche IGDB est la même,
  pour que les jeux déjà cochés dans l'app restent reliés si Wikipédia renomme un titre.
- Écrit <out>/<console>.json (compact) et <out>/fullsets-index.json (empreinte de chaque fichier).
"""
import argparse
import datetime
import hashlib
import json
import os
import re
import sys
import time
import unicodedata
import urllib.parse
import urllib.request

IGDB_URL = "https://api.igdb.com/v4/games"
FIELDS = ("name,game_type,cover.image_id,alternative_names.name,game_localizations.name,"
          "game_localizations.region,game_localizations.cover.image_id")
# Régions IGDB des localisations : 3 = Japon, 4 = Europe
LOCALIZATION_REGIONS = {3: "JP", 4: "PAL"}


class IGDB:
    def __init__(self, client_id, client_secret):
        self.client_id = client_id
        query = urllib.parse.urlencode({"client_id": client_id, "client_secret": client_secret,
                                        "grant_type": "client_credentials"})
        request = urllib.request.Request("https://id.twitch.tv/oauth2/token?" + query, method="POST")
        with urllib.request.urlopen(request) as response:
            self.token = json.load(response)["access_token"]

    def query(self, body):
        request = urllib.request.Request(IGDB_URL, data=body.encode(), method="POST", headers={
            "Client-ID": self.client_id, "Authorization": f"Bearer {self.token}", "Accept": "application/json"})
        for attempt in range(6):
            try:
                with urllib.request.urlopen(request, timeout=60) as response:
                    return json.load(response)
            except urllib.error.HTTPError as error:
                if error.code != 429:
                    raise
                time.sleep(2 * (attempt + 1))
        raise RuntimeError("IGDB : trop de requêtes")

    def games_for_platform(self, platform_id):
        games, offset = [], 0
        while True:
            page = self.query(f"fields {FIELDS}; where platforms = ({platform_id}); "
                              f"sort id asc; limit 500; offset {offset};")
            games += page
            if len(page) < 500:
                return games
            offset += 500
            time.sleep(0.3)   # IGDB autorise 4 requêtes par seconde


def normalize(text):
    """Même normalisation que l'app : casse, accents, ponctuation, variantes de romanisation japonaise."""
    text = re.sub(r"\(.*?\)", " ", text)
    text = unicodedata.normalize("NFKC", text)
    text = "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c)).lower()
    text = text.replace("&", " and ")
    for variant, vowel in (("ou", "o"), ("oo", "o"), ("uu", "u"), ("aa", "a"), ("ii", "i")):
        text = text.replace(variant, vowel)
    words = "".join(c if c.isalnum() else " " for c in text).split()
    if words and words[0] == "the":
        words = words[1:]
    return " ".join(words)


def enrich(path, igdb, cache, previous_ids):
    data = json.load(open(path))
    candidates = []
    for platform_id in data.pop("igdbPlatforms", []):
        if platform_id not in cache:
            cache[platform_id] = igdb.games_for_platform(platform_id)
        candidates += cache[platform_id]
    by_id = {c["id"]: c for c in candidates}

    index = {}
    for candidate in candidates:
        names = [candidate["name"]] + [n.get("name") for n in candidate.get("alternative_names", [])] \
            + [n.get("name") for n in candidate.get("game_localizations", [])]
        for key in {normalize(n) for n in names if n}:
            if key:
                index.setdefault(key, []).append(candidate)

    matched = 0
    used_ids = set()
    for game in data["games"]:
        keys = [normalize(game["title"])] + [normalize(t) for t in sorted(game.get("titles", {}).values())]
        found = next((index[k] for k in keys if k in index), None)
        if found is None:
            # Secours : « 007: Agent Under Fire » ↔ « James Bond 007: Agent Under Fire », si un seul candidat
            ids = {c["id"] for k in keys if len(k) >= 10 and " " in k
                   for key, items in index.items() if key.endswith(" " + k) for c in items}
            if len(ids) == 1:
                found = [by_id[ids.pop()]]
        game.pop("publisher", None)
        if found:
            best = next((c for c in found if c.get("game_type") == 0), found[0])
            matched += 1
            game["igdb"] = best["id"]
            if best.get("cover"):
                game["cover"] = best["cover"]["image_id"]
            covers = {}
            for localization in best.get("game_localizations", []):
                region = LOCALIZATION_REGIONS.get(localization.get("region"))
                if region and localization.get("cover"):
                    covers[region] = localization["cover"]["image_id"]
            if covers:
                game["covers"] = covers
            # Identifiant stable : on garde celui de la version précédente pour la même fiche IGDB
            old_id = previous_ids.get(best["id"])
            if old_id and old_id not in used_ids:
                game["id"] = old_id
        used_ids.add(game["id"])
    return data, matched


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    igdb = IGDB(os.environ["IGDB_CLIENT_ID"], os.environ["IGDB_CLIENT_SECRET"])
    os.makedirs(args.out, exist_ok=True)
    cache, index = {}, []
    raw_index = json.load(open(os.path.join(args.raw, "index.json")))
    for summary in raw_index:
        key = summary["platform"]
        out_path = os.path.join(args.out, f"{key}.json")
        previous_ids = {}
        if os.path.exists(out_path):
            for game in json.load(open(out_path))["games"]:
                if game.get("igdb"):
                    previous_ids.setdefault(game["igdb"], game["id"])

        data, matched = enrich(os.path.join(args.raw, f"{key}.json"), igdb, cache, previous_ids)
        payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        open(out_path, "w").write(payload)
        summary["sha256"] = hashlib.sha256(payload.encode()).hexdigest()
        index.append(summary)
        total = len(data["games"])
        print(f"{key:18} {matched:5} / {total:5} jaquettes", file=sys.stderr)

    generated = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    json.dump({"generatedAt": generated, "platforms": index},
              open(os.path.join(args.out, "fullsets-index.json"), "w"), ensure_ascii=False, separators=(",", ":"))


if __name__ == "__main__":
    main()
