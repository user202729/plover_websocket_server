# Plover WebSocket Server

[![PyPI](https://img.shields.io/pypi/v/plover-engine-server-2?style=flat)](https://pypi.python.org/pypi/plover-engine-server-2/)

A WebSocket server plugin for [Plover](https://github.com/openstenoproject/plover) that
exposes real-time steno events, dictionary lookups, and engine control to external programs.

This plugin is available on [GitHub](https://github.com/user202729/plover_websocket_server)
and [PyPI](https://pypi.org/project/plover-engine-server-2/) (under the name `plover-engine-server-2`).
Report all bugs on GitHub.

## Installation

Download the latest version of Plover for your operating system from the [releases page](https://github.com/openstenoproject/plover/releases). Only versions 4.0.0.dev8 and higher are supported.

### From the Plugin Manager

1. Open Plover
2. Navigate to the Plugin Manager tool
3. Select the "plover-engine-server-2" plugin entry in the list
4. Click install
5. Restart Plover

The same method can be used for updating and uninstalling the plugin.

### From the CLI

You can also install the plugin using the Plover CLI:

```bash
plover -s plover_plugins install plover-engine-server-2
```

For development, install in editable mode from a local checkout:

```bash
cd plover_websocket_server
plover -s plover_plugins install -e .
```

## Configuration

A default configuration file named `plover_engine_server_config.json` is automatically
created inside Plover's configuration directory (same directory as `plover.cfg`) when the
plugin starts for the first time.

The default configuration is:

```json
{
  "host": "localhost",
  "port": 8086,
  "secretkey": "",
  "ssl": {
    "cert_path": "",
    "key_path": ""
  }
}
```

All fields are optional. Leave `secretkey` empty to disable authentication.

### SSL / TLS

By default the server runs unencrypted (`ws://`). If you provide paths to an SSL certificate
and private key, the server will use TLS and serve over `wss://` instead. This encrypts all
traffic between your client and Plover, which matters if you're connecting from another machine
on your network or exposing the server beyond localhost.

To enable SSL, set both `cert_path` and `key_path` to absolute paths pointing to your
PEM-encoded certificate and private key files:

```json
{
  "ssl": {
    "cert_path": "/home/you/.certs/plover.crt",
    "key_path": "/home/you/.certs/plover.key"
  }
}
```

Both fields must be set for SSL to take effect. If either is empty or missing, SSL is disabled
and the server falls back to plain `ws://`.

You can generate a self-signed certificate for local/development use with:

```bash
openssl req -x509 -newkey rsa:2048 -keyout plover.key -out plover.crt -days 365 -nodes
```

For production or cross-machine use, consider a certificate from
[Let's Encrypt](https://letsencrypt.org/) or your organization's CA.

## How to Use

1. Enable the extension in Plover under Configure > Plugins
2. The server starts automatically on `ws://localhost:8086`
3. Connect a WebSocket client to `ws://localhost:8086/websocket` (or `wss://` if SSL
   is configured)

If you have set a `secretkey`, include it in the `X-Secret-Token` header when connecting.

A standalone web demo is included in `web_demo/index.html`. Open it in a browser to
test the connection and explore the protocol interactively.

## Protocol

All communication happens over a single WebSocket connection using JSON messages. There are
three kinds of messages:

- **Events**: The server pushes these to every connected client when something happens in
  Plover (a stroke, a translation, output toggling, etc.). Your client just listens for them.
- **Actions**: Your client sends these to tell Plover to do something (inject a stroke,
  toggle output, add a dictionary entry). Actions do not produce a direct response, but they
  may trigger broadcast events as a side effect.
- **Queries**: Your client sends these to request information (dictionary lookups, engine
  state). The server responds only to the requesting client, not to all clients.

Sending the raw text `close` (not JSON) disconnects you.

### Connecting and Initial State

After opening the WebSocket connection, you will typically want to query for the current
engine state so your client can display accurate information from the start:

```json
{"id": "1", "get_machine_state": true, "get_output": true, "get_dictionaries": true}
```

This returns the machine type and connection state, whether steno output is enabled, and
the list of loaded dictionaries, all in a single round trip.

From that point on, listen for events to keep your state up to date. The `output_changed`,
`machine_state_changed`, and `dictionaries_loaded` events will tell you when those values
change.

### Message Ordering

When Plover processes a stroke, the server sends output events (`send_string`,
`send_backspaces`, `send_key_combination`) *before* the corresponding `stroked` event.
If you are building a stroke display, buffer any output events and attach them to the
next `stroked` event that arrives.

### Matching Query Responses

Include an `"id"` field in any message that contains queries. The server echoes that `id`
back in the response so you can match it to the original request. If you omit the `id`,
the response is still sent but you will have no way to correlate it. Multiple queries can
be combined in a single message and they will share the same `id` in the response.

### Events (server to client)

Events are broadcast to all connected clients whenever something happens in Plover.

| Key | Value | Fires when |
|-----|-------|------------|
| `stroked` | `{...stroke object, "rtfcre": "TEFT"}` | A stroke is performed |
| `translated` | `{"old": [...], "new": [...]}` | A translation occurs |
| `machine_state_changed` | `{"machine_type": "...", "machine_state": "..."}` | Machine connection changes |
| `output_changed` | `true/false` | Steno output is toggled |
| `config_changed` | `{...config object}` | Configuration is modified |
| `dictionaries_loaded` | `true` | All dictionaries finish loading |
| `dictionary_state_changed` | `{"path": "...", "enabled": bool, "errored": bool}` | A single dictionary's state changes |
| `send_string` | `"text"` | A string is sent to the OS |
| `send_backspaces` | `5` | Backspaces are sent to the OS |
| `send_key_combination` | `"Alt_L(Tab)"` | A key combination is sent |
| `add_translation` | `true` | The Add Translation tool opens |
| `focus` | `true` | The main window is focused |
| `configure` | `true` | The configuration window opens |
| `lookup` | `true` | The lookup tool opens |
| `suggestions` | `true` | The suggestions tool opens |
| `quit` | `true` | Plover is quitting |

### Actions (client to server)

Actions tell Plover to do something. They do not return a response (but may
trigger broadcast events like `output_changed`).

**Inject a stroke:**

```json
{"stroke": ["S-", "T-"]}
```

The stroke is processed through the translation engine exactly as if it came from a steno
machine, but no keystrokes are emitted to the OS. WebSocket events (like `stroked` and
`send_string`) still fire, so other clients can observe the stroke. Invalid steno keys are
silently dropped.

**Inject a translation or macro:**

```json
{"translation": "hello"}
{"translation": "{PLOVER:TOGGLE}"}
```

Sends a translation string or Plover command directly into the engine, bypassing stroke
lookup. Like injected strokes, this fires events without emitting OS keystrokes.

**Toggle or set steno output:**

```json
{"toggle_output": true}
{"set_output": false}
```

**Add a dictionary entry:**

```json
{"add_translation": {"strokes": ["TEFT"], "translation": "test"}}
{"add_translation": {"strokes": ["TEFT"], "translation": "test", "dictionary_path": "/path/to/dict.json"}}
```

If `dictionary_path` is omitted, the entry is added to the first writable dictionary.

**Clear the translator state:**

```json
{"clear_translator_state": false}
```

Pass `true` to also undo all previous translations on the stack (sends backspaces),
or `false` to just reset without undoing.

**Force execution when the engine is off:**

By default, actions are ignored when steno output is disabled. Set `"forced": true` on
any action message to execute it regardless. To prevent character deletion when resuming
with the Keyboard machine, also set `"zero_last_stroke_length": true`.

```json
{"stroke": ["S-", "T-"], "forced": true, "zero_last_stroke_length": true}
```

### Queries (client to server to client)

Queries let you request information from the engine. The response is sent back to
only the requesting client (not broadcast). Include an `"id"` field to match
responses to requests.

#### Dictionary Lookups

There are several ways to search the dictionaries depending on what you have and what
you need.

**Stroke to translation** (`lookup`): Given an outline, returns the translation Plover
would produce. Returns `null` if the outline is not defined in any active dictionary.

```json
{"id": "1", "lookup": ["TEFT"]}
```
Response: `{"id": "1", "lookup": "test"}`

**Stroke to translation with dictionary source** (`lookup_from_all`): Like `lookup`, but
returns results from every dictionary that contains the outline, in priority order. The
first entry is the one Plover actively uses. Entries marked as `{plover:deleted}` are
excluded.

```json
{"id": "2", "lookup_from_all": ["TEFT"]}
```
Response: `{"id": "2", "lookup_from_all": [{"translation": "test", "dict_path": "/path/to/main.json"}]}`

**Translation to strokes** (`reverse_lookup`): Given a word or phrase, returns all
outlines that produce it. Each outline is a list of stroke strings.

```json
{"id": "3", "reverse_lookup": "test"}
```
Response: `{"id": "3", "reverse_lookup": [["TEFT"], ["T", "E", "S", "T"]]}`

**Translation to strokes with dictionary source** (`reverse_lookup_with_dicts`): Like
`reverse_lookup`, but each result includes the path of the dictionary where that outline
is defined. Outlines that are overridden by a higher-priority dictionary are excluded (the
same behavior as `reverse_lookup`).

```json
{"id": "4", "reverse_lookup_with_dicts": "test"}
```
Response: `{"id": "4", "reverse_lookup_with_dicts": [{"outline": ["TEFT"], "dict_path": "/path/to/main.json"}]}`

**Case-insensitive translation to strokes** (`casereverse_lookup`): Like `reverse_lookup`
but matches regardless of case.

```json
{"id": "5", "casereverse_lookup": "test"}
```
Response: `{"id": "5", "casereverse_lookup": [["TEFT"]]}`

**Suggestions** (`get_suggestions`): Returns suggested outlines for a word, including
partial matches and alternate forms. Each suggestion has a `text` field (the word Plover
would produce) and a `steno_list` (all outlines for that text).

```json
{"id": "6", "get_suggestions": "test"}
```
Response: `{"id": "6", "get_suggestions": [{"text": "test", "steno_list": [["TEFT"]]}]}`

#### Engine State

**List loaded dictionaries** (`get_dictionaries`): Returns metadata for every dictionary
Plover has loaded, in priority order (highest priority first).

```json
{"id": "7", "get_dictionaries": true}
```
Response: `{"id": "7", "get_dictionaries": [{"path": "...", "enabled": true, "readonly": false, "errored": false}]}`

**Get machine state** (`get_machine_state`): Returns the current machine type (e.g.
"Keyboard", "Gemini PR") and its connection state (e.g. "connected", "disconnected").

```json
{"id": "8", "get_machine_state": true}
```
Response: `{"id": "8", "get_machine_state": {"type": "Keyboard", "state": "connected"}}`

**Get output state** (`get_output`): Returns whether steno output is currently enabled.

```json
{"id": "9", "get_output": true}
```
Response: `{"id": "9", "get_output": true}`

**Get full Plover config** (`get_config`): Returns the entire Plover configuration object.

```json
{"id": "10", "get_config": true}
```
Response: `{"id": "10", "get_config": {"auto_start": true, "undo_levels": 100, ...}}`

#### Combining Queries

Multiple queries can be sent in a single message. All results share the same response:

```json
{"id": "11", "get_output": true, "get_machine_state": true}
```
Response: `{"id": "11", "get_output": true, "get_machine_state": {"type": "Keyboard", "state": "connected"}}`
