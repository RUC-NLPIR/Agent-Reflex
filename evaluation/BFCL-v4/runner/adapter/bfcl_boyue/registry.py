from __future__ import annotations

from .config import CONTRACTS


def register_models(mapping=None, model_config_cls=None, handler_cls=None):
    if mapping is None or model_config_cls is None:
        from bfcl_eval.constants.model_config import MODEL_CONFIG_MAPPING, ModelConfig

        mapping = MODEL_CONFIG_MAPPING if mapping is None else mapping
        model_config_cls = ModelConfig if model_config_cls is None else model_config_cls

    if handler_cls is None:
        from .handler import BoyueOpenAICompletionsHandler

        handler_cls = BoyueOpenAICompletionsHandler

    created = {}
    for registry_id, contract in CONTRACTS.items():
        value = model_config_cls(
            model_name=contract.request_model,
            display_name=contract.display_name,
            url=contract.base_url,
            org=contract.organization,
            license="Proprietary",
            model_handler=handler_cls,
            input_price=None,
            output_price=None,
            is_fc_model=True,
            underscore_to_dot=True,
        )
        existing = mapping.get(registry_id)
        if existing is not None and existing != value:
            raise RuntimeError(f"registry conflict for {registry_id}")
        mapping[registry_id] = value
        created[registry_id] = value
    return created
