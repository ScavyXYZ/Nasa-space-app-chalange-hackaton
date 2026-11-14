# GIS / Terrain Engine — готовий програмний модуль

**Актуальне розширення:** додано dataset `regional` для всієї регіональної
оптичної карти (~30 × 30 км) і марсіанську метричну шкалу.
Див. [regional_routing.md](regional_routing.md). `ctx` і `hirise` нижче лишаються
сумісними локальними режимами; вони не переписувалися.

## Що реалізовано

- `algorithms/terrain.py`: read-only NumPy/mmap-доступ до CTX і HiRISE; перевірка марсіанського CRS, масок, розмірів і метричних осей.
- Точкові висота та ухил за координатами; прив’язка до клітинки без інтерполяції.
- Помилка для координат поза покриттям; NoData повертається як `valid: false` і JSON `null`.
- Маска непрохідності `blocked_mask(max_slope_deg)` для Algorithm Engineer.
- `algorithms/metrics.py`: профіль **заданої** лінії, довжина по сфері Марса, набір/спуск, мінімум/максимум висот і максимальний ухил усіх перетнутих клітинок.
- Консервативна перевірка перетнутих клітинок: не можна перетнути NoData чи зрізати невідомий кут по діагоналі.
- FastAPI у `backend/main.py` з read-only шарами та аналізом профілю.
- Робоча **діагностична** Leaflet-карта у `frontend/gis-check/index.html`. Це не заміна майбутнього React-продукту.
- Марсіанські географічні PNG для візуального суміщення оптики, топографії, геології та наукових областей.

## Запуск

У корені репозиторію:

```powershell
python -m pip install -r requirements.txt
# Якщо даних ще немає — спершу виконати acquisition/processing з nasa_data_report.md.
python scripts/build_gis_overlays.py
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

- GIS QA-карта: http://127.0.0.1:8000/gis-check
- Головна `/` віддає React production build, якщо `frontend/dist` зібрано.
- OpenAPI: http://127.0.0.1:8000/docs
- Health: http://127.0.0.1:8000/api/health

API доступний лише локально за цією командою. CORS дозволяє localhost:5173 для майбутнього Vite frontend. Для зовнішнього деплою потрібна окрема конфігурація. Сирі файли/довільні шляхи не експонуються; PNG видаються за allowlist.

Leaflet 1.9.4 завантажується з CDN, тому **QA-карті потрібен доступ до інтернету**. API та підготовлені геодані не залежать від зовнішніх картографічних сервісів.

## API-контракт

| Метод | Шлях | Результат |
|---|---|---|
| GET | `/api/health` | Готовність CTX/HiRISE; 503, якщо CTX відсутній |
| GET | `/api/layers` | Метадані сіток, конфігурації/легенди й джерела |
| GET | `/api/elevation?lon=…&lat=…&dataset=ctx` | Висота, ухил, valid, row/col і центр клітинки |
| GET | `/api/points` | Підтверджені наукові **області** |
| GET | `/api/geology` | Геологічний GeoJSON |
| GET | `/api/overlays/ctx` або `/api/overlays/hirise` | PNG-шари та їхні bounds/легенди |
| GET | `/api/assets/{name}` | Дозволені PNG |
| POST | `/api/route/profile` | Аналіз **наданої** лінії, не пошук маршруту |
| POST | `/api/route` | A* пошук, характеристики та наукові області поблизу |

Сітка завжди явна: `ctx` (за замовчуванням) або `hirise`. Автоматичного підмішування, fallback чи зшивання немає.

Приклад точкового запиту для ділянки, яка є в обох сітках:

```text
GET /api/elevation?lon=77.4508&lat=18.4447&dataset=hirise
```

Приклад тіла запиту профілю:

```json
{
  "dataset": "ctx",
  "coordinates": [[77.4508, 18.4447], [77.452, 18.4452]],
  "max_slope_deg": 15
}
```

Координати — **марсіанські `[lon, lat]`**, не WGS84. Не передавайте GeoJSON Feature: поле `coordinates` приймає масив вершин LineString. Максимум 1000 вершин; лише двовимірні координати. Ці координати прикладу лежать у підготовленому покритті, але не позначають окремих іменованих наукових цілей.

Опційний `sample_step_m` може зменшити крок. Надто грубий крок автоматично обмежується половиною найменшої фізичної клітинки, щоб не пропустити рельєф. Максимум 20 000 профільних точок; за перевищення повертається 413, а не неповний результат.

Відповідь:

- `route`: початкова лінія з позначкою `user_supplied_not_A_star`.
- `summary`: `distance_m`, `elevation_min_m`, `elevation_max_m`, `elevation_gain_m`, `elevation_loss_m`, `net_elevation_change_m`, `max_terrain_slope_deg`, `cells_crossed`, `cells_above_slope_threshold`, `requires_review`.
- `profile`: відстань від початку, lon/lat, row/col, висота, ухил і прапорець перевищення порогу для кожної вибірки.
- `sampling`, `model_parameters`, `warnings`.

Висоти профілю беруться з клітинок без вигадування субпіксельних значень. Набір/спуск залежить від роздільності й шуму DEM; згладжування не застосовується. `max_terrain_slope_deg` — ухил поверхні з растра, **не поздовжній градієнт між двома точками маршруту**.

### Помилки

- 422 `outside_coverage`: вихід за AOI.
- 422 `route_nodata`: лінія перетинає невідомий рельєф.
- 422 для невірних параметрів/невідомої сітки.
- 413 `profile_too_large`: надто великий профіль.
- 503 `dataset_unavailable`/`invalid_dataset`: відсутні або пошкоджені дані.
- 200 з `valid: false` та `null` для **точкового** NoData-запиту.

Відсутні дані не генеруються й не підміняються CTX/HiRISE. Перезапустіть сервер після повторної генерації масивів: сітки кешуються та звільняють mmap при shutdown. Не перезаписуйте відкриті файли працюючого процесу.

## Використання з Python / A*

```python
from algorithms.terrain import TerrainGrid
from algorithms.metrics import analyze_route

