# TODO: clean up this code

import base64
import json
import os
import socket
import sys
import threading
import time
from typing import Any

ORCHESTRATOR_IP = os.environ.get("ORCHESTRATOR_HOST", "host.docker.internal")
ORCHESTRATOR_PORT = 65432
ORCHESTRATOR_ADDR = (ORCHESTRATOR_IP, ORCHESTRATOR_PORT)


def handle_write(addr, message):
    wire_message = socket.gethostname() + ":" + message
    for attempt in range(1, 6):
        try:
            print(f"attempting to write to {addr} (attempt {attempt}/5)")
            with socket.create_connection(addr, timeout=5.0) as client_socket:
                client_socket.sendall(wire_message.encode())
            print("tool msg:", wire_message)
            return
        except OSError as e:
            print(f"[-] Error sending message to {addr}: {e}")
            if attempt < 5:
                time.sleep(0.5)


def main() -> None:
    tool_code_b64: str = os.environ.get("TOOL_CODE", "")
    args_json_b64: str = os.environ.get("ARGS", "[]")
    kwargs_json_b64: str = os.environ.get("KWARGS", "{}")
    tool_code: str = base64.b64decode(tool_code_b64).decode()
    args_json: str = base64.b64decode(args_json_b64).decode()
    kwargs_json: str = base64.b64decode(kwargs_json_b64).decode()

    try:
        args: list[Any] = json.loads(args_json)
        kwargs: dict[str, Any] = json.loads(kwargs_json)
    except Exception as e:
        print("Error decoding ARGS:", e, flush=True)
        sys.exit(1)
    if not tool_code.strip():
        print("No TOOL_CODE provided.", flush=True)
        sys.exit(1)
    try:
        local_ns = {}
        exec(tool_code, {}, local_ns)

        result: Any = local_ns["main"](*args, **kwargs)

        result_b64: str = base64.b64encode(json.dumps(result).encode()).decode()

        result_b64 = "RESULT:" + result_b64

        # Send message to orchestrator
        writer_thread = threading.Thread(target=handle_write, args=(ORCHESTRATOR_ADDR, result_b64), daemon=True)
        writer_thread.start()

        writer_thread.join()

    except Exception as e:
        error_msg: str = f"Error executing tool code: {e}"
        error_msg_b64: str = "ERROR:" + base64.b64encode(error_msg.encode()).decode()
        print(error_msg, flush=True)
        writer_thread = threading.Thread(target=handle_write, args=(ORCHESTRATOR_ADDR, error_msg_b64), daemon=True)
        writer_thread.start()
        writer_thread.join()

        sys.exit(1)


if __name__ == "__main__":
    main()
