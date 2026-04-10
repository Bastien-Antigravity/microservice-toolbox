import grpc
from concurrent import futures
import time

class GRPCServer:
    """
    Standardized gRPC server wrapper for the microservice-toolbox.
    Provides basic start/stop functionality with consistent logging.
    """
    def __init__(self, addr, max_workers=10):
        self.addr = addr
        self.server = grpc.server(futures.ThreadPoolExecutor(max_workers=max_workers))
        self._stopped = False

    def add_service(self, add_func, servicer):
        """
        Add a service to the gRPC server.
        Example: server.add_service(msg_pb2_grpc.add_LogServiceServicer_to_server, MyServicer())
        """
        add_func(servicer, self.server)

    def start(self):
        """Start the gRPC server."""
        print(f"Toolbox: GRPC Server listening on {self.addr}")
        self.server.add_insecure_port(self.addr)
        self.server.start()

    def wait_for_termination(self):
        """Block until the server is terminated."""
        try:
            self.server.wait_for_termination()
        except KeyboardInterrupt:
            self.stop()

    def stop(self, grace=5):
        """Stop the gRPC server gracefully."""
        if not self._stopped:
            print("Toolbox: Stopping GRPC Server...")
            self.server.stop(grace)
            self._stopped = True
