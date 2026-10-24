# O/U Club — NBA 2026–27

Una sola home per confrontare i pronostici di **Met, Sasso, Zach, Bill e House** con una proiezione lineare del record NBA su 82 partite. Nessun account, chiave API, database o servizio a pagamento.

## Pubblicare sul tuo GitHub

1. Crea un repository **pubblico**, per esempio `nba-ou`, con branch principale `main`.
2. Carica i contenuti di questa cartella nella radice del repository: `index.html`, `assets/`, `data/`, `scripts/`, `tests/`, **`.github/workflows/daily-pages.yml`**, `.gitignore`, `NBA_OU.xlsx` e questo README. La cartella `.github` è indispensabile: non ometterla perché inizia con un punto. Non caricare lo ZIP o `_site`.
3. In **Settings → Pages → Build and deployment → Source**, scegli **GitHub Actions**.
4. Apri **Actions → NBA O-U · aggiorna e pubblica → Run workflow**. Se richiesto, abilita Actions per il repository.
5. Dopo il completamento, il link appare in **Settings → Pages** e nello step di deployment. Sarà normalmente `https://TUO-USERNAME.github.io/nba-ou/`.

Se carichi i file dal browser GitHub, accertati che `.github/workflows/daily-pages.yml` sia stato incluso: puoi anche crearlo con **Add file → Create new file**, incollando il contenuto e usando il percorso completo come nome del file.

Da quel momento GitHub esegue il workflow **ogni giorno alle 08:00, Europe/Berlin** (stesso orario civile di Italia e Belgio), con passaggio automatico fra ora solare e legale. Il computer può rimanere spento. Gli scheduler di GitHub possono subire ritardi, quindi non è garantito l’aggiornamento alle 08:00 esatte.

Il workflow richiede soltanto i permessi del `GITHUB_TOKEN` automatico dichiarati nel file YAML; non servono secrets. Un commit automatico con quel token non avvia ricorsivamente un altro workflow. Branch protetti che vietano i commit del bot richiedono una configurazione apposita. In un repository pubblico senza attività per 60 giorni GitHub può disattivare la programmazione; i normali commit giornalieri dello storico mantengono il repository attivo. Non archiviarlo e non disattivare Actions durante la stagione.

**Per aggiornare i pronostici:** sostituisci `NBA_OU.xlsx` nel repository conservando la struttura attuale (intestazioni in riga 3, squadre nelle righe 4–33). “Io” diventa Met; il grassetto nelle celle dei pronostici identifica i locks. Il workflow reimporta il file. Gli O/U restano quelli del file originale, senza inseguire nuove quote. Modificare le scelte ricalcola anche i grafici dello storico secondo le nuove scelte: lo storico conserva i record NBA, non le vecchie versioni dei pronostici.

## Anteprima locale

Con Python 3.12+ e Node.js 20+ disponibili:

```powershell
python -m http.server 8765 --bind 127.0.0.1
```

