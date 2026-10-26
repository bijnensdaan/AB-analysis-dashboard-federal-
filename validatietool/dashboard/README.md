# Dashboardmodule

Zie de [README van de repository](../../README.md) voor installatie, datavoorbereiding, starten en tests, en de [gebruikershandleiding](../../docs/GEBRUIK.md) voor de interface.

- `data/`: alleen-lezen bronqueries, configuratie, repositories en gecontroleerde lokale snapshotcaches.
- `logic/`: selecties, filters, teleenheden, orgaankoppeling, vertalingen en exports.
- `ui/`: controle-CLI, lokale HTTP-server en webinterface.
- `tests/`: tests met tijdelijke data en nagebootste bronnen.

`requirements-fase6.txt` omvat alle runtime-afhankelijkheden via de eerdere requirementsbestanden. `.env.example` documenteert de ondersteunde instellingen. Echte credentials en gegenereerde data horen buiten Git.
