# Produksjonscelle web-app

Flask-basert webapp for produksjonscelle med Lean-Lift, ABB/Güdel og Fanuc CNC.

## Sider i appen
- `/` Dashboard: aktiv hylle-kart i hovedbilde, produksjonsstart (antall eller alle av type), simulering start/pause/step.
- `/shelves`: definer hvor delene ligger på hyller (lagre mal + bruk mal på hylle).
- `/parts`: definer deltyper (diameter/lengde/høyde/antall).
- `/cnc`: ekstra CNC-info og flere FOCAS-funksjoner med dynamiske inputfelt.
- `/lift`: heis-side med REST-kommandoer, dynamiske inputfelt og responsvisning.
- `/stats`: statistikk og historikk for cellen.

## Viktige funksjoner
- Hyller er identifisert med nummer fra **1 til 50**.
- Hovedkartet viser alltid **aktiv hylle** (fra simulering).
- Delkoordinater inkluderer **X/Y/Z**.
- Én deltype per hylle-mal (homogen deltype).

## API (utdrag)
- `GET /api/state`
- `GET /api/leanlift/shelf-layout/<shelf>`
- `POST /api/production/start`
- `POST /api/layout-templates`
- `POST /api/shelf/apply-template`
- `POST /api/parts`
- `POST /api/cnc/focas`
- `POST /api/lift/command`
- `POST /api/simulation/start`
- `POST /api/simulation/pause`
- `POST /api/simulation/step`

## Kjør lokalt
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```
