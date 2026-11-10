# Projekt 3: Fan Chat AI — Automatisierte Chat-Betreuung für Erotikmodels

## Vision
Eine KI die im Namen von Amateur-Erotikmodels die Fan-Chats auf allen Portalen betreut. Lernt den Schreibstil des Models, sammelt Fan-Informationen und pflegt Kontakte autonom.

## Kernfunktionen
- **Chat-Analyse:** Liest bisherige Chats und lernt den Schreibstil des Models
- **Fan-Datenbank:** Pro Fan eine separate Datenbank mit Infos (Name, Vorlieben, Kaufhistorie, letzter Kontakt)
- **Model-Datenbank:** Infos über das Model (Persönlichkeit, Vorlieben, Grenzen, Preise)
- **Automatische Antworten:** Antwortet stellvertretend im Namen des Models
- **Proaktive Kontaktpflege:** Schreibt Fans in regelmäßigen Abständen an (Geburtstag, neue Content, etc.)
- **Eskalation:** Leitet komplexe/wichtige Chats an das Model weiter
- **Tonalität:** Passt sich dem Schreibstil des Models an (Slang, Emojis, Formalität)

## Zielgruppe
Amateur-Erotikmodels, Content Creator, Agenturen

## Technische Anforderungen
- LLM-basierte Chat-Automation (Claude/GPT)
- RAG (Retrieval Augmented Generation) mit Fan- und Model-Daten
- WebSocket-Integration mit Portal-Chats
- Verschlüsselte Datenbank (DSGVO)
- Dashboard für das Model (Übersicht, Eskalationen, Statistiken)

## Monetarisierung
- Monatliches Abo pro Model
- Enterprise für Agenturen (mehrere Models)

---

# Umsetzung (v0.2, MVP + S3)

**Prinzip: Assistenz statt Täuschung.** Die KI schreibt Entwürfe im Stil der Creatorin. Gesendet wird nur,
was sie selbst freigibt, und jede KI-unterstützte Nachricht trägt einen sichtbaren Hinweis
(`AI_DISCLOSURE`, EU AI Act Art. 50). Fragen wie "Bist du ein Bot?", Treffen, Adressen, Grenzthemen und Top-Fans
werden eskaliert: Dafür erzeugt die KI keinen Text, die Creatorin antwortet selbst.

| Blueprint-Funktion | Umsetzung |
|---|---|
| Chat-Analyse / Tonalität | `POST /profile/learn-style`: Statistik aus eigenen Nachrichten (Länge, Emojis, Anrede, Wörter, Beispiele) |
| Fan-Datenbank | `/fans` (+ Käufe, Verlauf, Geburtstag, Kontaktsperre); sensible Felder verschlüsselt (Fernet) |
| Model-Datenbank | `/profile` (Persona, Grenzen, Preise, Eskalations-Stichwörter, Top-Fan-Schwelle) |
| Antworten | eingehende Nachricht → Entwurf (RAG aus Profil, Fan, Verlauf, Käufen) → `/drafts/{id}/decision` → `/send` |
| Kontaktpflege | `POST /outreach/generate`: Entwürfe zu Geburtstagen und Funkstille, keine Duplikate |
| Eskalation | `app/services/rules.py` |
| Dashboard | `/stats` |
| Portale | Adapter-Interface, nur offizielle Wege; `manual` liefert Text zum Kopieren. Eingang: `POST /inbox/events` (Connector, authentifiziert) oder `POST /webhooks/{tenant_id}` (HMAC-SHA256 über den Body, Secret via `POST /profile/webhook-secret`); beides exactly-once über die `webhook_inbox` (UNIQUE event_id, Duplikat → 200 + `duplicate: true`) |
| Chat-Import | `POST /fans/import`: exportierte Verläufe je Portal/Fan, ohne Entwürfe; setzt letzten Kontakt, lernt Fakten |
| Langzeitgedächtnis | `memory_facts` je Fan (Text PII-redaktiert und verschlüsselt; im Klartext nur Lexeme des tsvector + Embedding; Fakten mit Injektionsmustern werden verworfen): automatisch aus Fan-Nachrichten extrahiert + manuell (`/fans/{id}/facts`); hybride Suche tsvector (german) + Embedding-Port (Hashing-Fake) mit Reciprocal Rank Fusion (k=60), `GET /fans/{id}/facts?q=` |
| PII-Redaktion | `app/services/pii.py`: E-Mail, Telefon, IBAN, Kartennummer (Luhn) → Platzhalter, vor Index und Prompt |
| Guardrails | `app/services/guardrails.py`: Input-Rail (Injektionsmuster in Nachricht/Nickname → Eskalation), Fan-Daten im Prompt als `<untrusted>` markiert; Output-Rail (Link, „bin kein Bot“, Gratis, Kontaktdaten/Plattformwechsel → Entwurf blockiert, Creatorin schreibt selbst) |
| Statistiken | `/stats` zusätzlich je Portal: Fans, Umsatz, Nachrichten ein/aus |

Sicherheit: Multi-Tenant mit PostgreSQL FORCE RLS, App-Rolle ohne SUPERUSER/BYPASSRLS, Argon2id, JWT mit Widerruf,
nur die Creatorin (Rolle owner) darf freigeben, Audit-Log, Löschen eines Fans entfernt alles (DSGVO).

```bash
python -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env && .venv/bin/alembic upgrade head
.venv/bin/uvicorn app.api.main:app --reload
LLM_PROVIDER=fake .venv/bin/pytest -q      # 24 Tests
```

Abweichungen zur Spezifikation (bewusst, MVP): kein pgvector/HNSW (Embedding als JSONB + Cosine in Python, Port austauschbar),
kein Cross-Encoder-Reranking, keine Redis-Locks (Idempotenz über DB-UNIQUE), kein LangGraph (Draft→Decision→Send ist die State-Machine),
Discord-Sharding/Telegram-Local-API nicht enthalten. Alles davon hinter Ports, siehe `nexussaas/projects/03-fan-chat-ai.md`.

Offen: Web-Dashboard, konkrete Portal-Connectoren (nur offizielle APIs), echtes Embedding-Modell + Reranker.