terrain = TerrainGrid.load("ctx")
try:
    point = terrain.sample(lon=77.4508, lat=18.4447)
    blocked = terrain.blocked_mask(max_slope_deg=15)
    result = analyze_route(terrain, [[77.4508,18.4447], [77.452,18.4452]])
finally:
    terrain.close()
```

Масиви `terrain.elevation`, `terrain.slope`, `terrain.valid` мають індекси `[row,col]`.
`terrain.index(lon,lat)` → клітинка; `terrain.lonlat(row,col)` → координати її центру.
`terrain.distance_m(a,b)` приймає дві пари **`(lon,lat)`**.

Для CTX/HiRISE не можна перевикористовувати одні й ті самі row/col чи affine. Пороги та штрафи A* — окремі модельні параметри. Повернена blocked-маска не є офіційною картою NASA trafficability.

## Перевірки

```powershell
python -m unittest discover -s tests -v
python scripts/validate_data.py --online
python scripts/validate_hirise.py --remote-samples
```

**23 unit/integration-тести пройшли** на Python 3.14.7. Цільова версія проєкту — Python 3.14.

Для браузерної перевірки:

```powershell
python -m pip install -r requirements-browser.txt
python -m playwright install chromium
# В іншому терміналі має працювати API.
python tests/smoke_gis_browser.py
```

Фактично виконано у Chromium: обидва dataset-запити, інтерактивні профілі, графік/таблиця, завантаження оптичних/топографічних/геологічних шарів, марсіанська відстань, координатний display-roundtrip, 375px mobile і landscape. JavaScript page errors немає. Скріншоти й `browser_validation_report.json` — у `data/processed/gis/`.

Це перевірка **відображення**, не доказ метрової суміщеності геології. Відоме зміщення SIM 3464 100–200 м залишається.

## Передача бінарних даних команді

```powershell
python scripts/package_terrain.py
```

Створює `artifacts/mars-explorer-terrain.zip` з обробленими даними, масивами, шарами, джерелами й manifest SHA-256. Його можна розпакувати **в корінь клону репозиторію**. Оригінальні сирі набори не включені; повні source-validators потребують їх окремого отримання.

За прямим погодженням власника **архів, великі растри, NumPy-масиви та сирі дані включено через Git LFS**. Після клонування виконайте `git lfs install` та `git lfs pull`, якщо великі файли не завантажилися автоматично. Потрібна доступна GitHub LFS storage/bandwidth квота. Сам скрипт пакування лише створює локальний архів і нічого автоматично не публікує.

## Межі цієї реалізації

GIS-модуль та його API/QA-інтерфейс готові. Для автоматичної побудови маршрутів доступний `POST /api/route`, див. [опис пошуку](routing.md). React MVP із Plotly та наскрізною перевіркою також реалізовано — див. [поточний стан](mvp_status.md). Публічний деплой і автоматичне злиття HiRISE/CTX не заявляються виконаними. Результати описують модель рельєфу та задані обмеження.
