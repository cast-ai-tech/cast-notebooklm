# Créditos

cast-notebooklm es una unificación personal e interna de ideas y código de tres proyectos open source con licencia MIT que dan acceso programático a Google NotebookLM. **No** es un fork publicado de ninguno de los tres — es un proyecto nuevo, bajo copyright propio, que vendoriza código de uno de los tres y reimplementa de forma independiente ideas de diseño aprendidas de los otros dos. A continuación, atribución completa a los tres, como exige la licencia MIT.

## 1. Base: jacob-bd/notebooklm-mcp-cli

- **Repositorio:** https://github.com/jacob-bd/notebooklm-mcp-cli
- **Autor:** Jacob Ben-David
- **Licencia:** MIT, Copyright (c) 2025 Jacob Ben-David (texto completo: `LICENSE-jacob-bd`)

`src/notebooklm_tools/` en este repositorio es una copia del árbol de código de este proyecto (CLI, servidor MCP, y las capas `core`/`services` debajo de ambos), usada como base sobre la que se construye cast-notebooklm. Es el único de los tres proyectos fuente cuyo código se vendoriza acá directamente en vez de reimplementarse; su `LICENSE` se preserva sin modificar como `LICENSE-jacob-bd`, según lo exige la licencia MIT.

Qué aporta jacob-bd/notebooklm-mcp-cli: un cliente Python que habla directo con la API interna `batchexecute` de NotebookLM por HTTP (vía `httpx`), autenticando con cookies extraídas vía Chrome DevTools Protocol (sin automatización de clics); un CLI `nlm` (Typer); un servidor MCP (FastMCP); y soporte completo de Studio (audio, video, infografía, presentación, tabla de datos, reporte, flashcards, quiz, mapa mental), research, batch, y operaciones cross-notebook.

## 2. Diseño de API REST, cifrado y multi-cuenta: roomi-fields/notebooklm-mcp

- **Repositorio:** https://github.com/roomi-fields/notebooklm-mcp
- **Autor:** Romain Peyrichou (@roomi-fields)
- **Licencia:** MIT, Copyright (c) 2025 Romain Peyrichou (wrapper de API REST HTTP);
  Copyright (c) 2025 Please Prompto! (servidor MCP original de NotebookLM del cual este proyecto es fork)

Es un fork en TypeScript de PleasePrompto/notebooklm-mcp (ver abajo). Su código propio **no** está vendorizado acá — el paquete `rest_api/` de cast-notebooklm y las adiciones de cifrado/multi-cuenta a `src/notebooklm_tools/core/` son una reimplementación independiente en Python, informada por el estudio del diseño de este proyecto:

- **Forma de la API REST** (`rest_api/routers/`, `rest_api/main.py`): una capa de transporte HTTP delgada sobre las mismas funciones de servicio que ya llaman el CLI/MCP, siguiendo las convenciones de endpoints y de envelope de respuesta de este proyecto (`{"success": bool, "data"/"error": ...}`).
- **Cifrado de credenciales en reposo** (`src/notebooklm_tools/core/crypto.py`): mismo enfoque AES-256-GCM y jerarquía de resolución de clave (env var → archivo de clave → clave generada y persistida) que `src/accounts/crypto.ts` de este proyecto. El largo del nonce difiere (12 bytes acá vs. 16 ahí) — ver el docstring del módulo `core/crypto.py` para el porqué.
- **Pool de clientes multi-cuenta** (`rest_api/client_pool.py`): informado por el modelo de aislamiento de credenciales/sesión por cuenta de este proyecto, adaptado al sistema `AuthManager` de perfiles ya existente en jacob-bd en vez de construir un almacén de cuentas paralelo.

cast-notebooklm también mejora a este proyecto en un aspecto notado durante la revisión: su wrapper HTTP en Express no tiene autenticación alguna (bindea `0.0.0.0` con CORS abierto). `rest_api/deps.py` agrega un chequeo de API key obligatorio que ese proyecto no tiene.

## 3. Marcador de provenance y perfiles de herramientas: PleasePrompto/notebooklm-mcp

- **Repositorio:** https://github.com/PleasePrompto/notebooklm-mcp
- **Autor:** Gérôme Dexheimer ("Please Prompto!")
- **Licencia:** MIT, Copyright (c) 2025 Please Prompto!

El servidor MCP original de NotebookLM (roomi-fields, arriba, es un fork de este). Su código propio **no** está vendorizado acá — lo siguiente son reimplementaciones independientes en Python de ideas de este proyecto:

- **Marcador de provenance / contenido no confiable generado por IA**
  (`src/notebooklm_tools/services/provenance.py`): el mismo diseño de dos partes que `src/utils/disclaimer.ts` de este proyecto — un campo de metadata `_provenance` adjunto junto a `answer` (sin envolverlo), más un prefijo de texto inline `[AI-GENERATED ...]` en la respuesta misma, para que el marcador sobreviva aunque quien llama solo lea el string de respuesta crudo. Aplicado en `services/chat.py::query()`, el único punto que comparten los tres transportes (CLI, MCP, REST).
- **Perfiles nombrados de visibilidad de herramientas MCP** (`src/notebooklm_tools/mcp/profiles.py`):
  los mismos nombres de perfil `minimal`/`standard`/`full` y selección por env var que `src/utils/settings-manager.ts` de este proyecto, construidos sobre el gating de herramientas por grupo ya existente en jacob-bd (`mcp/tool_groups.py`) en vez de reimplementar el filtrado por herramienta desde cero.

## Nota de cumplimiento de licencia

Según la licencia MIT, deben preservarse los avisos de copyright y permiso de cada uno de los tres proyectos. El de jacob-bd se preserva vía `LICENSE-jacob-bd` (su código está vendorizado textualmente bajo `src/notebooklm_tools/`). El código de roomi-fields y PleasePrompto no está copiado acá — solo ideas de diseño, reimplementadas de forma independiente en Python — pero ambos están acreditados arriba en su totalidad como buena práctica, más allá de lo que exige estrictamente MIT para trabajo no copiado.
