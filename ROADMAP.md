# Piano di sviluppo

Questo è un piano, non una promessa: l'ordine riflette ciò che oggi pesa di più nell'uso quotidiano. Le misure citate vengono da prove su un iCloud Drive reale di circa 1200 file e 5 GB (novembre 2026, rclone 1.76).

## Dove siamo (0.2.0)

- Sincronizzazione a due vie affidabile, con protezioni contro le eliminazioni di massa e ripristino automatico.
- PC → iCloud: circa 30 secondi. iCloud → PC: file nuovi in 20–30 secondi, eliminazioni e modifiche in 40–70 secondi, rinomine fino a 5 minuti.
- Icona nel vassoio con stato, apertura cartella e sincronizzazione immediata.
- Pacchetto `.deb` costruito e verificato in pipeline; test automatici su Python 3.11–3.14.

## 0.3 — Comodità d'uso

| Voce | Perché | Note |
|---|---|---|
| Finestra grafica per il login Apple | Il rinnovo ogni 30 giorni oggi richiede il terminale | Da costruire sul flusso `rclone config reconnect`; va provata con un login vero |
| Vassoio: pausa/riprendi, elementi esclusi, log, rinnovo login | Completare ciò che oggi si fa solo da terminale | |
| Notifiche con azione ("Rinnova login", "Mostra file") | Meno passaggi quando serve un intervento | |
| Messaggi in inglese, italiano come traduzione | Il programma oggi parla solo italiano: limita chi può usarlo | gettext; README in inglese |
| Emblema e icona della cartella nel gestore file | Rende visibile che la cartella è sincronizzata | Dolphin e Nautilus |

## 0.4 — Velocità dal lato iCloud

| Voce | Guadagno atteso | Note |
|---|---|---|
| rclone sempre acceso (`rclone rcd`) | 6–7 secondi in meno sulla corsia veloce | Oggi ogni richiesta avvia un rclone che ripercorre il percorso dalla radice (~2 s per livello) |
| Eliminazioni e modifiche nella corsia veloce | Da 40–70 a circa 20 secondi | Richiede regole prudenti: oggi la corsia veloce non elimina e non sovrascrive mai |
| Rinomine rilevate senza aspettare il giro di sicurezza | Da 5 minuti a circa 1 | Le rinomine non cambiano gli etag: serve un altro segnale |
| Canale push web di Apple | Reazione quasi immediata, niente controllo ogni 10 s | Sperimentale: è il meccanismo privato usato da icloud.com, non documentato e fuori da rclone |

## 0.5 — Distribuzione

| Voce | Perché |
|---|---|
| Repository APT firmato (aggiornamenti con `apt upgrade`) | Oggi il `.deb` va riscaricato a mano a ogni versione |
| Pacchetto sorgente Debian (`debian/`, debhelper) | Necessario per PPA e per proporlo a Debian |
| RPM (Fedora, openSUSE) e AUR (Arch) | Il programma è un solo file Python: il lavoro è di impacchettamento |
| Verifica della firma di rclone nell'installatore | Oggi si verifica solo il checksum, scaricato dallo stesso sito |
| `CONTRIBUTING`, `SECURITY`, modelli per le segnalazioni | Per accogliere contributi e bug report |
| Icona nel vassoio anche con PySide6 (LGPL) | Oggi serve PyQt6, che è GPL-3.0: con PySide6 l'intero programma resterebbe sotto licenze permissive |

## 0.6 — Funzioni

| Voce | Note |
|---|---|
| Cestino locale per ciò che arriva eliminato o sovrascritto da iCloud | Rete di sicurezza per N giorni (`--backup-dir` di rclone) |
| Sincronizzazione selettiva | Scegliere quali cartelle tenere sul PC |
| Più coppie cartella/account | Oggi una sola |
| Pausa automatica su rete a consumo o a batteria; limite di banda | |
| File "on demand" (segnaposto scaricati all'apertura) | Grosso: passa da `rclone mount` e cambia il modello del programma |
| Backup di iCloud Foto (sola lettura) | Il backend di rclone lo supporta già |

## Dipendenze a monte e rischi

- **Cartelle condivise e documenti iWork** non sono scaricabili con rclone: vanno seguiti (e segnalati) i relativi problemi nel progetto rclone. Il programma li riprova da solo a ogni aggiornamento di rclone.
- **API non ufficiale**: Apple può cambiarla senza preavviso; finché rclone non si adegua la sincronizzazione si ferma (senza perdere dati).
- **Login ogni 30 giorni**: è un limite di Apple, non aggirabile.
- **Prove contro un account reale**: i test automatici usano due cartelle locali; il comportamento specifico di iCloud (etag, lentezza dopo le modifiche) oggi è verificato solo a mano. Serve un account di prova dedicato per automatizzarlo.

## Da valutare: riscrittura in Rust

Non ora. Il tempo di una sincronizzazione è dominato dalla rete e dai server Apple, non da Python, e la logica sta ancora cambiando: la strategia di rilevamento remoto è stata riscritta tre volte in un giorno, cosa che in un singolo file Python costa poco.

Avrebbe senso quando si verificano queste condizioni:

1. il comportamento è stabile da qualche mese e coperto dai test;
2. si vuole un solo eseguibile senza dipendenze (oggi servono Python e, per l'icona, PyQt6);
3. si decide di fare a meno di rclone parlando direttamente con iCloud.

Il terzo punto è il vero spartiacque: significa reimplementare autenticazione Apple, verifica a due fattori e Protezione avanzata dei dati, cioè la parte fragile che oggi mantiene rclone. Senza quel passo, Rust darebbe soprattutto processi più leggeri: oggi il demone occupa circa 30 MB di memoria e l'icona nel vassoio circa 95 MB (quasi tutti di PyQt6).
