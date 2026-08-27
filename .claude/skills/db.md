# Skill: Jarvis DB Manager

Cuando el usuario invoque este skill, usá psql para inspeccionar o modificar la base de datos `jarvis`.

## Conexión
```
psql postgresql://jarvis:jarvis123@localhost/jarvis
```

## Comandos útiles

### Ver tablas
```bash
psql postgresql://jarvis:jarvis123@localhost/jarvis -c "\dt"
```

### Ver resúmenes de Gmail
```bash
psql postgresql://jarvis:jarvis123@localhost/jarvis -c "SELECT date, email_count, LEFT(summary, 100) FROM gmail_summaries ORDER BY date DESC LIMIT 10;"
```

### Ver historial de conversaciones
```bash
psql postgresql://jarvis:jarvis123@localhost/jarvis -c "SELECT role, LEFT(content, 80), created_at FROM conversations ORDER BY created_at DESC LIMIT 20;"
```

### Ver tools registradas
```bash
psql postgresql://jarvis:jarvis123@localhost/jarvis -c "SELECT id, name, description, command, enabled FROM tools;"
```

### Ver ejecuciones de scripts
```bash
psql postgresql://jarvis:jarvis123@localhost/jarvis -c "SELECT sr.id, t.name, sr.status, sr.created_at FROM script_runs sr JOIN tools t ON t.id = sr.tool_id ORDER BY sr.created_at DESC LIMIT 10;"
```

### Agregar una tool desde CLI
```bash
psql postgresql://jarvis:jarvis123@localhost/jarvis -c "INSERT INTO tools (name, description, command, enabled) VALUES ('nombre', 'descripcion', 'python script.py', true);"
```

### Limpiar historial de chat
```bash
psql postgresql://jarvis:jarvis123@localhost/jarvis -c "DELETE FROM conversations WHERE created_at < NOW() - INTERVAL '30 days';"
```
