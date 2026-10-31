"""Round-robin TCP relay for the multi-proxy beta mode.

The relay picks one sing-box inbound for each new TCP connection. It does not
stripe one TCP stream across several servers; browsers can open parallel
connections, which are distributed independently.
"""

from __future__ import annotations

import itertools
import logging
import socket
import threading

log = logging.getLogger("balancer")


class TCPBalancer:
    def __init__(self) -> None:
        self._server: socket.socket | None = None
        self._accept_thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._backends: list[tuple[str, int]] = []
        self._choices = None
        self._lock = threading.Lock()
        self._clients: set[socket.socket] = set()

    @property
    def running(self) -> bool:
        return self._server is not None and not self._stop.is_set()

    def start(self, host: str, port: int, backends: list[tuple[str, int]]) -> None:
        if self.running:
            raise RuntimeError("Балансировщик уже запущен")
        if not backends:
            raise ValueError("Для балансировщика не заданы серверы")
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            server.bind((host, int(port)))
            server.listen(128)
            server.settimeout(0.5)
        except Exception:
            server.close()
            raise
        self._stop.clear()
        self._backends = list(backends)
        self._choices = itertools.cycle(self._backends)
        self._server = server
        self._accept_thread = threading.Thread(
            target=self._accept_loop, name="proxy-balancer", daemon=True
        )
        self._accept_thread.start()

    def _accept_loop(self) -> None:
        server = self._server
        while server and not self._stop.is_set():
            try:
                client, _address = server.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            with self._lock:
                backend = next(self._choices)
            worker = threading.Thread(
                target=self._relay, args=(client, backend), daemon=True,
                name="proxy-relay",
            )
            with self._lock:
                self._clients.add(client)
            worker.start()

    def _relay(self, client: socket.socket, backend: tuple[str, int]) -> None:
        upstream: socket.socket | None = None
        try:
            upstream = socket.create_connection(backend, timeout=5.0)
            upstream.settimeout(None)
            with self._lock:
                self._clients.add(upstream)
            directions = (
                (client, upstream), (upstream, client),
            )
            pumps = [threading.Thread(target=self._copy, args=pair, daemon=True)
                     for pair in directions]
            for pump in pumps:
                pump.start()
            while any(pump.is_alive() for pump in pumps) and not self._stop.is_set():
                for pump in pumps:
                    pump.join(timeout=0.2)
        except OSError as exc:
            if not self._stop.is_set():
                log.debug("Прокси-соединение завершено: %s", exc)
        finally:
            for sock in (client, upstream):
                if sock is not None:
                    with self._lock:
                        self._clients.discard(sock)
                    try:
                        sock.close()
                    except OSError:
                        pass

    @staticmethod
    def _copy(reader: socket.socket, writer: socket.socket) -> None:
        try:
            while True:
                data = reader.recv(65536)
                if not data:
                    break
                writer.sendall(data)
        except OSError:
            pass
        finally:
            try:
                writer.shutdown(socket.SHUT_WR)
            except OSError:
                pass

    def stop(self) -> None:
        self._stop.set()
        server, self._server = self._server, None
        if server:
            try:
                server.close()
            except OSError:
                pass
        with self._lock:
            clients = list(self._clients)
            self._clients.clear()
        for client in clients:
            try:
                client.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                client.close()
            except OSError:
                pass
        thread, self._accept_thread = self._accept_thread, None
        if thread and thread is not threading.current_thread():
            thread.join(timeout=1.5)
        self._backends.clear()
        self._choices = None
