"""The middleman between Plover and the server."""

import json
import os
import traceback
from typing import Optional

import jsonpickle

from plover import log
from plover.engine import StenoEngine, ErroredDictionary
from plover.steno import Stroke
from plover.oslayer.config import CONFIG_DIR
from plover.formatting import _Action
from plover.steno_dictionary import StenoDictionaryCollection
from plover.translation import _mapping_to_macro, Translation

from plover_engine_server.errors import (
    ERROR_MISSING_ENGINE,
    ERROR_SERVER_RUNNING,
    ERROR_NO_SERVER,
)
from plover_engine_server.server import EngineServer, ServerStatus
from plover_engine_server.websocket.server import WebSocketServer
from plover_engine_server.config import ServerConfig


SERVER_CONFIG_FILE = 'plover_engine_server_config.json'


class _NoOpOutput:
    """Swapped in for keyboard emulation during injected strokes/translations.
    Hooks still fire (WebSocket clients see events), but no keys are typed
    into the OS, which prevents feedback loops with the Keyboard machine."""
    def send_string(self, s): pass
    def send_backspaces(self, n): pass
    def send_key_combination(self, c): pass

QUERY_KEYS = frozenset({
    'lookup',
    'lookup_from_all',
    'reverse_lookup',
    'reverse_lookup_with_dicts',
    'casereverse_lookup',
    'get_suggestions',
    'get_dictionaries',
    'get_machine_state',
    'get_output',
    'get_config',
})


