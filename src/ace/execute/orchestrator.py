import base64
import json
import os
import socket
import threading
import time
from queue import Queue
from typing import Any, cast

from ..logging_config import get_logger
from ..recovery import RepairPolicy, build_output_validation_failure
from ..schema.abstract import AbstractPlan
from ..schema.concrete import ConcreteToolBase
from ..schema.events import AgentEventHandler, ExecutionOutputEvent, RepairAppliedEvent, ToolFailureEvent
from ..schema.outcome import ExecutionOutcome, ExecutionStatus, ExecutionVariant, ToolExecutionResult, ToolResultStatus
from ..schema.recovery import RepairPatch, ToolFailure
from .sandbox import PlanExecutionSandbox, ToolExecutionSandbox

logger = get_logger(__name__)


class ExecutionAbortedError(RuntimeError):
    """A fatal execution error that still carries a safe experiment outcome."""

    def __init__(self, outcome: ExecutionOutcome):
        super().__init__("Execution aborted after tool output schema validation failed")
        self.outcome = outcome


class PlanOrchestrator:
    plan: AbstractPlan
    tools: dict[str, ConcreteToolBase]
    plan_execution_sandbox: PlanExecutionSandbox | None
    tool_execution_sandbox: ToolExecutionSandbox | None
    listener_thread: threading.Thread | None
    shutdown: threading.Event
    toolrunner_ids: set[str]
    toolrunner_context: dict[str, tuple[str, ToolExecutionSandbox]]
    exception_queue: Queue
    result: ExecutionOutcome | None
    tool_use_history: list[str]
    event_handler: AgentEventHandler | None
    failure_history: list[ToolFailure]
    repair_history: list[RepairPatch]
    tool_results: dict[str, ToolExecutionResult]
    execution_output_history: list[str]
    execution_variant: ExecutionVariant

    def __init__(
        self,
        plan: AbstractPlan,
        tools: dict[str, ConcreteToolBase],
        event_handler: AgentEventHandler | None = None,
        execution_variant: ExecutionVariant = ExecutionVariant.M1,
    ):
        logger.info("Initializing PlanOrchestrator")
        self.plan = plan
        self.tools = tools
        self.result = None
        self.shutdown = threading.Event()
        self.plan_execution_sandbox = None
        self.tool_execution_sandbox = None
        self.toolrunner_ids = set()
        self.toolrunner_context = {}
        self.exception_queue = Queue()
        self.result = None
        self.tool_use_history = []
        self.event_handler = event_handler
        self.execution_variant = ExecutionVariant(execution_variant)
        self.failure_history = []
        self.repair_history = []
        self.tool_results = {}
        self.execution_output_history = []
        self.repair_policy = RepairPolicy(max_repairs_per_tool=1)

        logger.debug(f"Plan has {len(plan.abs_tools)} abstract tools")
        logger.debug(f"Tool mapping has {len(tools)} concrete tools")
        logger.debug(f"Tools: {list(tools.keys())}")

        # Log detailed execution plan using enhanced logger
        logger.log_execution("ORCHESTRATOR_INIT", f"tools={len(tools)} abs_tools={len(plan.abs_tools)}")
        logger.log_plan(plan.script, plan.abs_tools)

        # Log tool mappings
        for abs_name, concrete_tool in tools.items():
            logger.log_tool_match(
                abs_name,
                concrete_tool.name,
                {
                    "provider": concrete_tool.provider,
                    "clearances": str(concrete_tool.clearances),
                    "permissions": str(concrete_tool.permissions),
                },
            )

    def __enter__(self):
        logger.debug("Entering PlanOrchestrator context")
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        logger.debug("Exiting PlanOrchestrator context")
        if exc_type:
            logger.error(f"PlanOrchestrator context exited with exception: {exc_type.__name__}: {exc_value}")
        self.kill()

    def launch(self) -> None:
        logger.info("Launching plan orchestrator")

        # Start listener thread
        logger.debug("Starting orchestrator listener thread")
        self.listener_thread = threading.Thread(target=self.__start_listener, args=("0.0.0.0", 65432), daemon=True)
        self.listener_thread.start()

        # Launch plan execution container and wait for port to open
        logger.debug("Launching plan execution sandbox")
        try:
            self.plan_execution_sandbox = PlanExecutionSandbox(self.plan)
            self.plan_execution_sandbox.launch()
            logger.debug("Plan execution sandbox launched, waiting for port")
            self.plan_execution_sandbox.wait_for_port()
            logger.info("Plan execution sandbox ready")
        except Exception as e:
            logger.error(f"Failed to launch plan execution sandbox: {e}", exc_info=True)
            raise

    def join(self, timeout: float | None = None) -> None:
        if timeout is None:
            timeout = float(os.getenv("ACE_EXECUTION_TIMEOUT_SECONDS", "300"))

        logger.debug("Joining orchestrator threads")
        timed_out = False
        try:
            if self.listener_thread:
                deadline = time.monotonic() + timeout
                while self.listener_thread.is_alive() and self.exception_queue.empty():
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        timed_out = True
                        break
                    self.listener_thread.join(timeout=min(0.2, remaining))

                if not self.listener_thread.is_alive():
                    logger.debug("Listener thread joined")
        finally:
            self.kill()

        if not self.exception_queue.empty():
            exception = self.exception_queue.get()
            logger.error(f"Orchestrator completed with exception: {exception}")
            raise exception
        elif timed_out:
            raise TimeoutError(f"Plan execution exceeded {timeout:g} seconds")
        else:
            logger.info("Orchestrator completed successfully")

    def kill(self) -> None:
        logger.debug("Killing orchestrator and cleaning up sandboxes")
        self.shutdown.set()

        if self.plan_execution_sandbox:
            logger.debug("Killing plan execution sandbox")
            self.plan_execution_sandbox.kill()
        if self.tool_execution_sandbox:
            logger.debug("Killing tool execution sandbox")
            self.tool_execution_sandbox.kill()

    def handle_invoke(self, tool_name: str, tool_args: list, tool_kwargs: dict) -> None:
        logger.info(f"Handling tool invocation: {tool_name}")
        logger.debug(f"Tool args: {tool_args}")
        logger.debug(f"Tool kwargs: {tool_kwargs}")

        # Log detailed invocation using enhanced logger
        logger.log_execution("TOOL_INVOKE", f"tool={tool_name} args={tool_args} kwargs={tool_kwargs}")

        if tool_name not in self.tools:
            error_msg = f"Tool {tool_name} not found in available tools: {list(self.tools.keys())}"
            logger.error(error_msg)
            logger.log_execution("TOOL_NOT_FOUND", error_msg)
            self.exception_queue.put(ValueError(error_msg))
            return

        # Execute tool and retrieve result
        tool = self.tools[tool_name]
        logger.debug(f"Executing tool: {tool.name} (provider: {tool.provider})")
        logger.log_execution(
            "TOOL_EXECUTE",
            f"concrete_tool={tool.name} provider={tool.provider} clearances={tool.clearances} permissions={tool.permissions}",
        )

        self.tool_execution_sandbox = ToolExecutionSandbox(tool)
        self.tool_use_history.append(tool_name)

        try:
            self.tool_execution_sandbox.launch(tool_args, tool_kwargs)
            if self.tool_execution_sandbox:
                runner_id = self.tool_execution_sandbox.id
                self.toolrunner_ids.add(runner_id)
                self.toolrunner_context[runner_id] = (tool_name, self.tool_execution_sandbox)
                logger.debug(f"Tool {tool_name} execution started with container ID: {runner_id}")
        except Exception as e:
            logger.error(f"Failed to execute tool {tool_name}: {e}", exc_info=True)
            self.exception_queue.put(ValueError(f"Failed to execute tool {tool_name}: {e}"))
            error = "Tool failed to start."
            error_b64 = base64.b64encode(error.encode()).decode()
            if self.plan_execution_sandbox:
                self.plan_execution_sandbox.send(f"ERROR:{error_b64}")

    def handle_print(self, message: str) -> None:
        logger.debug(f"Received PRINT message: {message[:100]}...")
        self.execution_output_history.append(message)

    def flush_trusted_outputs(self) -> None:
        if self.failure_history and self.execution_variant is ExecutionVariant.M1:
            logger.info("Suppressing generated plan output because execution contains rejected tool results")
            self.execution_output_history.clear()
            return

        for message in self.execution_output_history:
            if self.event_handler:
                self.event_handler.on_execution_output(ExecutionOutputEvent(message))
            else:
                print("PRINT:", message)
        self.execution_output_history.clear()

    def handle_output_validation_failure(
        self,
        tool: ConcreteToolBase,
        result: object,
        validation_error: Exception,
        abstract_tool: str | None = None,
    ) -> None:
        abstract_tool = abstract_tool or (self.tool_use_history[-1] if self.tool_use_history else "")
        affected_fields: tuple[str, ...] = ()
        errors = getattr(validation_error, "errors", None)
        if callable(errors):
            validation_errors = cast(list[dict[str, Any]], errors())
            affected_fields = tuple(".".join(str(part) for part in error.get("loc", ())) for error in validation_errors)

        if self.execution_variant is ExecutionVariant.BASELINE:
            failure = build_output_validation_failure(
                plan=self.plan,
                tools=self.tools,
                abstract_tool=abstract_tool,
                concrete_tool=tool,
                output=result,
                affected_fields=affected_fields,
                attempt=1,
            )
            self.failure_history.append(failure)
            self.tool_results[tool.name] = ToolExecutionResult(status=ToolResultStatus.REJECTED, value=None)
            self.execution_output_history.clear()
            outcome = ExecutionOutcome(
                status=ExecutionStatus.FAILED,
                final_output=None,
                tool_results=dict(self.tool_results),
                failures=list(self.failure_history),
                repairs=[],
            )
            self.result = outcome
            if self.event_handler:
                self.event_handler.on_tool_failure(ToolFailureEvent(failure))

            error_message = "Tool output schema validation failed; aborting baseline execution."
            error_b64 = base64.b64encode(error_message.encode()).decode()
            if self.plan_execution_sandbox:
                self.plan_execution_sandbox.send(f"ERROR:{error_b64}")
            self.exception_queue.put(ExecutionAbortedError(outcome))
            self.shutdown.set()
            return

        failure, patch = self.repair_policy.propose_output_rejection(
            plan=self.plan,
            tools=self.tools,
            abstract_tool=abstract_tool,
            concrete_tool=tool,
            output=result,
            affected_fields=affected_fields,
        )
        self.failure_history.append(failure)
        self.repair_history.append(patch)
        self.tool_results[tool.name] = ToolExecutionResult(status=ToolResultStatus.REJECTED, value=None)

        if self.event_handler:
            self.event_handler.on_tool_failure(ToolFailureEvent(failure))
            self.event_handler.on_repair_applied(RepairAppliedEvent(patch))

        error_message = (
            f"Rejected invalid output from {tool.name}; resume through the trusted plan's existing exception handler."
        )
        error_b64 = base64.b64encode(error_message.encode()).decode()
        if self.plan_execution_sandbox:
            self.plan_execution_sandbox.send(f"ERROR:{error_b64}")

    def handle_terminate(self) -> None:
        logger.info("Received TERMINATE message")
        if self.plan_execution_sandbox:
            self.plan_execution_sandbox.kill()
        self.shutdown.set()

    def finalize_outcome(self, raw_final_output: Any) -> ExecutionOutcome:
        outcome_factory = (
            ExecutionOutcome.from_legacy_recovery
            if self.execution_variant is ExecutionVariant.M0
            else ExecutionOutcome.from_execution
        )
        outcome = outcome_factory(
            raw_final_output=raw_final_output,
            tool_results=self.tool_results,
            failures=self.failure_history,
            repairs=self.repair_history,
        )
        self.result = outcome
        self.flush_trusted_outputs()
        return outcome

    def _active_plan_id(self) -> str | None:
        sandbox = self.plan_execution_sandbox
        if sandbox is None or sandbox.container is None:
            return None
        container_id = sandbox.container.id
        return container_id[:12] if container_id else None

    def __handle_client(self, client_socket: socket.socket, addr: tuple[str, int]) -> None:
        logger.debug(f"New connection from {addr}")

        try:
            while True:
                # TODO: Implement message buffering
                message = client_socket.recv(4096).decode()
                if not message:
                    logger.debug(f"Empty message received from {addr}, closing connection")
                    break

                logger.debug(f"Received message from {addr}: {message[:200]}...")
                try:
                    id, message = message.split(":", 1)
                except ValueError:
                    logger.warning(f"Invalid message format from {addr}: {message}")
                    continue

                plan_id = self._active_plan_id()
                logger.debug(f"Processing message from ID: {id}, plan_id: {plan_id}")

                if id == plan_id:
                    if message.startswith("INVOKE:"):
                        logger.debug("Processing INVOKE message")
                        msg_b64 = message[len("INVOKE:") :]
                        msg_json = base64.b64decode(msg_b64).decode()
                        tool_name, tool_args, tool_kwargs = json.loads(msg_json)
                        logger.info(f"Plan invoking tool: {tool_name}")
                        self.handle_invoke(tool_name, tool_args, tool_kwargs)
                    elif message.startswith("PRINT:"):
                        logger.debug("Processing PRINT message")
                        msg_b64 = message[len("PRINT:") :]
                        msg_str = base64.b64decode(msg_b64).decode()
                        if "Error executing tool code" in message:
                            logger.error(f"Tool execution error detected in PRINT: {msg_str}")
                            exception = RuntimeError(message)
                            self.exception_queue.put(exception)
                            raise exception
                        self.handle_print(msg_str)
                    elif message.startswith("TERMINATE"):
                        logger.info("Processing TERMINATE message")
                        # Extract final output
                        msg_b64 = message[len("TERMINATE:") :]
                        msg_str = base64.b64decode(msg_b64).decode()
                        raw_final_output = json.loads(msg_str)
                        self.finalize_outcome(raw_final_output)
                        logger.info(f"Plan execution completed with result: {type(self.result).__name__}")

                        # Cleanup orchestrator
                        self.handle_terminate()
                        break
                    else:
                        logger.warning(f"Unknown message type from plan {id}: {message[:100]}")
                elif id in self.toolrunner_ids:
                    logger.debug(f"Processing message from tool runner {id}")
                    if message.startswith("RESULT:"):
                        logger.debug("Processing tool RESULT message")
                        result_b64 = message[len("RESULT:") :]

                        # Decode result to dict
                        result_json = base64.b64decode(result_b64).decode()
                        result_dict = json.loads(result_json)
                        abstract_tool = ""
                        tool = None
                        runner_context = self.toolrunner_context.get(id)
                        if runner_context:
                            abstract_tool, tool_sandbox = runner_context
                            tool = tool_sandbox.tool
                            tool_sandbox.kill()
                        elif self.tool_execution_sandbox:
                            tool = self.tool_execution_sandbox.tool
                            self.tool_execution_sandbox.kill()

                        # Validate output against tool schema if available
                        if tool and tool.output_schema:
                            try:
                                validated = tool.output_schema.model_validate(result_dict)
                                result_dict = validated.model_dump()
                            except Exception as e:
                                logger.error(f"Tool output schema validation failed: {type(e).__name__}")
                                self.handle_output_validation_failure(
                                    tool,
                                    result_dict,
                                    e,
                                    abstract_tool=abstract_tool,
                                )
                                if self.tool_execution_sandbox:
                                    self.tool_execution_sandbox.kill()
                                continue

                        if tool:
                            self.tool_results[tool.name] = ToolExecutionResult(
                                status=ToolResultStatus.SUCCESS,
                                value=result_dict,
                            )

                        # Encode validated dict and send to worker
                        if self.plan_execution_sandbox:
                            validated_json = json.dumps(result_dict)
                            validated_b64 = base64.b64encode(validated_json.encode()).decode()
                            self.plan_execution_sandbox.send(f"RESPONSE:{validated_b64}")
                            logger.debug("Sent validated tool result back to plan")
                    elif message.startswith("ERROR:"):
                        logger.error(f"Tool execution error from {id}")
                        error = message[len("ERROR:") :]
                        error_b64 = base64.b64encode(error.encode()).decode()
                        if self.tool_execution_sandbox:
                            self.tool_execution_sandbox.kill()

                        if self.plan_execution_sandbox:
                            self.plan_execution_sandbox.send(f"ERROR:{error_b64}")
                        exception = RuntimeError("Error in execution:" + str(error))
                        self.exception_queue.put(exception)
                        raise exception
                else:
                    logger.warning(f"Received message from unknown ID {id}: {message[:100]}")
        except ConnectionResetError:
            logger.warning(f"Connection lost with {addr}")
        except RuntimeError as e:
            logger.error(f"Runtime error in client handler for {addr}: {e}", exc_info=True)
            self.exception_queue.put(e)
            raise
        except Exception as e:
            logger.error(f"Unexpected error in client handler for {addr}: {e}", exc_info=True)
            self.exception_queue.put(e)
            raise
        finally:
            client_socket.close()
            logger.debug(f"Closed connection to {addr}")

    def __start_listener(self, ip: str, port: int, backlog: int = 5) -> None:
        logger.info(f"Starting orchestrator listener on {ip}:{port}")
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        # allow fast rebinding
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.settimeout(1.0)

        try:
            server.bind((ip, port))
            server.listen(backlog)
            logger.info(f"Listener thread listening on {ip}:{port}")
        except Exception as e:
            logger.error(f"Failed to start listener on {ip}:{port}: {e}", exc_info=True)
            raise

        try:
            while not self.shutdown.is_set():
                try:
                    client_socket, addr = server.accept()
                    logger.debug(f"Accepted connection from {addr}")
                    threading.Thread(target=self.__handle_client, args=(client_socket, addr), daemon=True).start()
                except TimeoutError:
                    continue
                except Exception as e:
                    if not self.shutdown.is_set():
                        logger.error(f"Error accepting connection: {e}")
        finally:
            server.close()
            logger.info("Listener thread shutting down")
