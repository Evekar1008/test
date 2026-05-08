# Produksjonscelle web-app

Flask-basert utviklingsversjon for produksjonscelle med Haenel LeanLift, Gudel/ABB portalrobot og CMZ/Fanuc CNC. Appen er fortsatt en simulator, men den har naa en felles cellestatus for HMI, REST-API og OPC UA.

## Sider i appen
- `/` Dashboard: produksjonsordre, programvalg, maskinstatus, safety-status, aktivt hyllekart og hurtigsignaler.
- `/shelves`: hyllekart i skala, definerbare hyllemaal, grafisk produksjonslayout og manuell inn/utlasting.
- `/parts`: deltyper og inventaroversikt.
- `/cnc`: CNC-status, whitelisted programvalg per produkt og simulerte FOCAS-kall.
- `/lift`: LeanLift-status, hurtigvalg for hylle/uttak og Host-Web-kommandoer fra referansefil.
- `/opcua`: OPC UA-simulatorstatus og webbasert signaltest.
- `/stats`: statistikk, produksjonsordre og hendelseslogg.
- `/diagnostics`: raa kommunikasjon/logg mellom simulerte enheter.

## OPC UA simulator
Serveren startes sammen med `python app.py` dersom pakken `opcua` er installert.

- Endpoint: `opc.tcp://<host>:4840/production-cell/sim/`
- Namespace: `urn:bergsli:production-cell:simulation`
- Toppnode: `Objects/ProductionCell`

UAExpert kan skrive til noder under:
- `Cell`: `Mode`, `Command`, `Message`
- `Safety`: `EmergencyStopActive`, `GatesClosed`, `ScannerClear`
- `LeanLift`: `CurrentShelf`, `AccessPoint`, `TrayPresent`, `TrayExtended`, `DoorClosed`, `AlarmActive`, `StatusMessage`
- `Robot`: `Ready`, `Busy`, `Fault`, `AtHome`, `PartInGripper`, `StationComplete`, `ActiveTask`, `StatusMessage`
- `CNC`: `MachineReady`, `CycleRunning`, `CycleComplete`, `AlarmActive`, `PartPresent`, `SelectedProgram`, `StatusMessage`
- `Cell/Command`: kommandoer som `GET_SHELF 7`, `TRAY_EXTEND`, `TRAY_HOME`, `CNC_START`, `CNC_COMPLETE`, `SAFETY_TRIP`, `SAFETY_OK`, `ROBOT_FAULT`, `RESET_ALARMS`, `MODE AUTO`, `MODE SETUP`, `MODE SERVICE`

## API (utdrag)
- `GET /api/state`
- `GET /api/leanlift/shelf-layout/<shelf>`
- `POST /api/shelf/configure-graphic`
- `POST /api/shelf/slot/update`
- `POST /api/parts`
- `POST /api/production/start`
- `POST /api/production/stop`
- `POST /api/cnc/program/select`
- `POST /api/cnc/focas`
- `POST /api/lift/command`
- `POST /api/opcua/start`
- `POST /api/opcua/signal`
- `GET /api/diagnostics`
- `POST /api/simulation/start|pause|step`

## Status mot Functional Description
- Host-Web/WSDL-operasjoner lastes fra `doc/hostweb_reference.json` og speiler `doc/macro.wsdl`.
- FOCAS-funksjoner lastes fra `focas/focas_reference.json`.
- Produksjonsstart validerer valgt CNC-program mot produktets whitelist og sjekker tilgjengelige raemner i inventar.
- Safety og maskinhandshakes er simulert via HMI/API/OPC UA. Raspberry Pi/webappen er ikke en safety-controller.
- Data ligger fortsatt i minne. Database, innlogging/roller, ekte SOAP/FOCAS/ABB RWS og endelig safety/integrasjonslogikk gjenstaar.

## Kjor lokalt
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Deretter kan HMI aapnes paa `http://localhost:5000`, og UAExpert kan kobles til endpointet over.
