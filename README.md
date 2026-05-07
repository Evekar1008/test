# Produksjonscelle web-app

Flask-basert webapp for produksjonscelle med Lean-Lift, ABB/Güdel og Fanuc CNC.

## Sider i appen
- `/` Dashboard: aktiv hylle i hovedbildet, produksjonsordre (antall eller alle av type), simulering, fargeinnstillinger for statuser.
- `/shelves`: grafisk hyllekonfig (ingen ren JSON nødvendig), manuell inn/utlasting per lokasjon.
- `/parts`: definere deltyper.
- `/cnc`: CNC-status og FOCAS-funksjoner.
- `/lift`: LeanLift REST-kommandoer (simulert), dynamiske felter og responsvisning.
- `/stats`: statistikk og historikk.
- `/diagnostics`: rå kommunikasjon mellom enheter.

## Viktige funksjoner
- Hyller 1–50.
- Aktivt hyllekart i dashboard følger alltid aktiv hylle.
- Deler på hylle er nummerert (`slot_no`), og farge endres med status.
- Farger for status kan endres i settings fra dashboard.
- Hyllekonfig viser én valgt hylle om gangen.
- Manuell last/avlast for heis-lokasjoner via hyllekonfig-siden.

## API (utdrag)
- `GET /api/state`
- `GET /api/leanlift/shelf-layout/<shelf>`
- `POST /api/shelf/configure-graphic`
- `POST /api/shelf/slot/update`
- `POST /api/parts`
- `POST /api/production/start`
- `POST /api/cnc/focas`
- `POST /api/lift/command`
- `GET /api/diagnostics`
- `POST /api/simulation/start|pause|step`

## Merk
FOCAS-funksjonslisten lastes fra `focas/focas_reference.json`, og LeanLift/HOST-WEB kommandoer lastes fra `doc/hostweb_reference.json`. Kallene er fortsatt simulert, men kommando-/funksjonsnavn og dynamiske felter speiler dokumentasjonen. Store vendorfiler er fjernet for å unngå diff/PR-feil som "binary files not supported".

## Kjør lokalt
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```
