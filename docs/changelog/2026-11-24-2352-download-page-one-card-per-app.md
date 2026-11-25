# depot's download page shows one card per app, with debug and older builds in dropdowns

- **Cards.** Each app gets one card with its newest release up top, then collapsible "Debug builds" and "Older versions" sections, each build with its own download. An app with only debug builds shows its newest debug build up top, tagged "debug".
- **Catalog.** `GET /v1/catalog` returns one entry per app, its release id and `.debug` id grouped, with every kept build newest first and its download file name.
- **Checked.** `checks.depot` covers the grouped catalog. The page was screenshotted at phone width, light and dark, collapsed and expanded.
