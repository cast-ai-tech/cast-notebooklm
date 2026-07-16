# SETUP-ALEXANDER.md

Notas de setup personales de Alexander Cast. Este proyecto está escrito pa' que lo pueda instalar cualquiera (ver README.md, la versión genérica) — este archivo es el "cómo lo corro yo" con la regla de la cuenta secundaria.

## ⚠️ Regla de cuenta

**Autenticate con una cuenta de Google secundaria/de prueba, nunca con la principal.** Este proyecto habla directo con la API interna no documentada de NotebookLM, y Google puede rotarla o restringirla sin aviso. Mantenela aislada de `founder@kreoon.com` o cualquier cuenta atada a datos reales de KREOON/Infiny.

## 1. Instalar

Requiere Python 3.11+.

```bash
cd ruta/a/cast-notebooklm
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

pip install -e .
```

Verificar:

```bash
nlm --help
```

## 2. Autenticar (cuenta secundaria)

```bash
nlm login
```

Esto abre una ventana de Chrome (Chrome DevTools Protocol) — logueate con la cuenta **secundaria** de Google cuando te lo pida. Las credenciales se extraen solo como cookies (sin contraseña guardada) y quedan escritas **cifradas en reposo** (AES-256-GCM) en `~/.notebooklm-mcp-cli/` — ver "Clave de cifrado" abajo.

Para una segunda cuenta (multi-cuenta), usá un perfil nombrado:

```bash
nlm login --profile trabajo
nlm login switch trabajo    # la deja como perfil activo para CLI/MCP
```

## 3. Clave de cifrado

La primera vez que se guardan credenciales, se genera una clave automáticamente en `~/.notebooklm-mcp-cli/encryption.key` (permisos `0o600`) y se imprime una advertencia. **Hacé backup de ese archivo** — perderlo hace que las credenciales cifradas existentes queden irrecuperables (solo implica volver a correr `nlm login`, sin pérdida de datos más allá de re-autenticarte).

Para fijar la clave explícitamente en vez de auto-generarla (ej. pa' compartirla entre máquinas, o setearla vía un gestor de secretos):

```bash
export CAST_NLM_ENCRYPTION_KEY=$(python -c "import secrets; print(secrets.token_hex(32))")
```

## 4. Corriendo cada modo

### CLI

```bash
nlm notebook list
nlm chat query --notebook-id <id> --query "..."
```

### Servidor MCP (para Claude Desktop, Cursor, etc.)

stdio (default, para configs de apps de escritorio):

```bash
notebooklm-mcp
```

HTTP (para acceso por red):

```bash
notebooklm-mcp --transport http --port 8000
```

Opcional: restringir qué herramientas ve el agente host (ahorra contexto) con un perfil nombrado:

```bash
CAST_NLM_PROFILE=minimal notebooklm-mcp     # solo lectura + chat + health
CAST_NLM_PROFILE=standard notebooklm-mcp    # + gestión de contenido/notebooks/fuentes, auth, labels
# sin setear, o CAST_NLM_PROFILE=full       # todo (default, comportamiento sin cambios)
```

### API REST (para n8n / Zapier / Make)

Requiere al menos una API key configurada — el servidor se rehúsa a arrancar sin ella:

```bash
export CAST_NLM_API_KEYS=$(python -c "import secrets; print(secrets.token_urlsafe(32))")
cast-notebooklm-api
```

Default en `127.0.0.1:8008` (sobreescribible con `CAST_NLM_API_HOST` / `CAST_NLM_API_PORT`). Cada request necesita el header `X-API-Key: <una de las keys configuradas>`. Docs interactivos en `http://127.0.0.1:8008/docs`.

Ejemplo de llamada:

```bash
curl -X POST http://127.0.0.1:8008/chat/ask \
  -H "X-API-Key: $CAST_NLM_API_KEYS" \
  -H "Content-Type: application/json" \
  -d '{"notebook_id": "<id>", "question": "Resume este notebook."}'
```

Multi-cuenta: pasá `"profile": "trabajo"` en cualquier body (o `?profile=trabajo` en las rutas GET) para usar una cuenta específica de `nlm login --profile` en vez de `default`.

Cada respuesta de `/chat/ask` incluye un campo `_provenance` y el texto de la respuesta viene con el prefijo `[AI-GENERATED ...]` — es intencional (etiquetado anti-inyección-de-prompts, ver CREDITS.md §3). Para desactivar solo el prefijo de texto inline (el campo `_provenance` siempre queda): `CAST_NLM_AI_MARKER=false`.

## 5. Cosas a tener en cuenta

- `nlm doctor` y la migración legacy (`utils/config.py::run_migration`) todavía pueden encontrar credenciales en **texto plano** de una instalación vieja de la herramienta `notebooklm-mcp-cli` original (previa a este fork). Si pasa eso, la carga de credenciales falla con gracia y loguea una advertencia — solo hay que correr `nlm login` de nuevo.
- Un test pre-existente (`tests/test_cdp_port_map.py::test_mapped_chrome_owns_profile_matches_user_data_dir_flag`) falla en esta máquina Windows, independiente de todo lo construido acá — está sin modificar respecto al repo base de jacob-bd.
- El endpoint `/health` de MCP reporta `"version":"0.8.7"` (el string de versión del proyecto base jacob-bd) en vez de la versión propia de cast-notebooklm — cosmético, no conectado, inofensivo.
