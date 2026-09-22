# Website

Static product landing for Dossier. Assembled with the Sphinx guide by
`make pages-site` into `_site/` (landing at `/`, guide at `/guide/`).

Shared chrome lives in `chrome/` and is also loaded by Sphinx via
`docs/conf.py`.

Umami snippet uses the **Dossier** website on `analytics.glenwright.earth`
(`a616cbd3-08e8-4c29-b7bd-802f3f7b9b0e`). Do not reuse the glenwright.earth
site id. Guide pages get the same id via `docs/_templates/page.html`.
