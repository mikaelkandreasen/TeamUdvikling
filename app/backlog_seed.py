"""Startliste til backloggen i Administration (kan redigeres frit i appen). (prioritet, titel, beskrivelse)"""
SEED = [
    (0, "Verificér Docker-build og Dockhand-deploy", "Containeren starter, /healthz svarer, data overlever redeploy."),
    (0, "HTTPS bag reverse proxy", "Vejledning og test med COOKIE_SECURE=1 og TRUSTED_PROXIES=1."),
    (0, "Første rigtige gennemløb med trænere", "1 hold, 2 trænere, 1 evalueringsrunde, motivationsskema på tablet. Notér friktionspunkter."),
    (0, "Backup-restore afprøvet", "Test scripts/restore.sh mod en rigtig backup; beskriv kopi uden for serveren."),
    (1, "Øvelsesbank med forslag til udviklingsområder", "Øvelser tagget med rolle × nøglefærdighed; forslag på spillerprofil og en fælles fokusside for holdet."),
    (1, "DBU KampKlar-integration (afventer valg)", "Ingen officiel API. Muligheder: iCal, uofficiel scraper eller manuel import. Vurder børnedata og DBU's vilkår."),
    (1, "Ekstern pentest/scan af udrullet system", "OWASP ZAP/nuclei mod HTTPS-adressen, før den åbnes på internettet."),
    (1, "Opbevaringstid pr. spiller", "deactivated_at og automatisk sletning efter aftalt frist."),
    (2, "Kryptering af TOTP-hemmeligheder i hvile", "Envelope-kryptering med nøgle uden for databasen."),
    (2, "Forældrerapport som PDF", "Samlet, venlig rapport pr. spiller til udlevering."),
    (3, "Kamp- og træningskalender", "Fremmøde pr. aktivitet i stedet for samlede tal."),
]
