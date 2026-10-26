# Het dashboard gebruiken

## Openen

Dubbelklik in de map **Analysis** op **Start dashboard.cmd**. Het dashboard opent
op <http://localhost:8780/#overview>. Een bestaande dashboardserver wordt
hergebruikt; anders start de lokale server op de achtergrond. Een andere toepassing
op poort 8780 wordt niet gestopt. Er wordt niet naar een willekeurige poort uitgeweken.

Vanuit PowerShell kan hetzelfde met:

```powershell
python -B validatietool/open_dashboard.py
```

Dit start geen nieuwe classificaties en ververst de brongegevens niet. Sluiten van
de browsertab stopt de server niet. Na een herstart van de computer gebruik je de
startknop opnieuw. Bij een startfout staat de uitleg in `tmp/dashboard-start.log`.
Als een link vanuit de chat niet opent, typ het adres rechtstreeks in Chrome of Edge.

## Grafieken en doorklikken

Kies **Overzicht → Informatiestromen en grafieken**. Compacte verdelingen tonen
standaard **Alle categorieën**. De drie IO-grafieken tonen daarmee alle aanwezige
IO-types binnen de actieve selectie. Een filter kan het aantal aanwezige types
verminderen. De taxonomiebenamingen komen uit de bron en zijn deels Engelstalig.

Lijsten met vrije actornamen, datavelden en wetsverwijzingen kunnen tienduizenden
categorieën bevatten. Daar toont de grafiek standaard de top 10. Boven de grafiek
staat hoeveel categorieën worden getoond. Met **Weergave** kun je een andere grens
kiezen; die keuze wordt per grafiek onthouden zolang de pagina geopend blijft.

Klik op een balk, band of heatmapcel om de bijbehorende acts te bekijken. De filters
blijven van toepassing. Bij een kruistabel is een cel een datapunt: bijvoorbeeld
19 IO-types over 6 bestuursniveaus zijn maximaal 114 mogelijke cellen, geen 114
verschillende types. Alleen opgeslagen combinaties zijn doorklikbaar. Een lege cel
betekent geen geregistreerde observatie binnen deze selectie.

Onder **Exacte waarden, broncitaten en actlijst** staan de volledige labels en
aantallen van de getoonde punten. **Broncitaten** toont lezersbewijs;
**Bronbewijs** bij organen/rubrieken toont de hoofding of ministerportefeuille.
**Gekoppelde acts** leidt bij actverdelingen naar de onderliggende publicaties.
In het actdetail staan de oorspronkelijke beoordelingen, historie en bronverantwoording.

## Exporteren

- **PNG** exporteert de getoonde grafiek met bronmomenten, filters en vermelding
  van de getoonde categorieën. Bij organen/rubrieken staat ook de dekking erin.
- **CSV (getoond)** bevat de exacte waarden van de getoonde grafiek.
- **Volledige CSV** verschijnt wanneer categorieën verborgen zijn. Deze download
  bevat alle aanwezige categorieën binnen dezelfde actieve filters, ook bij de
  grote vrije lijsten. Het bestand kan groot zijn.
- De CSV vermeldt of het een beperkte of volledige export is, de getoonde/totale
  categorieën, teleenheid, bronmomenten, snapshot-/projectieversie en filters.
- Actdetails hebben afzonderlijke PDF- en Markdown-exports met brongegevens en
  beoordelingen. Dit zijn geen exports van alleen de zichtbare grafiekselectie.

## De cijfers lezen

**Acts**, **registerbepalingen** en **lezersclaims** zijn verschillende teleenheden.
Een bepaling kan door verschillende lezingen in meerdere categorieën vallen.
Categorieregels mogen daarom niet zonder meer worden opgeteld tot één totaal.
Gelijk vertaalde broncodes blijven afzonderlijk herkenbaar met hun code.

**Onbekend** betekent dat iets niet is vastgesteld. Het is geen nul en geen
negatieve classificatie. De beleidsrubriek volgt een diensthoofding of expliciete
voordragende ministerportefeuille; het onderwerp van iedere act is niet inhoudelijk
geclassificeerd. De bekende rubrieken vormen geen representatieve steekproef.

Percentages ten opzichte van het corpus ontbreken wanneer voor de actieve filters
geen gecontroleerde noemer beschikbaar is. Informatiestromen tonen directe
opgeslagen relaties. De actverkenner toont mogelijke aansluitingen; dit zijn geen
bevestigde informatieketens en geen gemeten aantallen berichten, personen of kosten.

De bronmomenten staan in het dashboard. Gewone grafiekverzoeken gebruiken de
bewaarde lokale gegevens; het is geen live weergave van iedere bronwijziging.
