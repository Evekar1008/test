# Produksjonscelle web-app

Flask-basert webapp for produksjonscelle med Lean-Lift, ABB/Güdel og Fanuc CNC.

## Ny funksjonalitet i denne versjonen
- **1:1 hyllekart per valgt hylle** med visning av delplasseringer.
- Hver deltype har **spesifisert størrelse** (diameter/lengde/høyde).
- **X/Y/Z-koordinat** vises for alle deler i koordinattabellen.
- **Settings** for `shelf_width_mm` og `shelf_depth_mm`.
- **Maler (templates)** for plassering av deler på hyller.
- Én plasseringstype per hylle (homogen deltype per hylle).
- Hyller er identifisert med nummer fra **1 til 50**.

## Kjør lokalt
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

## API (utdrag)
- `GET /api/state`
- `GET /api/leanlift/shelf-layout/<shelf>`
- `POST /api/settings`
- `POST /api/layout-templates`
- `POST /api/shelf/apply-template`
- `POST /api/select-product`
- `POST /api/cnc/select-program`

## Regel for hylleinnhold
- Alle delene på en hylle skal være av samme deltype.
- En layout-mal kan ha flere posisjoner, men `part_type_id` må være lik for alle plasseringer i malen.


## Simulering
- Ja, programmet kan simuleres i denne versjonen.
- Bruk knapper i UI: **Start simulering**, **Pause simulering**, **Kjør ett steg**.
- API-endepunkter: `POST /api/simulation/start`, `POST /api/simulation/pause`, `POST /api/simulation/step`.
- Simuleringen oppdaterer robotstatus, CNC-signaler (spindle/feed/state), aktiv hylle og hendelseslogg.
