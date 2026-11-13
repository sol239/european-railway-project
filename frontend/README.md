# Railway Atlas

Nuxt with a Nitro API and a CesiumJS station map. Station locations and scheduled stop counts come from the published Gold Iceberg tables through Trino.

## Run with Docker

From the repository root, with the lakehouse and Trino running:

```bash
docker compose up -d --build frontend
```

Development and Docker both use port 7007, so stop the development server before starting the Docker service.

Open http://localhost:7007/map for the map or http://localhost:7007/statistics for the network overview. Nitro connects to `http://trino:8080` over Docker networking.

## Local development

Use Node.js 22.14 or newer. Start the existing lakehouse and Trino services, then:

```bash
cd frontend
npm ci
npm run dev
```

Open http://localhost:7007/map for the map or http://localhost:7007/statistics for the network overview. The Nuxt app includes the Nitro server at `/api/stations`, so no separate API service is needed. Copy `.env.example` to `.env` to change `NUXT_TRINO_URL` or `NUXT_TRINO_USER`. These values are server-only runtime configuration.

## Railway infrastructure layer

Use **Rails** above the map to select **Operating**, **All statuses**, or **Off**. The layer starts off. Operating segments use blue solid lines, and other infrastructure statuses use gray dashed lines. Stations and their hover cards remain available over the lines. The infrastructure overlay is independent of station visit counts.

Nitro's `/api/railways` endpoint follows the RFN raw-data latest pointer in MinIO, verifies the file's SHA-256 and row count, and decodes its WKB GeoParquet geometry to GeoJSON. It serves the original geometry directly without registering an Iceberg table or adding another API service. Responses are cached for 60 seconds. Reload the page to fetch the latest snapshot after an Airflow ingestion.

Run the `rfn_lines_download` Airflow DAG before using the layer. For local development, configure `NUXT_MINIO_ACCESS_KEY` and `NUXT_MINIO_SECRET_KEY` in the ignored `.env` with the credentials from `infra/lakehouse/.env`. `NUXT_MINIO_ENDPOINT` defaults to `http://127.0.0.1:7004` and `NUXT_MINIO_BUCKET` to `railway`. MinIO credentials remain on the Nitro server. Docker Compose provides credentials from the existing lakehouse env file and uses `http://minio:9000` over the shared network.

The overlay depicts RFN infrastructure, including historical/closed statuses when selected. It does not infer which track a GTFS trip follows. RFN data is attributed to SNCF Réseau under ODbL.

## Map and data

- Choose **Theme → Neon** in the **Map settings** dialog opened from the header for a dark map with cyan stations and magenta selection. **Light** restores the original appearance. The choice is remembered in this browser. The light and neon themes use Esri gray basemaps with separate reference labels; no recoloring filter is applied to text or station circles. Map overlays use the device pixel density, capped at 1.5× to limit GPU load. The Map tile detail setting controls basemap refinement independently of the markers.
- Cesium starts in 2D. Use Map settings → Map view to switch between 2D and a 3D globe with an ellipsoid surface. Zoom or reset the view with the map controls.
- Map tile detail selects 0.5×, 0.75×, 1× (default), 1.5×, 2×, or 3× basemap refinement. Higher values can load more detailed tiles; available detail depends on tile zoom levels. Marker and line resolution uses the device pixel density, capped at 1.5×.
- Select a station from the list or map to inspect its coordinates, scheduled stop count, and arrivals and departures. The timetable follows the map date and time, with a choice between upcoming services and the full day; it includes overnight visits from the preceding two service days. Times are scheduled, not live updates.
- Station counts represent stop visits in the schedule without expansion over service dates. Counts are not passenger totals or live train movements.
- Stations are shown as individual dots at every zoom level. Select a dot to view station details.
- Stations without valid coordinates are excluded from the map. Stations with no scheduled visits remain visible.
- The minimal Esri Light Gray Canvas basemap uses grayscale imagery with increased contrast and requires internet access. Station dots use light outlines. No Cesium ion token is needed. Cesium assets are copied locally by the development/build scripts. The interface uses Google Fonts with system-font fallbacks.
- Nitro caches station responses for 60 seconds. It queries each Gold table's current snapshot, so a concurrent pipeline publication may expose a mixture of table snapshots until it completes.

## Checks and production

```bash
npm test
npm run typecheck
# With the app running and Google Chrome installed
npm run test:e2e
npm run build
HOST=127.0.0.1 PORT=7007 npm run start
```

The production build includes the Nitro Node.js server in `.output/server/index.mjs`. In Docker, the process listens on container port 3000, published only on `127.0.0.1:7007`.

Station dots use compact sizes to indicate scheduled activity.

The floating timeline controls scheduled train estimates. Active services are read from Gold stop times for the selected date (including overnight services). Each train is represented by a pentagon marker in both 2D and 3D. A Web Worker builds the operating RFN graph and computes routes without blocking map interaction. Stations snap to the nearest point on a track segment within 2 km; line endpoints within 20 m of another segment are connected to repair small cartographic junction gaps. Interior crossings are not automatically joined. Positions interpolate between scheduled station times along shortest connected operating RFN paths, using cached cumulative distances. These are timetable estimates, not GPS positions or confirmed train routings. Services without a connected path within 2 km of their stations are omitted and counted above the timeline.

The interface uses Nuxt UI 4 with Tailwind CSS, wrapped in `UApp`. Buttons, inputs, date fields, selectors, switches, cards, alerts, icons, collapsibles, the settings modal, and timeline slider use Nuxt UI primitives. Map theme tokens also apply to teleported settings and select menus. Run `npx playwright test tests/nuxt-ui.e2e.ts` for the UI migration smoke test.

Use the timeline play/pause button to freeze or resume the selected time. Editing the date or dragging the slider pauses playback; press Play to advance from that time, or Now to return to the live clock. Playback continues across midnight.

## Statistics

The Statistics page displays counts of station, trip and route records in the current Gold tables, plus stop visits and the five stations with the most visits. Trips and visits are counted once per timetable record; they are not expanded across service dates. Station totals include stations without usable coordinates, which are excluded from the map.

Operating rail length is the sum of geodesic lengths of the operating RFN feature geometry. Overlapping or duplicated geometry may be counted more than once, and the total is infrastructure length, not a sum of train journey distances. The schedule and rail totals load independently so a MinIO outage does not hide the schedule statistics.
