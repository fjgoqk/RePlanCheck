from .plan.concrete import SchemaAdaptedTool
from .schema.concrete import ConcreteToolBase


class SubstitutionApprovalError(ValueError):
    pass


def _schema_signature(schema: type | None) -> dict:
    if schema is None or not hasattr(schema, "model_json_schema"):
        return {}
    signature = schema.model_json_schema()
    signature.pop("title", None)
    return signature


def build_approved_substitutions(
    selected_tools: dict[str, ConcreteToolBase],
    recovery_catalog: dict[str, ConcreteToolBase],
    requested: dict[str, list[str]],
) -> dict[str, tuple[ConcreteToolBase, ...]]:
    """Adapt predeclared substitutes without consulting an LLM at recovery time."""

    approved: dict[str, tuple[ConcreteToolBase, ...]] = {}
    for abstract_tool, replacement_names in requested.items():
        selected = selected_tools.get(abstract_tool)
        if selected is None:
            raise SubstitutionApprovalError(f"Unknown abstract tool: {abstract_tool}")
        if not isinstance(selected, SchemaAdaptedTool):
            raise SubstitutionApprovalError(f"Selected tool for {abstract_tool} has no verified schema adapter")

        replacements = []
        for replacement_name in replacement_names:
            raw_replacement = recovery_catalog.get(replacement_name)
            if raw_replacement is None:
                raise SubstitutionApprovalError(f"Recovery tool is not preloaded: {replacement_name}")
            if raw_replacement.name == selected.name:
                raise SubstitutionApprovalError("Recovery tool must differ from the selected tool")
            if raw_replacement.clearances != selected.wrapped_tool.clearances:
                raise SubstitutionApprovalError(f"Recovery tool changes clearances: {replacement_name}")
            if not raw_replacement.permissions.issubset(selected.wrapped_tool.permissions):
                raise SubstitutionApprovalError(f"Recovery tool increases permissions: {replacement_name}")
            if _schema_signature(raw_replacement.args_schema) != _schema_signature(selected.wrapped_tool.args_schema):
                raise SubstitutionApprovalError(f"Recovery tool input schema differs: {replacement_name}")
            if _schema_signature(raw_replacement.output_schema) != _schema_signature(
                selected.wrapped_tool.output_schema
            ):
                raise SubstitutionApprovalError(f"Recovery tool output schema differs: {replacement_name}")

            replacements.append(
                SchemaAdaptedTool(
                    name=raw_replacement.name,
                    provider=raw_replacement.provider,
                    description=raw_replacement.description,
                    clearances=raw_replacement.clearances,
                    permissions=raw_replacement.permissions,
                    args_schema=selected.args_schema,
                    output_schema=selected.output_schema,
                    wrapped_tool=raw_replacement,
                    input_mapping_source=selected.input_mapping_source,
                    output_mapping_source=selected.output_mapping_source,
                )
            )
        approved[abstract_tool] = tuple(replacements)
    return approved
