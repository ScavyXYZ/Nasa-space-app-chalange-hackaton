# Деплой MARS EXPLORER

## Фактичний стан

Локальний production build перевірений із реальним API. **Публічний деплой не виконано**:
акаунти Render/Vercel не під’єднані, жоден cloud-сервіс не створювався.
Не вводьте вигаданий demo URL у заявку.

Docker CLI доступний, але локальний Docker daemon не працює; **Docker image не збирався**.
Файли нижче — підготовлена конфігурація, не підтверджений cloud-деплой.
CI workflow також потребує фактичного запуску після публікації змін у GitHub.

## Варіант A — один контейнер для frontend + backend

Рекомендований найпростіший варіант без CORS: FastAPI віддає production Vite build і API.

```powershell
git lfs pull
docker build -t mars-explorer .
docker run --rm -p 8000:8000 mars-explorer
```

Відкрити `http://127.0.0.1:8000`. Python у контейнері — 3.14, Node build stage — 24.
Процес запускається як непривілейований користувач; `PORT` враховується у команді запуску.
Health check: `/api/health`.

`.dockerignore` виключає оригінальні архіви, GeoTIFF та відео, які не потрібні runtime.
API працює з підготовленими NumPy-сітками, JSON/GeoJSON та PNG.

### Важливо про Git LFS

Деякі хостинги клонують тільки LFS pointers. Перед build потрібно виконати
**авторизований `git lfs pull`**, або передати матеріалізовані NumPy-файли у build context.
Для тільки runtime достатньо:

```sh
git lfs pull --include="data/processed/*.npy,data/processed/hirise/*.npy,data/processed/regional/*.npy,data/processed/regional/*.geojson" --exclude=""
```

`scripts/prepare_runtime_data.py` перевіряє дев’ять обов’язкових runtime-масивів (~30 МБ)
за SHA-256 з `data/runtime_manifest.json`. Анонімний GitHub media URL при фактичній
спробі повернув HTTP 404; автоматичного неавторизованого download fallback немає.
В CI використовується стандартна авторизація GitHub checkout + selective LFS pull.
Якщо Render Git-build отримує тільки pointers, використайте збірку образу з локального
матеріалізованого клону й погоджений container registry або налаштуйте підтримуване
хостингом безпечне отримання LFS. Не вбудовуйте GitHub-токени в Dockerfile/ARG.
Build із pointers або неправильними hash зупиняється; вигадані дані не генеруються.

Метадані й runtime-масиви повинні належати одному набору. При зміні підготовлених даних
потрібно свідомо оновити manifest і повторити валідацію; історичний ref локальних
наборів не є URL для автоматичного завантаження регіональних даних.

### Render

1. Опублікувати поточні зміни в GitHub.
2. У власному Render-акаунті створити Blueprint з цього репозиторію та `render.yaml`.
3. Перевірити тариф і можливі витрати **перед підтвердженням**. Тариф конфігурацією не зафіксовано.
4. Запустити deploy вручну: автоматичний deploy вимкнено.
5. Перевірити build logs, `/api/health`, обидва datasets, головну сторінку та реальний A*.
6. Запустити `python tests/smoke_mvp_browser.py --url https://ВАШ-РЕАЛЬНИЙ-ХОСТ`.
7. Тільки після успіху внести реальний URL у README/презентацію.

Слабкий або засинаючий instance може мати cold starts і повільний HiRISE-пошук.
Потрібно перевірити фактичне CPU/RAM навантаження на обраному тарифі.

## Варіант B — Vercel frontend + Python backend

1. Спершу розгорнути Python backend із даними.
2. У Vercel встановити **Root Directory = `frontend`**, framework Vite, Node 24.
3. `frontend/vercel.json` задає build `npm run build`, output `dist`.
4. У build environment задати `VITE_API_BASE_URL=https://РЕАЛЬНИЙ-BACKEND` **без `/api`**.
   Це публічне налаштування, не секрет. Воно вбудовується під час build.
5. У backend environment задати `CORS_ORIGINS=https://РЕАЛЬНИЙ-FRONTEND`.
   Для кількох дозволених origin — список через кому; без wildcard.
6. Перебудувати frontend та перезапустити backend, потім пройти E2E.

На Vercel не потрібно переносити великі NumPy/GeoTIFF-файли у static output.
Усі запити та PNG отримуються від backend через налаштований base URL.

## Що ще не є production-hardening

Є обмеження A*: для локальних сіток 200 000 розгорнутих клітинок та приблизно 8 секунд;
для регіональної сітки — 500 000 клітинок та приблизно 20 секунд пошуку.
`search_limit` відрізняється від `no_route`. Час перевіряється періодично, а підготовка
графа теж займає час; це **не жорстка гарантія часу HTTP-відповіді**.
Немає розподіленої черги, акаунтів, загального rate limiting чи production SLA.
Для відкритого демо з високим навантаженням потрібен окремий захист від зловживань.
