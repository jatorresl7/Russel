# Jarvis

Asistente personal. Backend FastAPI + app Android (Kotlin).

## Requisitos

- Python 3.11+
- PostgreSQL corriendo con DB `jarvis`
- Tailscale activo (para conectar el celular)

## Arrancar

```bash
cd /PROJECTS/PYTHON/claude-automation
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

DB: `postgresql://jarvis:jarvis123@localhost/jarvis`

## App Android

Proyecto en `/PROJECTS/KOTLIN/jarvis-app`. Conecta al backend vía Tailscale (IP del PC: `100.69.89.52:8000`).

## Scripts de trabajo

Los scripts están en `scripts/`. Se gestionan desde la app (toggle + lanzar).

| Script | Descripción |
|--------|-------------|
| logs-aixa.sh | Logs en tiempo real de Aixa |
| send-prexc.sh | Mediport Automation |
| ssh-mediport.sh | SSH a servidor → /opt/aixabot-external-sources/mediport |
| ssh-miia-core2.sh | SSH a servidor → /opt/miia_core2 |
