# barbl-kb

Knowledge base dei piani di allenamento di Barbl: file YAML letti come dati da `barbl-engine`, che produce i piani del contratto dell'app (`vscafuto87/barbl`, `docs/contratto/`). Il motore non contiene numeri di dominio: stanno tutti qui.

## Struttura

- `VERSION` — `rulesVersion` della KB (semver). Ogni modifica che cambia un piano generato alza la versione.
- `schema/` — JSON Schema di ogni tipo di file. La CI li applica.
- `contract/` — copia degli schemi del contratto dell'app (`plan.schema.json`, `profile.schema.json`), con il commit di origine in `contract/SOURCE.md`. Non si modificano qui: si aggiornano dall'app.
- `vocab/` — vocabolari chiusi: muscoli, pattern di movimento, attrezzatura.
- `sources/` — una fonte per file.
- `principles/` — un principio per file, in sottocartelle per tema.
- `exercises/` — un esercizio per file, in sottocartelle per pattern.
- `templates/` — split e sedute fatte di slot.
- `prescriptions/` — serie, ripetizioni e recupero per obiettivo e ruolo.
- `parameters/` — un file per gruppo del blocco `parameters` del contratto, più il mesociclo.
- `rationales/` — testi del «Perché?» in italiano e inglese, uno per `ruleId`.
- `conflicts.yaml` — conflitti tra fonti e decisioni prese.
- `golden/` — profili sintetici e proprietà attese, per le eval del motore.
- `tools/` — validatore (`python3 tools/validate.py`) e strumenti di estrazione.

## Regole che non si discutono

- **Mai il testo delle fonti.** Le fonti con `use: internal` (libri e programmi acquistati) entrano solo come riferimento: titolo, pagina, file locale. Ogni frase della KB è scritta con parole nostre. Il validatore, con `--sources-md`, cerca sequenze di 8 parole copiate dai Markdown estratti.
- **I PDF, i Markdown estratti e i dati strutturati dei programmi non entrano mai nel repository.** Restano in `~/Progetti/app-palestra/sources/` sul Mac.
- **Ogni numero ha un'origine.** Un valore di `parameters/` o `prescriptions/` cita i principi da cui viene; se nessuna fonte lo sostiene è un principio di tipo `design`, dichiarato come tale.
- **Gerarchia delle fonti** per risolvere i conflitti (`tier`): 1 position stand e umbrella review, 2 meta-analisi e meta-regressioni, 3 RCT, 4 libri e programmi di autori evidence-based, 5 pratica dei coach e scelte di design. Un conflitto si registra in `conflicts.yaml`, non si nasconde.
- **Provvisorio finché non confermato.** Un principio è `confirmed` solo con almeno una fonte primaria letta nel testo completo (`access: full_text`) e la revisione di un coach (`reviewedBy`). Un gruppo di parametri ha `provisional: false` solo se tutti i suoi principi sono confermati. Un principio con un conflitto `open` non alimenta un parametro confermato.
- **Programmi famosi come termine di confronto, non come regole.** Entrano nelle eval e nella struttura dei template (pattern, ruoli, sostituzioni), mai con nomi commerciali, note o tabelle copiate.
- **Identificativi in inglese**, uguali a quelli del contratto (`exerciseId`, `ruleId`, valori di `equipment` e `split`). Testi per l'utente in italiano e inglese.
- **Nessun consiglio medico** nei testi.

## Comandi

- Validazione: `python3 tools/validate.py` (richiede `pyyaml` e `jsonschema`)
- Controllo dei testi copiati: `python3 tools/validate.py --sources-md ~/Progetti/app-palestra/sources/md`

## Modo di lavorare

- **Mai commit diretti su `main`.** Ogni modifica va su un ramo (`kb/…`, `fix/…`, `docs/…`) e arriva su `main` con una pull request approvata da Vincenzo.
- Prima di dichiarare finito: `python3 tools/validate.py` senza errori.
- Una pull request per tema (una ricerca, un gruppo di esercizi, un template).
- Commit e testi in italiano.
- Se un dato non ha una fonte, non inventarlo: segnalo come scelta di design o chiedi.
