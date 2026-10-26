# AB analysis dashboard (federal)

Alleen-lezen dashboard voor administratieve lasten in federale regelgeving: overzicht, filters, actlijst, bronbewijs, actdetails, grafieken, exports en een Nederlandse en Engelse interface.

## Installeren

Gebruik Python 3.12. Voer alle opdrachten uit vanuit de repositorymap:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r validatietool/dashboard/requirements-fase6.txt
Copy-Item validatietool/dashboard/.env.example .env
```

Vul de database-instellingen in de lokale `.env` in. Procesvariabelen met dezelfde `AB_*`-namen worden ook ondersteund. De voorbeeldconfiguratie bevat geen credentials.

## Data voorbereiden

Deze branch bevat dashboardbroncode, SQL, tests, startscripts en documentatie. Database-exporten, snapshots, tekstcaches, gegenereerde grafieken en analyse-archieven zijn niet opgenomen. Een nieuwe checkout heeft eerst lokale data nodig.

Met toegang tot de bestaande register- en corpusdatabanken kunnen de snapshots in onderstaande volgorde opnieuw worden opgebouwd. De bronverbindingen zijn alleen-lezen; uitvoer wordt lokaal opgeslagen onder `validatietool/data/`.

```powershell
python -B validatietool/controle_dashboard.py --ververs
python -B validatietool/start_dashboard.py --alleen-verversen
python -B validatietool/koppel_overheidsorganen.py --uitvoer tmp/orgaankoppeling
python -B validatietool/ververs_overzicht.py
python -B validatietool/bouw_grafiekcache.py
```

Herstart de server na een verversing. Bestaande compatibele snapshots kunnen afzonderlijk worden overgezet. De cache-identiteit hangt af van de bronconfiguratie; grafiekmanifesten kunnen absolute corpuspaden bevatten. Bouw de grafiekcache na verplaatsing opnieuw op. Actteksten worden op aanvraag uit een lokale tekstcache of de bron geladen. EU-teksten vereisen een bronverbinding.

## Starten

```powershell
python -B validatietool/start_dashboard.py --geen-browser
```

Open <http://localhost:8780/#overview>. Stop met Ctrl+C. Onder Windows opent `Start dashboard.cmd` het dashboard en start het zo nodig op de achtergrond. De server luistert op `127.0.0.1`.

Zie de [gebruikershandleiding](docs/GEBRUIK.md) voor filters, grafieken en exports.

## Controles

```powershell
python -B -m unittest discover -s validatietool/dashboard/tests -t validatietool
```

De tests gebruiken tijdelijke fixtures en nagebootste bronverbindingen, zonder productiegegevens of databasecredentials.

## Deployment-branch

`deployment` bundelt de relevante dashboardbestanden. Pushen publiceert broncode; de repository bevat geen hostingconfiguratie of automatische live deployment. Voor externe hosting zijn een geschikte Python-serveromgeving, lokale snapshots en afzonderlijk ingestelde credentials nodig.
