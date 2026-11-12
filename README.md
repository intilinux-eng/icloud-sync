# icloud-sync

Sincronizzazione **bidirezionale e automatica** di iCloud Drive su Linux.
Una cartella locale (`~/iCloudDrive`) resta allineata con iCloud Drive: quello che cambi sul PC sale in pochi secondi, quello che cambi da iPhone/Mac scende entro qualche minuto.

> Progetto indipendente, non affiliato ad Apple. iCloud è un marchio di Apple Inc.
> Software fornito **senza alcuna garanzia** (licenza MIT): tieni sempre un backup dei dati importanti.

## Perché esiste

Apple non offre un client Linux e iCloud Drive non espone un filesystem né SSH: strumenti come `rsync` o `unison` non possono parlarci direttamente. L'unico motore maturo è [rclone](https://rclone.org/iclouddrive/), che dalla v1.69 ha un backend iCloud Drive nativo, e [`rclone bisync`](https://rclone.org/bisync/) per la sincronizzazione a due vie.

Usare `rclone bisync` a mano però significa scrivere da sé flag, filtri, timer, gestione errori e rinnovo del login. `icloud-sync` è lo strato che manca:

| Problema | Cosa fa icloud-sync |
|---|---|
| iCloud non notifica le modifiche | inotify sul lato locale (reazione in ~5 s) + controllo periodico del remoto (5 min) |
| Un elenco remoto vuoto o errato cancellerebbe tutto | file di controllo su entrambi i lati + blocco oltre il 25% di eliminazioni |
| Stesso file modificato su due dispositivi | vince il più recente, l'altro viene conservato come `nome.conflict1.ext` |
| Stato di bisync corrotto dopo un crash | `--resilient --recover` e ricostruzione automatica (che non elimina mai nulla) |
| Il login Apple scade ogni 30 giorni | promemoria 4 giorni prima, notifica alla scadenza, `icloud-sync login` |
| PC sospeso, rete assente | nessun tentativo offline, ripresa automatica |

## Installazione

Servono Python ≥ 3.11 e systemd (qualsiasi distribuzione recente). Nessun pacchetto Python da installare.

```bash
python3 icloud-sync setup
```

La procedura guidata installa rclone se manca (binario ufficiale, checksum verificato, in `~/.local/bin`), chiede Apple ID, password e codice a due fattori, esegue la prima sincronizzazione e attiva il servizio in background.

Note sul login:

- serve la password normale dell'Apple ID (Apple non accetta qui le "password per app"); viene salvata offuscata nella configurazione locale di rclone;
- con la **Protezione avanzata dei dati** attiva, abilita prima *Accedi ai dati iCloud sul web* su iPhone (Impostazioni → account → iCloud).

## Uso

```text
icloud-sync status          stato, ultima sync, giorni rimasti al login
icloud-sync sync            sincronizza subito (--dry-run per l'anteprima)
icloud-sync login           rinnova il login Apple (circa ogni 30 giorni)
icloud-sync log             ultime operazioni (--error: log rclone dell'ultimo errore)
icloud-sync doctor          diagnostica completa
icloud-sync resync          riallinea da zero senza eliminare nulla
icloud-sync enable|disable|restart   gestione del servizio
```

Configurazione in `~/.config/icloud-sync/config.toml` (commentata): cartella, intervalli, esclusioni, limite eliminazioni, flag extra per rclone. Dopo una modifica: `icloud-sync restart`.

## Come funziona

- Motore: `rclone bisync LOCALE icloud:` con `--resilient --recover --max-lock 2m --check-access --max-delete 25 --conflict-resolve newer`.
- Un demone (servizio systemd utente) sorveglia la cartella con inotify, raggruppa le modifiche e lancia bisync; in assenza di modifiche locali controlla il remoto ogni `poll_interval` secondi.
- Errori temporanei: nuovo tentativo con attesa crescente (1 → 15 min). Errori che richiedono te (login, troppe eliminazioni): notifica desktop con il comando da eseguire.
- All'arresto il demone ferma rclone con un singolo SIGINT, così lo stato viene salvato correttamente.

## Limiti noti

- Il backend iCloud di rclone è classificato **sperimentale** e usa l'API web non ufficiale di Apple: un cambiamento lato Apple può romperlo finché rclone non si aggiorna (`icloud-sync install-rclone` aggiorna il binario).
- iCloud non fornisce checksum: il confronto è su dimensione + data di modifica.
- Ogni controllo elenca l'intero Drive: con decine di migliaia di file un ciclo dura minuti. Sincronizzare una sottocartella (`remote = "icloud:Documenti"`) lo rende molto più rapido.
- Le modifiche remote arrivano con il ritardo del polling (default 5 minuti).
- Non è un filesystem "on demand": tutti i file della cartella sincronizzata occupano spazio su disco.
- Nella radice compare un file `RCLONE_TEST`: è il file di controllo, non eliminarlo.

## Licenza

MIT — vedi [LICENSE](LICENSE).
