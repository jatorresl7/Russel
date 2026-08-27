# Skill: Add Work Script

Cuando el usuario invoque este skill, crea el archivo `.sh` en `scripts/` y lo registra en la DB vía la API.

## Proceso completo

### 1. Crear el archivo del script
Crear en `/PROJECTS/PYTHON/claude-automation/scripts/<filename>.sh` con el comando que va dentro del tab (sin gnome-terminal).

```bash
chmod 700 /PROJECTS/PYTHON/claude-automation/scripts/<filename>.sh
```

### 2. Registrar en la DB vía API
```bash
curl -s -X POST http://localhost:8000/api/work-scripts \
  -H "Content-Type: application/json" \
  -d '{"name":"<name>","title":"<title>","filename":"<filename>.sh","enabled":true,"order":<order>}'
```

- `name`: identificador corto (ej: `mediport`)
- `title`: texto que aparece en la app (ej: `Mediport`)
- `filename`: nombre del archivo en `scripts/`
- `order`: posición en la lista (revisar los existentes con `/db` o `GET /work-scripts`)

### 3. Verificar
```bash
curl -s http://localhost:8000/api/work-scripts | python3 -m json.tool
```

## Ver order de scripts existentes
```bash
psql postgresql://jarvis:jarvis123@localhost/jarvis -c "SELECT id, name, title, filename, enabled, \"order\" FROM work_scripts ORDER BY \"order\";"
```
