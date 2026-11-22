# Changelog

Le versioni seguono [Semantic Versioning](https://semver.org/lang/it/). Finché siamo a 0.x, configurazione e comandi possono ancora cambiare.

## 0.3.0

### Aggiunto

- Emblemi di stato sui file in Dolphin (spunta verde, frecce, conflitto, non sincronizzabile): plugin C++ nella cartella `dolphin/`, da compilare e installare a parte. Collaudato con un test automatico e verificato in Dolphin.
- Messaggi in inglese, con l'italiano come traduzione: la lingua segue quella del sistema (`LANGUAGE`, `LC_ALL`, `LC_MESSAGES`, `LANG`). Un test garantisce che nessun messaggio resti senza traduzione.
- Finestra grafica per l'accesso Apple (`icloud-sync login --gui`, o dal vassoio): Apple ID, password e codice a due fattori senza terminale. Provata contro un rclone simulato; non ancora contro un vero rinnovo con Apple.
- Vassoio: *Metti in pausa / Riprendi*, *Elementi esclusi* con «Riprova tutti», *Registro attività*, *Rinnova accesso Apple* con i giorni rimasti.
- Comandi `pause` e `resume`: la pausa sopravvive al riavvio e alla ripresa si recupera tutto ciò che è cambiato.
- Notifiche con pulsanti: *Rinnova accesso* quando il login scade o viene rifiutato, *Mostra* sui nuovi file arrivati da iCloud, *Apri cartella* sui conflitti.
- Icona a nuvola sulla cartella sincronizzata in Dolphin.
- File di controllo nascosto `.icloud-sync-check` al posto di `RCLONE_TEST`, convertito automaticamente alla prima sincronizzazione. Un altro PC rimasto alla 0.2 va aggiornato, altrimenti si blocca segnalando il file di controllo mancante.

### Cambiato

- Se il file di controllo viene eliminato per sbaglio dalla cartella locale, viene ripristinato da iCloud invece di bloccare la sincronizzazione (solo se la cartella contiene ancora almeno metà dei file noti).
- Un errore passeggero (per esempio una cartella eliminata mentre la sincronizzazione la stava leggendo) non genera più una notifica: viene riprovato in silenzio e segnalato solo se si ripete.
- README in inglese come pagina di presentazione, con nota sull'uso quotidiano e sintesi del piano di sviluppo; la versione italiana è in `README.it.md`.
- README: per cartelle condivise e documenti iWork, i riferimenti ai problemi aperti nel progetto rclone e una soluzione temporanea.
- Licenze: intestazioni SPDX nei sorgenti, elenco del software di terzi, avviso di assenza di garanzia nel README, nella guida in linea, nella procedura `setup` e nella pagina man.

## 0.2.0

### Aggiunto

- Icona nel vassoio di sistema (`icloud-sync tray`, avviata da `enable`): stato a colpo d'occhio, *Apri cartella iCloud Drive*, *Sincronizza ora*.
- Rilevamento rapido delle modifiche su iCloud: controllo leggero della radice ogni 10 secondi (`remote_check_interval`) al posto del solo polling ogni 5 minuti.
- Corsia veloce: i file nuovi comparsi su iCloud vengono scaricati subito seguendo gli etag delle cartelle, con notifica (`notify_downloads`).
- Esclusione automatica degli elementi che rclone non riesce a scaricare (cartelle condivise, documenti iWork) e comando `skipped`.
- Pacchetto Debian (`make deb`), pagina man, voce di menu, unità systemd di sistema.
- Suite di test (unitari e di integrazione) e pipeline GitHub Actions per test, pacchetto e release.

### Cambiato

- Poche eliminazioni non vengono più bloccate dalla soglia in percentuale (`max_delete_min_files`, predefinito 10): prima eliminare 1 file su 3 fermava la sincronizzazione.
- Se un lato risulta completamente vuoto la sincronizzazione si ferma con un messaggio chiaro, senza tentare ricostruzioni automatiche.
- Il limite di frequenza della ricostruzione automatica vale solo dopo una ricostruzione riuscita.
- Un arresto del servizio durante una sincronizzazione non viene più registrato come errore.

## 0.1.0

- Prima versione: sincronizzazione bidirezionale con `rclone bisync`, demone con inotify, protezioni (file di controllo, limite eliminazioni), ripristino automatico, promemoria del login Apple, servizio systemd utente.
