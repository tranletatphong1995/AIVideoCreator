"""Text model providers for local Ollama and optional ima2-gen ChatGPT mode."""

from typing import Optional

import requests

from module_ima2_runtime import resolve_ima2_oauth_url


class LocalOllamaTextProvider:
    provider_name = "ollama"

    def __init__(self, model_name: str):
        self.model_name = model_name

    def chat(self, messages, options: Optional[dict] = None, model: Optional[str] = None):
        import ollama

        return ollama.chat(
            model=model or self.model_name,
            messages=messages,
            options=options or {},
        )


class Ima2ChatGPTTextProvider:
    provider_name = "ima2-chatgpt"

    def __init__(
        self,
        model_name: str = "gpt-5.4-mini",
        server_url: str = "",
        reasoning_effort: str = "low",
        timeout_sec: int = 240,
    ):
        self.model_name = model_name or "gpt-5.4-mini"
        self.server_url = server_url or ""
        self.reasoning_effort = reasoning_effort or "low"
        self.timeout_sec = timeout_sec

    def _extract_text(self, data) -> str:
        if isinstance(data, dict):
            if isinstance(data.get("output_text"), str):
                return data["output_text"]
            output = data.get("output")
            if isinstance(output, list):
                for item in output:
                    if not isinstance(item, dict):
                        continue
                    content = item.get("content")
                    if not isinstance(content, list):
                        continue
                    for block in content:
                        if not isinstance(block, dict):
                            continue
                        for key in ("text", "value"):
                            value = block.get(key)
                            if isinstance(value, str):
                                return value
            choices = data.get("choices")
            if isinstance(choices, list) and choices:
                message = choices[0].get("message") if isinstance(choices[0], dict) else None
                if isinstance(message, dict) and isinstance(message.get("content"), str):
                    return message["content"]
        return ""

    def _wants_json(self, messages) -> bool:
        text = "\n".join(
            str(message.get("content", ""))
            for message in messages
            if isinstance(message, dict)
        ).lower()
        return "json" in text

    def _post_chat_completions(self, oauth_url: str, messages, active_model: str):
        body = {
            "model": active_model,
            "messages": messages,
        }
        if self._wants_json(messages):
            body["response_format"] = {"type": "json_object"}

        response = requests.post(
            f"{oauth_url}/v1/chat/completions",
            json=body,
            timeout=self.timeout_sec,
        )
        if response.status_code == 401:
            raise RuntimeError("ChatGPT OAuth expired. Run: npx --yes @openai/codex login")
        response.raise_for_status()
        text = self._extract_text(response.json())
        if not text:
            raise RuntimeError("ChatGPT returned an empty chat/completions response.")
        return {"message": {"content": text}}

    def _post_responses(self, oauth_url: str, messages, active_model: str, options: Optional[dict] = None):
        max_tokens = None
        if isinstance(options, dict):
            max_tokens = options.get("num_predict") or options.get("max_tokens")

        body = {
            "model": active_model,
            "input": messages,
            "stream": False,
            "reasoning": {"effort": self.reasoning_effort},
        }
        if max_tokens:
            body["max_output_tokens"] = int(max_tokens)

        response = requests.post(
            f"{oauth_url}/v1/responses",
            json=body,
            timeout=self.timeout_sec,
        )
        if response.status_code == 401:
            raise RuntimeError("ChatGPT OAuth expired. Run: npx --yes @openai/codex login")
        if response.status_code == 404:
            raise RuntimeError("ima2 OAuth proxy is not ready. Start ima2-gen first.")
        response.raise_for_status()

        text = self._extract_text(response.json())
        if not text:
            raise RuntimeError("ChatGPT returned an empty text response.")
        return {"message": {"content": text}}

    def chat(self, messages, options: Optional[dict] = None, model: Optional[str] = None):
        oauth_url = resolve_ima2_oauth_url(self.server_url)
        active_model = model or self.model_name
        try:
            return self._post_chat_completions(oauth_url, messages, active_model)
        except Exception as chat_error:
            try:
                return self._post_responses(oauth_url, messages, active_model, options)
            except Exception:
                raise chat_error
