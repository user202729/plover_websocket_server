# Plover WebSocket Server

A WebSocket server for exposing [Plover](https://github.com/openstenoproject/plover) events
and controlling Plover from an external program.

This plugin is available on [GitHub]( https://github.com/user202729/plover_websocket_server)
and [PyPI](https://pypi.org/project/plover-engine-server-2/) (under the name `plover-engine-server-2`).
Report all bugs on GitHub.

## Installation

Download the latest version of Plover for your operating system from the [releases page](https://github.com/openstenoproject/plover/releases). Only versions 4.0.0.dev8 and higher are supported.

1. Open Plover
2. Navigate to the Plugin Manager tool
3. Select the "plover-engine-server-2" plugin entry in the list
4. Click install
5. Restart Plover

The same method can be used for updating and uninstalling the plugin.

## Configuration

To configure the plugin, create a file named `plover_engine_server_config.json`
inside Plover's configuration directory (same directory as `plover.cfg` file).

Example content:

```json
{
  "host": "localhost",
  "port": 8086,
  "secretkey": "mysecretkey",
  "ssl": {
    "cert_path": "/path/to/cert.pem",
    "key_path": "/path/to/key.pem"
  }
}
```

All fields are optional, except if you have either specified a `cert_path` or a `key_path`. In that case you have to make sure that the path pair is properly set there. The default is included in the example above.

## How to Use

* Enable it in Configure -> Plugins
* Connect to either ws://localhost:8086/websocket or wss://localhost:8086/websocket, depending on whether or not you have specified SSL configuration, with your client and get the data pushed to you as
event: data formatted JSON.

### Received data format

Search for occurrences of `queue_message` in `plover_engine_server/manager.py`,
or write an example program (or use the existing `plover_engine_server/websocket/example_client.py`)
and observe its output.

Controlling Plover from other programs:

* Sending 'close' disconnects you.
* Sending a valid JSON string will execute the specified action.
For example `{"stroke": ["S-"]}` (note that invalid keys are silently dropped),
or `{"translation": "abc"}`.

Note: to avoid Plover being controlled by a malicious website, you should set some other than default key, and
add the secret key to the request header `X-Secret-Token`.

If there's some error during the execution, it will be silently ignored and printed on stderr.

If the `"force"` key is `true` then the command will be executed even when the engine is turned off.
Note that `{PLOVER:RESUME}` will have no effect in that case.

Because the Plover inner working is closely tied to the assumption
that strokes can only come from the keyboard, when `{PLOVER:RESUME}` (or a command with similar effect,
such as `{PLOVER:TOGGLE}`) is sent and the machine is
"Keyboard" then some characters before the cursor will be deleted.
To prevent this, set the `"zero_last_stroke_length"` key to `true`.
**Note** This should be used very sparingly because it may have unintended effects.
