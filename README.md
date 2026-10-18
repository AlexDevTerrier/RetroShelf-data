# RetroShelf — full sets

Listes complètes des jeux sortis en boîte de 60 consoles (de l'Odyssey à la Wii U), par région
PAL / US / JAP, utilisées par l'app iOS RetroShelf. Les jeux dématérialisés sont retirés ; les consoles
dont Wikipédia mélange physique et dématérialisé (PSP, 3DS, Vita, PS4, PS5, Xbox One, Xbox Series,
Switch, Switch 2) sont écartées tant qu'aucune source ne permet de les distinguer.

- `data/<console>.json` : jeux de la console, titres régionaux, années de sortie par région,
  identifiant et jaquette IGDB.
- `data/fullsets-index.json` : nombre de jeux par région et empreinte SHA-256 de chaque liste ;
  l'app ne télécharge que les listes dont l'empreinte a changé.
- `tools/build_fullsets.py` : extraction depuis les pages « List of … games » de Wikipédia.
- `tools/enrich_igdb.py` : association aux fiches IGDB pour les jaquettes.

Les listes sont régénérées chaque lundi par GitHub Actions (`.github/workflows/update-fullsets.yml`),
qui utilise les secrets `IGDB_CLIENT_ID` et `IGDB_CLIENT_SECRET`.

## Sources et licences

- Listes de jeux : Wikipédia, sous licence [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/).
  Les fichiers de `data/` sont donc diffusés sous la même licence.
- Identifiants et jaquettes : [IGDB.com](https://www.igdb.com). Les images ne sont pas copiées ici :
  l'app les charge depuis le CDN d'IGDB.
