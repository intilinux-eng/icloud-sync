# Changelog

Le versioni seguono [Semantic Versioning](https://semver.org/lang/it/). Finché siamo a 0.x, configurazione e comandi possono ancora cambiare.

## Non ancora rilasciato

- README in inglese come pagina di presentazione; la versione italiana è in `README.it.md`.
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
