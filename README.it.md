# icloud-sync

> 🇬🇧 [Read this page in English](README.md)

[![CI](https://github.com/intilinux-eng/icloud-sync/actions/workflows/ci.yml/badge.svg)](https://github.com/intilinux-eng/icloud-sync/actions/workflows/ci.yml)

Sincronizzazione **bidirezionale e automatica** di iCloud Drive su Linux.
Una cartella locale (`~/iCloudDrive`) resta allineata con iCloud Drive: quello che cambi sul PC sale in pochi secondi, un file aggiunto da iPhone o Mac compare sul PC in genere entro mezzo minuto.

> Progetto indipendente, non affiliato ad Apple. iCloud è un marchio di Apple Inc.
> Software fornito **senza alcuna garanzia** (licenza MIT): tieni sempre un backup dei dati importanti.

## Usato tutti i giorni

icloud-sync non è una demo. Il suo autore lo usa ogni giorno sul proprio iCloud Drive (in uso quotidiano da novembre 2026), e ciò che lì si rompe o dà fastidio decide che cosa viene sistemato dopo. Diverse funzioni esistono solo perché l'uso reale ha fatto emergere il problema:

- cartelle condivise e documenti iWork facevano fallire ogni sincronizzazione: ora vengono riconosciuti ed esclusi da soli;
- iCloud risponde cinque volte più lentamente subito dopo ogni modifica: da qui la corsia veloce per i file nuovi;
- eliminare un file su tre faceva scattare il blocco delle eliminazioni di massa: ora poche eliminazioni passano sempre.

Se da te si comporta male, [apri una segnalazione](https://github.com/intilinux-eng/icloud-sync/issues): è così che migliora.

## Perché esiste

Apple non offre un client Linux e iCloud Drive non espone un filesystem né SSH: strumenti come `rsync` o `unison` non possono parlarci direttamente. L'unico motore maturo è [rclone](https://rclone.org/iclouddrive/), che dalla v1.69 ha un backend iCloud Drive nativo, e [`rclone bisync`](https://rclone.org/bisync/) per la sincronizzazione a due vie.

Usare `rclone bisync` a mano però significa scrivere da sé flag, filtri, timer, gestione errori e rinnovo del login. `icloud-sync` è lo strato che manca:

| Problema | Cosa fa icloud-sync |
|---|---|
| iCloud non notifica le modifiche a client esterni | inotify sul lato locale (reazione in ~5 s); sul lato iCloud un controllo leggero da una sola richiesta ogni 10 s, e sincronizzazione solo quando qualcosa è cambiato |
| Dopo ogni modifica iCloud elenca il Drive 5 volte più lentamente | "corsia veloce": i file nuovi vengono scaricati subito scendendo solo nelle cartelle il cui etag è cambiato |
| Un elenco remoto vuoto o errato cancellerebbe tutto | file di controllo su entrambi i lati, blocco delle eliminazioni di massa, nessuna propagazione se un lato risulta vuoto |
| Stesso file modificato su due dispositivi | vince il più recente, l'altro viene conservato come `nome.conflict1.ext` |
| Stato di bisync corrotto dopo un crash | `--resilient --recover` e ricostruzione automatica (che non elimina mai nulla) |
| File che rclone non riesce a scaricare (cartelle condivise, documenti iWork) | esclusi automaticamente e segnalati, invece di far fallire ogni sync (`icloud-sync skipped`) |
| Il login Apple scade ogni 30 giorni | promemoria 4 giorni prima, notifica alla scadenza, `icloud-sync login` |
| PC sospeso, rete assente | nessun tentativo offline, ripresa automatica |

## Installazione

### Pacchetto Debian / Ubuntu

Scarica il file `.deb` dall'ultima [release](https://github.com/intilinux-eng/icloud-sync/releases) e installalo:

```bash
sudo apt install ./icloud-sync_*_all.deb
```

Poi, come utente normale:

```bash
icloud-sync setup
```

### Senza pacchetto

Basta il singolo file `icloud-sync` (Python ≥ 3.11, nessun modulo da installare):

```bash
python3 icloud-sync setup
```

### Cosa fa `setup`

La procedura guidata installa rclone se manca o è troppo vecchio (binario ufficiale, checksum verificato, in `~/.local/bin`), chiede Apple ID, password e codice a due fattori, esegue la prima sincronizzazione e attiva servizio in background e icona nel vassoio.

Note sul login:

- serve la password normale dell'Apple ID (Apple non accetta qui le "password per app"); viene salvata offuscata nella configurazione locale di rclone;
- con la **Protezione avanzata dei dati** attiva, abilita prima *Accedi ai dati iCloud sul web* su iPhone (Impostazioni → account → iCloud).

## Icona nel vassoio

`icloud-sync enable` avvia anche un'icona nel vassoio di sistema (serve `python3-pyqt6`). Il bollino indica lo stato: verde sincronizzato, blu sincronizzazione in corso, rosso serve un tuo intervento, grigio offline o servizio fermo.

- **Clic sull'icona** o *Apri cartella iCloud Drive*: apre la cartella nel gestore file.
- **Sincronizza ora**: avvia subito un giro completo.
- **Metti in pausa / Riprendi**: sospende la sincronizzazione automatica; alla ripresa recupera tutto.
- **Elementi esclusi** e **Registro attività**: ciò che non si è potuto sincronizzare e le ultime operazioni.
- **Rinnova accesso Apple**: apre una finestra per password e codice a due fattori, senza terminale, e mostra i giorni rimasti.

In Dolphin la cartella ha un'icona a nuvola; un piccolo plugin facoltativo aggiunge gli emblemi di stato su ogni file (sincronizzato, in attesa, conflitto): vedi [dolphin/](dolphin/README.md).

Le notifiche hanno pulsanti: *Mostra* su un file appena arrivato, *Rinnova accesso* quando Apple lo richiede.

## Uso da terminale

```text
icloud-sync status          stato, ultima sync, giorni rimasti al login
icloud-sync sync            sincronizza subito (--dry-run per l'anteprima)
icloud-sync login           rinnova il login Apple (circa ogni 30 giorni; --gui apre una finestra)
icloud-sync pause|resume    sospende e riprende la sincronizzazione automatica
icloud-sync log             ultime operazioni (--error: log rclone dell'ultimo errore)
icloud-sync doctor          diagnostica completa
icloud-sync skipped         elementi che iCloud non lascia scaricare (--retry per riprovarli)
icloud-sync resync          riallinea da zero senza eliminare nulla
icloud-sync enable|disable|restart   servizio in background e icona
icloud-sync tray            solo l'icona nel vassoio
```

Configurazione in `~/.config/icloud-sync/config.toml` (commentata): cartella, intervalli, esclusioni, limite eliminazioni, flag extra per rclone. Dopo una modifica: `icloud-sync restart`.

## Come funziona

- **Motore**: `rclone bisync LOCALE icloud:` con `--resilient --recover --max-lock 2m --check-access --max-delete 25 --conflict-resolve newer`.
- **Lato locale**: un demone (servizio systemd utente) sorveglia la cartella con inotify, raggruppa le modifiche e lancia bisync.
- **Lato iCloud**: la radice del Drive riporta per ogni cartella un etag che cambia quando cambia qualcosa al suo interno, a qualunque profondità. Il demone la legge ogni `remote_check_interval` secondi (una richiesta, ~0,5 s) e sincronizza solo se è cambiata. Un giro completo di sicurezza parte comunque ogni `poll_interval` secondi.
- **Corsia veloce**: per i file nuovi il demone segue gli etag cambiati, una richiesta per livello, e scarica subito ciò che bisync non conosceva. Non sovrascrive e non elimina: modifiche ed eliminazioni restano a bisync.
- **Errori**: quelli temporanei vengono riprovati con attesa crescente (1 → 15 min); quelli che richiedono te (login, eliminazioni di massa) producono una notifica con il comando da eseguire.
- **Arresto**: il demone ferma rclone con un singolo SIGINT, così lo stato viene salvato correttamente.

## Limiti noti

- Il backend iCloud di rclone è classificato **sperimentale** e usa l'API web non ufficiale di Apple: un cambiamento lato Apple può romperlo finché rclone non si aggiorna (`icloud-sync install-rclone` aggiorna il binario).
- **Cartelle condivise** e **documenti iWork** (Keynote, Pages, Numbers): rclone oggi non riesce a scaricarli (`RootURL not set`, `sizes differ`). Vengono esclusi e restano solo su iCloud; l'elenco è in `icloud-sync skipped`.
- **Tempi dal lato iCloud**: un file nuovo arriva in genere in 20–30 secondi; eliminazioni e modifiche richiedono un giro completo (40–70 secondi); le rinomine non cambiano gli etag e vengono colte dal giro di sicurezza (fino a 5 minuti).
- iCloud non fornisce checksum: il confronto è su dimensione + data di modifica.
- Non è un filesystem "on demand": tutti i file della cartella sincronizzata occupano spazio su disco.
- Nella radice c'è un file nascosto `.icloud-sync-check`: è il file di controllo, non eliminarlo. Se lo cancelli per sbaglio dal PC viene rimesso.
- Il programma parla inglese e italiano, secondo la lingua del sistema.

## Piano di sviluppo

Le priorità seguono l'uso quotidiano: è un piano, non una promessa.

- **0.3, comodità d'uso.** Fatto: finestra di accesso, pausa, registro ed elementi esclusi nel vassoio, notifiche con pulsanti, file di controllo nascosto, messaggi in inglese con l'italiano come traduzione.
- **0.4, lato iCloud più veloce.** Un rclone sempre acceso, che vale 6–7 secondi sulla corsia veloce; eliminazioni e modifiche nella corsia veloce; rinomine rilevate prima.
- **0.5, distribuzione.** Repository APT firmato, per aggiornare con `apt upgrade`; pacchetti RPM e AUR; icona nel vassoio anche con PySide6 (LGPL).
- **0.6, funzioni.** Cestino locale per i file eliminati o sovrascritti da iCloud; sincronizzazione selettiva; più account.

Il piano completo, con le motivazioni e le misure dietro ogni voce, è in [ROADMAP.md](ROADMAP.md).

## Sviluppo

```bash
make test    # test unitari + integrazione (serve rclone: ./icloud-sync install-rclone)
make lint    # controlli statici (serve pyflakes)
make deb     # costruisce dist/icloud-sync_<versione>_all.deb
```

I test di integrazione usano il programma vero e un rclone vero tra due cartelle locali. La pipeline [CI](.github/workflows/ci.yml) li esegue su Python 3.11–3.14, costruisce il pacchetto, lo passa a lintian e lo installa. Per pubblicare una versione: aggiorna `VERSION` nel programma e [CHANGELOG.md](CHANGELOG.md), poi crea il tag `vX.Y.Z`; la pipeline [Release](.github/workflows/release.yml) allega il `.deb` alla release.

Cosa è cambiato in ogni versione: [CHANGELOG.md](CHANGELOG.md).

## Licenza e software di terzi

icloud-sync è distribuito con [licenza MIT](LICENSE): puoi usarlo, modificarlo e ridistribuirlo mantenendo la nota di copyright. È fornito **"così com'è", senza alcuna garanzia**; gli autori non rispondono di danni o perdite di dati.

Si appoggia a software che non include e non ridistribuisce:

| Software | Licenza | Come viene usato |
|---|---|---|
| [rclone](https://rclone.org) | MIT | eseguito come programma esterno; `install-rclone` scarica il binario ufficiale da rclone.org nella tua cartella personale |
| [PyQt6](https://www.riverbankcomputing.com/software/pyqt/) | GPL-3.0 | facoltativo, solo per l'icona nel vassoio; installato dalla tua distribuzione |
| [Qt](https://www.qt.io) | LGPL-3.0 | tramite PyQt6 |
| Libreria standard di Python | PSF-2.0 | tutto il resto |

La licenza MIT è compatibile con la GPL, quindi la combinazione è permessa. Tieni presente che, quando usi l'icona nel vassoio, l'insieme con PyQt6 è regolato dalla GPL-3.0; il resto del programma non carica affatto PyQt6.

Progetto indipendente, non affiliato, approvato o sponsorizzato da Apple Inc. iCloud, iCloud Drive, iPhone e Mac sono marchi di Apple Inc., usati qui solo per indicare con cosa funziona il software.