Apri [http://127.0.0.1:8765](http://127.0.0.1:8765). Non aprire `index.html` con doppio clic: i browser bloccano il caricamento dei JSON da `file://`.

Per reimportare il file, aggiornare i record o verificare il progetto:

```powershell
python scripts/import_picks.py
python scripts/update_records.py
python -m unittest discover -s tests -p "test_*.py"
node --test tests/model.test.mjs
python scripts/build_static.py
```

Su Windows può essere necessario `pip install tzdata` se il tuo Python non comprende il database dei fusi orari. I runner Linux di GitHub lo includono già. Nessuna altra dipendenza Python o JavaScript è richiesta.

## Fonte e riutilizzo

**Wikipedia, tramite l’API ufficiale MediaWiki**, pagina [2026–27 NBA season](https://en.wikipedia.org/wiki/2026%E2%80%9327_NBA_season). Il programma fa una richiesta per esecuzione alla pagina della stagione ed estrae le colonne W/L. Non effettua scraping di siti sportivi commerciali e non usa loghi o fotografie di terzi.

Attribuzione: autori e contributori della pagina Wikipedia sulla stagione NBA. I record sono estratti, convertiti in JSON e usati per calcolare nuove proiezioni. Contenuti della fonte riutilizzati secondo [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/); l’attribuzione e la licenza accompagnano ogni snapshot, la home e i JSON pubblicati. Le stesse condizioni si applicano ai dati della fonte redistribuiti e adattati; i tuoi pronostici hanno origine nel tuo Excel.

Riferimenti: [accesso e licenze delle API Wikimedia](https://www.mediawiki.org/wiki/Wikimedia_APIs/Access_policy), [API Usage Guidelines](https://foundation.wikimedia.org/wiki/Policy:Wikimedia_Foundation_API_Usage_Guidelines). Il client si identifica con uno User-Agent che include il repository quando gira su GitHub. Rispetta le risposte di rate limit e `Retry-After`, con tentativi limitati; non aggira blocchi o limiti usando altri endpoint.

Wikipedia è una fonte comunitaria: le classifiche possono essere aggiornate in ritardo. “Dati prelevati il…” indica l’ora del download, non certifica che tutte le partite più recenti siano già state inserite. Il parser richiede **30 squadre distinte**, W/L interi non negativi, al massimo 82 gare per squadra, totali di vittorie e sconfitte uguali e nessuna discrepanza fra tabelle duplicate. Su errori, stagione errata o risposta incompleta, **lo storico non viene sovrascritto**. Il workflow pubblica l’ultimo snapshot valido e segnala l’errore in Actions. La home evidenzia dati prelevati oltre 36 ore prima; non può rilevare tutte le possibili omissioni della fonte.

## Calcoli e grafici

- **Vittorie proiettate** = `82 × V / (V + S)`; sconfitte proiettate = `82 − vittorie proiettate`. Senza partite, N.D.
- **Margine Over** = `proiezione − linea`. **Margine Under** = `linea − proiezione`.
- Positivo = giusto, negativo = sbagliato, zero = pari. Nessun arrotondamento prima del conteggio (tolleranza numerica 1e-9); in pagina un decimale. Pari e N.D. sono esclusi dalla percentuale di successo.
- **Locks:** Met 10, Sasso 10, Zach 6, Bill 7, House 6. Stesso peso degli altri pronostici; i grafici confrontano percentuali e mostrano anche conteggi e denominatori.
- La scala rosso–bianco–blu è identica per tutti, centrata a zero e satura a ±20. Il numero conserva il margine completo. ◆ identifica i locks, con bordo aggiuntivo. ✓ indica un esito matematicamente già certo, ricavato dalle vittorie/sconfitte effettive.
- Tabella ricercabile e ordinabile, filtro East/West e “Solo locks” (squadre con almeno un lock; le celle non lock sono attenuate). I filtri della tabella non cambiano i grafici.
- Grafici di giusti/sbagliati totali e locks; andamento giornaliero; matrice di accordo sui pronostici; cinque scelte solitarie con i margini assoluti più grandi.
- Lo storico conserva **uno snapshot per giorno locale** in `data/history.json`. Un nuovo prelievo nello stesso giorno sostituisce quello del giorno, senza duplicazioni. Nessun passato viene inventato: inizialmente si vede un solo punto.

Il sito è statico, responsive, senza analytics, cookie, librerie o font remoti. La pubblicazione copia soltanto HTML, CSS, JS e JSON in `_site`: l’Excel, i test e gli script non vengono serviti da Pages. Se il repository è pubblico, il file Excel nel repository è comunque consultabile.

## File

| Percorso | Funzione |
| --- | --- |
| `index.html`, `assets/` | Unica home, stile, grafici e calcoli |
| `NBA_OU.xlsx` | Fonte originale di linee, pronostici e locks |
| `data/picks.json` | Pronostici estratti dall’Excel |
| `data/history.json` | Record NBA, timestamp, fonte e storico |
| `scripts/import_picks.py` | Importatore Excel senza librerie esterne |
| `scripts/update_records.py` | Prelievo, validazione e salvataggio atomico |
| `scripts/build_static.py` | Prepara i soli file pubblici |
| `.github/workflows/daily-pages.yml` | Aggiornamento alle 08:00 e pubblicazione Pages |
| `tests/` | Test di calcolo, parser, locks e conservazione dati |