class EngineServerManager:
    """Manages a server that exposes the Plover engine."""

    def __init__(self, engine: StenoEngine):
        self._server: Optional[EngineServer] = None
        self._engine: StenoEngine = engine
        self._config_path: str = os.path.join(CONFIG_DIR, SERVER_CONFIG_FILE)

    def start(self):
        """Starts the server.

        Raises:
            AssertionError: The server failed to start.
            IOError: The server failed to start.
        """

        if self.get_server_status() != ServerStatus.Stopped:
            raise AssertionError(ERROR_SERVER_RUNNING)

        self._config = ServerConfig(self._config_path)

        self._server = WebSocketServer(
            self._config.host,
            self._config.port,
            self._config.ssl,
            self._config.secretkey,
        )
        self._server.register_message_callback(self._on_message)
        self._server.start()
        self._connect_hooks()

    def stop(self):
        """Stops the server.

        Raises:
            AssertionError: The server failed to stop.
        """

        if self.get_server_status() != ServerStatus.Running:
            raise AssertionError(ERROR_NO_SERVER)

        self._disconnect_hooks()
        self._server.queue_stop()
        log.info("Joining server thread...")
        self._server.join()
        log.info("Server thread joined.")
        self._server = None

    def get_server_status(self) -> ServerStatus:
        """Gets the status of the server.

        Returns:
            The status of the server.
        """

        return self._server.status if self._server else ServerStatus.Stopped

    # ── Incoming message handling ──────────────────────────────────────

    def _on_message(self, data: dict):
        with self._engine:
            response = {}

            forced_on = False
            if data.get('forced') and not self._engine._is_running:
                forced_on = True
                self._engine._is_running = True

            try:
                self._handle_actions(data)
                self._handle_queries(data, response)
            finally:
                if forced_on:
                    self._engine._is_running = False

            if response:
                if 'id' in data:
                    response['id'] = data['id']
                return response
            return None

    def _handle_actions(self, data: dict):
        if data.get('zero_last_stroke_length'):
            self._engine._machine._last_stroke_key_down_count = 0
            self._engine._machine._stroke_key_down_count = 0

        if 'stroke' in data or 'translation' in data:
            real_kbd = self._engine._keyboard_emulation
            self._engine._keyboard_emulation = _NoOpOutput()
            try:
                self._inject_stroke(data)
                self._inject_translation(data)
            finally:
                self._engine._keyboard_emulation = real_kbd

        if 'set_output' in data:
            self._engine._set_output(bool(data['set_output']))

        if 'toggle_output' in data:
            self._engine._toggle_output()

        if 'add_translation' in data:
            params = data['add_translation']
            if isinstance(params, dict):
                strokes = tuple(params.get('strokes', ()))
                translation = params.get('translation', '')
                dictionary_path = params.get('dictionary_path')
                self._engine.add_translation(strokes, translation, dictionary_path)

        if 'clear_translator_state' in data:
            undo = bool(data['clear_translator_state'])
            self._engine.clear_translator_state(undo=undo)

    def _inject_stroke(self, data: dict):
        if 'stroke' not in data:
            return
        steno_keys = data['stroke']
        if isinstance(steno_keys, list):
            try:
                stroke = Stroke(steno_keys)
                self._engine._translator.translate(stroke)
                self._engine._trigger_hook("stroked", stroke)
            except:
                traceback.print_exc()

    def _inject_translation(self, data: dict):
        if 'translation' not in data:
            return
        mapping = data['translation']
        if isinstance(mapping, str):
            try:
                stroke = Stroke([])
                macro = _mapping_to_macro(mapping, stroke)
                if macro is not None:
                    self._engine._translator.translate_macro(macro)
                else:
                    t = Translation([stroke], mapping)
                    self._engine._translator.translate_translation(t)
                    self._engine._translator.flush()
            except:
                traceback.print_exc()

    def _handle_queries(self, data: dict, response: dict):
        if not data.keys() & QUERY_KEYS:
            return

        if 'lookup' in data:
            outline = data['lookup']
            if isinstance(outline, list):
                response['lookup'] = self._engine.lookup(tuple(outline))

        if 'lookup_from_all' in data:
            outline = data['lookup_from_all']
            if isinstance(outline, list):
                results = self._engine.dictionaries.lookup_from_all(
                    tuple(outline),
                )
                response['lookup_from_all'] = [
                    {
                        'translation': value,
                        'dict_path': d.path,
                    }
                    for value, d in (results or [])
                    if value.lower() != '{plover:deleted}'
                ]

        if 'reverse_lookup' in data:
            text = data['reverse_lookup']
            if isinstance(text, str):
                results = self._engine.reverse_lookup(text)
                response['reverse_lookup'] = [
                    list(outline) for outline in results
                ] if results else []

        if 'reverse_lookup_with_dicts' in data:
            text = data['reverse_lookup_with_dicts']
            if isinstance(text, str):
                dicts = self._engine.dictionaries
                valid_outlines = dicts.reverse_lookup(text)
                results = []
                for outline in valid_outlines:
                    for d in dicts.dicts:
                        if not d.enabled:
                            continue
                        if d.get(outline) is not None:
                            results.append({
                                'outline': list(outline),
                                'dict_path': d.path,
                            })
                            break
                response['reverse_lookup_with_dicts'] = results

        if 'casereverse_lookup' in data:
            text = data['casereverse_lookup']
            if isinstance(text, str):
                results = self._engine.casereverse_lookup(text)
                response['casereverse_lookup'] = [
                    list(outline) for outline in results
                ] if results else []

        if 'get_suggestions' in data:
            text = data['get_suggestions']
            if isinstance(text, str):
                suggestions = self._engine.get_suggestions(text)
                response['get_suggestions'] = [
                    {
                        'text': s.text,
                        'steno_list': [
                            list(outline) for outline in s.steno_list
                        ],
                    }
                    for s in suggestions
                ]

        if 'get_dictionaries' in data:
            dicts = self._engine.dictionaries
            response['get_dictionaries'] = [
                {
                    'path': d.path,
                    'enabled': d.enabled,
                    'readonly': d.readonly,
                    'errored': isinstance(d, ErroredDictionary),
                }
                for d in dicts.dicts
            ]

        if 'get_machine_state' in data:
            response['get_machine_state'] = {
                'type': (
                    self._engine._machine_params.type
                    if self._engine._machine_params else None
                ),
                'state': self._engine.machine_state,
            }

        if 'get_output' in data:
            response['get_output'] = self._engine.output

        if 'get_config' in data:
            config_json = jsonpickle.encode(
                self._engine.config, unpicklable=False,
            )
            response['get_config'] = json.loads(config_json)

    # ── Hook management ────────────────────────────────────────────────

    def _connect_hooks(self):
        """Creates hooks into all of Plover's events."""

        if not self._engine:
            raise AssertionError(ERROR_MISSING_ENGINE)
        for hook in self._engine.HOOKS:
            callback = getattr(self, f'_on_{hook}', None)
            if callback is not None:
                self._engine.hook_connect(hook, callback)

    def _disconnect_hooks(self):
        """Removes hooks from all of Plover's events."""

        if not self._engine:
            raise AssertionError(ERROR_MISSING_ENGINE)
        for hook in self._engine.HOOKS:
            callback = getattr(self, f'_on_{hook}', None)
            if callback is not None:
                self._engine.hook_disconnect(hook, callback)

    # ── Hook callbacks (broadcast to all clients) ──────────────────────

    def _on_stroked(self, stroke: Stroke):
        """Broadcasts when a new stroke is performed.

        Args:
            stroke: The stroke that was just performed.
        """

        stroke_json = jsonpickle.encode(stroke, unpicklable=False)
        data = {'stroked': json.loads(stroke_json), 'rtfcre': stroke.rtfcre}
        self._server.queue_message(data)

    def _on_translated(self, old: list[_Action], new: list[_Action]):
        """Broadcasts when a new translation occurs.

        Args:
            old: A list of the previous actions for the current translation.
            new: A list of the new actions for the current translation.
        """

        old_json = jsonpickle.encode(old, unpicklable=False)
        new_json = jsonpickle.encode(new, unpicklable=False)
        data = {
            'translated': {
                'old': json.loads(old_json),
                'new': json.loads(new_json),
            }
        }
        self._server.queue_message(data)

    def _on_machine_state_changed(self, machine_type: str, machine_state: str):
        """Broadcasts when the active machine state changes.

        Args:
            machine_type: The name of the active machine.
            machine_state: The new machine state. This should be one of the
                state constants listed in plover.machine.base.
        """

        data = {
            'machine_state_changed': {
                'machine_type': machine_type,
                'machine_state': machine_state,
            }
        }
        self._server.queue_message(data)

    def _on_output_changed(self, enabled: bool):
        """Broadcasts when the state of output changes.

        Args:
            enabled: If the output is now enabled or not.
        """

        self._server.queue_message({'output_changed': enabled})

    def _on_config_changed(self, config_update):
        """Broadcasts when the configuration changes.

        Args:
            config_update: An object containing the full configuration or a
                part of the configuration that was updated.
        """

        config_json = jsonpickle.encode(config_update, unpicklable=False)
        self._server.queue_message({'config_changed': json.loads(config_json)})

    def _on_dictionaries_loaded(self, dictionaries: StenoDictionaryCollection):
        """Broadcasts when all of the dictionaries get loaded.

        Args:
            dictionaries: A collection of the dictionaries that loaded.
        """

        self._server.queue_message({'dictionaries_loaded': True})

    def _on_dictionary_state_changed(self, filename, dictionary):
        """Broadcasts when a single dictionary's loading state changes.

        Args:
            filename: The path to the dictionary file.
            dictionary: The StenoDictionary or ErroredDictionary instance.
        """

        data = {
            'dictionary_state_changed': {
                'path': filename,
                'enabled': dictionary.enabled,
                'errored': isinstance(dictionary, ErroredDictionary),
            }
        }
        self._server.queue_message(data)

    def _on_send_string(self, text: str):
        """Broadcasts when a new string is output.

        Args:
            text: The string that was output.
        """

        self._server.queue_message({'send_string': text})

    def _on_send_backspaces(self, count: int):
        """Broadcasts when backspaces are output.

        Args:
            count: The number of backspaces that were output.
        """

        self._server.queue_message({'send_backspaces': count})

    def _on_send_key_combination(self, combination: str):
        """Broadcasts when a key combination is output.

        Args:
            combination: A string representing a sequence of key combinations.
                Keys are represented by their names based on the OS-specific
                keyboard implementations in plover.oslayer.
        """

        self._server.queue_message({'send_key_combination': combination})

    def _on_add_translation(self):
        """Broadcasts when the add translation tool is opened via a command."""

        self._server.queue_message({'add_translation': True})

    def _on_focus(self):
        """Broadcasts when the main window is focused via a command."""

        self._server.queue_message({'focus': True})

    def _on_configure(self):
        """Broadcasts when the configuration tool is opened via a command."""

        self._server.queue_message({'configure': True})

    def _on_lookup(self):
        """Broadcasts when the lookup tool is opened via a command."""

        self._server.queue_message({'lookup': True})

    def _on_suggestions(self):
        """Broadcasts when the suggestions tool is opened via a command."""

        self._server.queue_message({'suggestions': True})

    def _on_quit(self):
        """Broadcasts when the application is terminated.

        Can be either a full quit or a restart.
        """

        self._server.queue_message({'quit': True})
