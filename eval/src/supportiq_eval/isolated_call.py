"""Killable local evaluation worker. Never deserialize data from external inputs."""
import multiprocessing
import time
import cloudpickle


def _worker(connection):
    try:
        while True:
            payload = connection.recv_bytes()
            try:
                function, kwargs = cloudpickle.loads(payload)
                connection.send_bytes(b'ready')
                try:
                    value = ('ok', function(**kwargs))
                except BaseException as exc:
                    value = ('error', type(exc).__name__)
                connection.send_bytes(cloudpickle.dumps(value))
            except EOFError:
                break
    except (EOFError, BrokenPipeError, OSError):
        pass
    finally:
        connection.close()


class IsolatedCaller:
    def __init__(self):
        self.process = None
        self.connection = None
        self.last_execution_seconds = 0.0

    def is_running(self):
        return self.process is not None and self.process.is_alive()

    def call(self, function, kwargs, timeout):
        payload = cloudpickle.dumps((function, kwargs))
        if not self.is_running():
            self.close()
            ctx = multiprocessing.get_context('spawn')
            self.connection, child = ctx.Pipe()
            self.process = ctx.Process(target=_worker, args=(child,), daemon=True)
            self.process.start()
            child.close()
        try:
            self.connection.send_bytes(payload)
            # Deserialization/model initialization is preparation, outside execution timing.
            if not self.connection.poll(60):
                raise TimeoutError('Worker preparation timed out')
            if self.connection.recv_bytes() != b'ready':
                raise RuntimeError('Worker handshake failed')
            started = time.perf_counter()
            if not self.connection.poll(timeout):
                raise TimeoutError('Evaluation deadline exceeded')
            status, value = cloudpickle.loads(self.connection.recv_bytes())
            self.last_execution_seconds = time.perf_counter() - started
            if status != 'ok':
                raise RuntimeError(value)
            return value
        except BaseException:
            self.close()
            raise

    def close(self):
        if self.process is not None:
            if self.process.is_alive():
                self.process.terminate()
                self.process.join(3)
                if self.process.is_alive():
                    self.process.kill()
                    self.process.join(3)
            else:
                self.process.join()
            self.process.close()
            self.process = None
        if self.connection is not None:
            self.connection.close()
            self.connection = None
