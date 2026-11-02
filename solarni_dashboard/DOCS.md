# Solarni monitor

Nadzorna ploča solarne elektrane u Home Assistantu (bočna traka → **Solarni monitor**). Podatke vuče s add-ona
**Solarni poslužitelj** (ili sa samostalnog poslužitelja na drugom računalu).

## Opcije
- **server_url** – `http://172.30.32.1:8700` kad je poslužitelj add-on na istom HA; inače `http://IP:8700`.
- **api_token** – prazno kad je poslužitelj na istom HA (čita se iz `/share/solarni/api_token`).
- **Port 8600** (Mreža) – pregled iz lokalne mreže za TV/tablet bez HA računa: upišite port, zatim u
  Postavke → Sustav uključite *Pregled iz mreže* i upišite pristupni ključ u preglednik. Samo za čitanje.

## Prečaci
F11 / Alt+Enter / dvoklik – cijeli zaslon · F2 – postavke · F1 – pomoć · F5 – osvježi · Ctrl+Z – poništi promjenu
rasporeda. Raspored widgeta: kartica „Widgeti” uz desni rub.

Prijava je prijava u Home Assistant. Postavke i raspored mogu se dodatno zaključati PIN-om (Postavke → Sustav).
