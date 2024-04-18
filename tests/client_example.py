from os import makedirs
from os.path import join
from ssl import Purpose, SSLContext, create_default_context

from aiohttp import ClientError, ClientSession, ClientWebSocketResponse, TCPConnector
from aiohttp.typedefs import LooseHeaders
from multidict import MultiMapping
from nacl.public import PrivateKey
from nacl_middleware import MailBox, Nacl
from plover.oslayer.config import CONFIG_DIR

# Make sure there is a config folder
makedirs(CONFIG_DIR, exist_ok=True)
CLIENT_CERTIFICATES_FOLDER = "tests/client_certificates"


class Client:
    """
    Represents a client that interacts with a server using HTTP and WebSocket protocols.

    Args:
        host (str): The hostname or IP address of the server.
        port (str): The port number of the server.
        server_hex_public_key (str): The server's public key in hexadecimal format.
        ssl (dict): A dictionary containing SSL/TLS configuration parameters.

    Attributes:
        private_key (PrivateKey): The client's private key.
        session (ClientSession): The client's HTTP session.
        mail_box (MailBox): The client's mailbox for encryption and decryption.
        ssl_context (SSLContext): The SSL context for establishing a secure connection.

    """

    private_key: PrivateKey
    session: ClientSession
    mail_box: MailBox
    ssl_context: SSLContext
    socket: ClientWebSocketResponse

    def __init__(
        self, host: str, port: str, server_hex_public_key: str, ssl: dict
    ) -> None:
        """
        Initializes a new instance of the Client class.

        Args:
            host (str): The hostname or IP address of the server.
            port (str): The port number of the server.
            server_hex_public_key (str): The server's public key in hexadecimal format.
            ssl (dict): A dictionary containing SSL/TLS configuration parameters.

        """
        pynacl = Nacl()
        self.private_key = pynacl.private_key
        self.hex_public_key = pynacl.decoded_public_key()
        self.isTLS = True if ssl else False
        self.host = host
        self.port = port
        if self.isTLS:
            """
            The following certificates can be generated with:
            > openssl genpkey -algorithm RSA -out client.key
            > openssl req -new -key client.key -out client.csr
            > openssl req -x509 -nodes -days 365 -newkey rsa:2048 -keyout selfsigned.key -out selfsigned.crt
            > openssl x509 -req -in client.csr -CA selfsigned.crt -CAkey selfsigned.key -CAcreateserial -out client.crt -days 365
            """
            cert_path: str = join(CONFIG_DIR, ssl["cert_path"])
            self.ssl_context = create_default_context(
                Purpose.SERVER_AUTH, cafile=cert_path
            )
            self.ssl_context.load_cert_chain(
                certfile=join(CLIENT_CERTIFICATES_FOLDER, "client.crt"),
                keyfile=join(CLIENT_CERTIFICATES_FOLDER, "client.key"),
            )
        else:
            self.ssl_context = None
        connector = TCPConnector(ssl=self.ssl_context)
        origin = f"http{self.protocol()}://{self.host}"
        self.headers: LooseHeaders = {"Origin": origin}
        self.session = ClientSession(connector=connector, headers=self.headers)
        self.mail_box = MailBox(self.private_key, server_hex_public_key)

    def _get_encryption_params(self, message) -> MultiMapping[str]:
        """
        Returns the encryption parameters for the given message.

        Args:
            message: The message to be encrypted.

        Returns:
            MultiMapping[str]: A dictionary containing the encryption parameters.

        """
        return {
            "publicKey": self.hex_public_key,
            "encryptedMessage": self.encrypt(message),
        }

    def protocol(self) -> str:
        """
        Returns the protocol string based on whether SSL/TLS is enabled.

        Returns:
            str: The protocol string ("s" for HTTPS, "ws" for WebSocket).

        """
        return "s" if self.isTLS else ""

    def encrypt(self, message) -> str:
        """
        Encrypts the given message using the client's mailbox.

        Args:
            message: The message to be encrypted.

        Returns:
            str: The encrypted message.

        """
        return self.mail_box.box(message)

    def decrypt(self, encrypted_message) -> any:
        """
        Decrypts the given encrypted message using the client's mailbox.

        Args:
            encrypted_message: The encrypted message to be decrypted.

        Returns:
            any: The decrypted message.

        """
        return self.mail_box.unbox(encrypted_message)

    async def fetch(self, url, params=None) -> any:
        """
        Sends an HTTP GET request to the specified URL with optional parameters.

        Args:
            url (str): The URL to send the request to.
            params (dict, optional): The query parameters for the request.

        Returns:
            any: The response from the server.

        """
        try:
            async with self.session.get(url, params=params) as response:
                return await response.text()
        except ClientError as e:
            # Handle connection errors here
            print(f"Error fetching data: {e}")
            return None

    async def send_message(self, message) -> any:
        """
        Sends a message to the server using the HTTP protocol.

        Args:
            message: The message to be sent.

        Returns:
            any: The response from the server.

        """
        url = f"http{self.protocol()}://{self.host}:{self.port}/protocol"

        encrypted_res = await self.fetch(
            url, params=self._get_encryption_params(message)
        )
        return self.decrypt(encrypted_res)

    async def send_websocket_message(self, message) -> None:
        """
        Sends a message to the server using the WebSocket protocol.

        Args:
            message: The message to be sent.

        """
        await self.socket.send_str(self.encrypt(message))

    async def connect_to_websocket(self, message) -> None:
        """
        Connects to the server using the WebSocket protocol.

        Args:
            message: The message to be sent during the connection process.

        """
        url = f"ws{self.protocol()}://{self.host}:{self.port}/websocket"

        self.socket = await self.session.ws_connect(
            url,
            params=self._get_encryption_params(message),
            headers=self.headers,
            ssl=self.ssl_context,
        )

    async def receive_json(self):
        return await self.socket.receive_json()

    async def disconnect(self) -> None:
        """
        Disconnects the client from the server by closing the session.
        """
        await self.session.close()
