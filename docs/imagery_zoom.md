# Деталізація зображень при наближенні

Глобус тепер використовує регіональний texture atlas: видима область
отримує тайли з відповідного рівня WMTS, а не лише збільшену 4096×2048
Viking-текстуру. Атлас обмежений 96 тайлами, чотирма одночасними запитами
та LRU-кешем 96 декодованих зображень; застарілі запити скасовуються.
GPU-текстури й ImageBitmap звільняються при заміні/закритті.

Джерела в `data/processed/atlas/tiles.json`:

- Viking colorized 232m browse service: глобальний кольоровий контекст.
- CTX global uncontrolled: чорно-біла оптична мозаїка, часткові прогалини
  й похибки реєстрації. Номінальне джерело 5 м не означає, що WMTS надає
  цей крок на максимальному рівні: статус показує крок саме тайлової сітки.
- Контрольована CTX Jezero 6 м та HiRISE Jezero 25 см: локальні оптичні
  мозаїки, географічні межі взяті з WMTS capabilities.
- У топографічному режимі глобуса — MOLA/HRSC hillshade, не optical CTX.

2D-атлас за замовчуванням має «Авто HD»: Viking → CTX → HiRISE відповідно
до масштабу й покриття. При сильному наближенні геологія стає векторною.
Виправлено порядок pane/z-index: статична підкладка більше не перекриває
детальні tile layers. Наближення обмежене доступною деталізацією з
невеликим запасом; навмисне розтягування до довільного zoom не виконується.

**Це зміни зображень, не числових DEM чи точності маршруту.**
Чорно-білі CTX/HiRISE не є true-color. Прозорі прогалини джерела показують
попередню/базову мозаїку, не синтетичні деталі. Мережа потрібна для нових
тайлів. Нескінченна чіткість не гарантується.

Відтворення каталогу: `python scripts/prepare_zoom_sources.py`.
Перевірка: `python tests/smoke_zoom_browser.py --url http://127.0.0.1:8003`.
Скриншоти: `artifacts/zoom/`.
# Interaction and loading update

## Coarse-first loading and bounded prewarming

The complete local Viking overview is preloaded before MissionControl mounts.
At detailed zoom, two reserved request slots fetch the visible overview at
three LOD levels lower, in parallel with four native-tile workers. The overview
is drawn underneath already loaded native pixels, not over them.
After visible work finishes, two idle workers warm at most 12 centre tiles of
the next zoom. View changes cancel obsolete work and keep overlapping requests.

`scripts/prepare_fast_imagery.py` prepares validated global CTX levels 0–3 and
3×3 neighbourhoods at levels 5–11 near four focus regions. The current run
cached 326/420 requested tiles; 94 unavailable/invalid source tiles were not
saved. This is bounded overview/regional caching, not full native Mars.

`tests/smoke_preview_latency.py` blocks all native responses and verifies that
real rendered overview pixels appear first, then verifies that the warmed next
LOD appears without waiting for its new network requests. Its controlled
timing is not a guarantee about public-tunnel or provider bandwidth.

## Current pipeline: original tiles and validated image bytes

### Confirmed repeated upstream pixels near the reported point A

CTX native level 8, rows 92–94, columns 116–118 returned the **same decoded
crater image** in nine different geographic tiles. PNG encodings/checksums
differ, but the decoded RGB SHA-256 is consistently
`95a2493faaca6595906ea74317987a1c02bd81fc3845038578d5308a7bc0b12d`.
This reproduced the user's tiled-crater screenshot directly from the source,
independently of the globe. A source-specific rejection of this confirmed
ambiguous image is applied before disk/memory caching. It is deliberately
not a blanket rule rejecting identical flat terrain pixels everywhere.
Native CTX levels around this area also contain genuinely truncated PNGs.
The globe therefore uses correctly cropped lower-level source tiles.

The real GPU-coordinate test now checks these ancestor pixels as well as native
pixels. Full application screenshots at both actual endpoints are
`artifacts/zoom/user-region-1.png` and `user-region-2.png`. Point B has a real
transparent CTX coverage strip; it is not reconstructed or called fine detail.

The earlier composite-to-composite retention approach below has been replaced.
Every atlas is now rebuilt from original, georeferenced cached tile images.
No progressively resampled composite is used as the source of another atlas.
Cached native images are composed before waiting for downloads.

Real testing found truncated PNGs both in the app cache and at the upstream
CTX service (e.g. `ctx-global/8/95/118`). HTTP 200 and `image/png` did not
guarantee decodable pixels. The backend now verifies structure/CRC **and**
fully decodes the expected image dimensions before serving/caching it.
Invalid temporary cache entries are removed individually. Prepared source
files are not deleted. Browser tile URLs are versioned to bypass old corrupt
HTTP-cache responses.

For unavailable native tiles, the globe crops the geographically correct
parent tile (up to three levels coarser), never duplicates a neighbour.
The UI separately counts lower-LOD fallbacks; source holes are not described
as new native detail. Requests have a timeout and one transient retry.
Globe marker size is compensated for perspective zoom.

Verification:

- `tests/test_imagery_validation.py`: truncated streams, wrong dimensions,
  and corrupt app-cache replacement.
- `tests/smoke_atlas_coordinates.py`: 21 GPU-rendered views, distinct tile
  colours and asymmetric markers, repeat pans, zoom, dateline wrapping,
  transient HTTP failures and permanent native failures with parent cropping.
- `tests/smoke_atlas_coordinates.py --real`: GPU pixels compared with source
  CTX pixels near both user endpoints. Real imagery filtering has a tolerance;
  the report records missing native tiles rather than hiding them.
- `tests/smoke_user_region.py`: full application screenshots at both endpoints.
- Existing zoom, retention, atlas, mission and traversability browser checks.

Reports and screenshots are under `artifacts/zoom/`. Upstream source corruption
is a real remaining service limit; coarser replacement is explicitly labelled.

## Retention fix

Atlas rebuilds now copy the overlapping image into the next geographic canvas,
including longitude wrapping. This preserves loaded pixels across multiple
partial replacements, rather than relying on a single previous texture.
Cached native tiles are composed synchronously before any network wait.
A one-tile surrounding strip is requested where atlas size limits allow,
and the atlas remains stable until the viewport approaches its edge.
Only obsolete offscreen requests are cancelled; overlapping requests are reused.

`python tests/smoke_tile_retention.py` checks rendered native-resolution pixels
using synthetic tiles with delayed responses and a differently coloured
lower-resolution fallback, through repeated pans and return navigation.
It is a retention regression, not a real-world bandwidth benchmark.

- Globe drag speed follows perspective zoom and distance above the sphere,
  rather than a fixed angular step. Tiny movements render even below the
  OrbitControls change-event threshold.
- Visible detail begins loading in the initial view. Camera updates are
  throttled at 60 ms instead of waiting for a pause in movement.
- Up to six tile downloads run concurrently; overlapping views reuse in-flight
  requests. Outdated views stop scheduling work without aborting useful tiles.
- The first completed tile is displayed immediately; subsequent updates are
  batched. The decoded-image LRU holds up to 192 normalized tiles.
- The 2D atlas requests tiles during panning (100 ms interval) and retains
  three offscreen tile rows/columns. This is retention, not whole-planet preload.
- Cold upstream requests still depend on the imagery provider and network.
