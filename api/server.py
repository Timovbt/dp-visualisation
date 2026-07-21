from fire import Fire

from visualisation.main import run_hello_world
from visualisation.utils.logging import logger

from dareplane_utils.default_server.server import DefaultServer


def main(port: int = 8080, ip: str = "127.0.0.1", loglevel: int = 10):
    logger.setLevel(loglevel)

    pcommand_map = {
        "START": run_hello_world,  # here you would hook up the functionality of your module to the server
    }

    server = DefaultServer(
        port, ip=ip, pcommand_map=pcommand_map, name="visualisation_control_server"
    )

    # initialize to start the socket
    server.init_server()
    
    logger.info(
        f"Server intialized, starting to listen for connections on: {ip=}, {port=}"
    )

    # start processing of the server
    server.start_listening()

    return 0


if __name__ == "__main__":
    Fire(main)
