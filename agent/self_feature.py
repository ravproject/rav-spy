"""
Self-Feature Generation & Safe Auto Development.
Memanfaatkan NIM AI untuk generate fitur baru secara aman.
"""
import os
import json
import re
import sys
import shutil
import subprocess
import httpx
from datetime import datetime
from pathlib import Path
from loguru import logger

FEATURES_DIR = Path.home() / ".config" / "rav-spy" / "features"
BACKUP_DIR = Path.home() / ".config" / "rav-spy" / "backups"
FEATURES_REGISTRY = FEATURES_DIR / "registry.json"

FEATURE_GEN_PROMPT = """You are an expert Python developer for RAV-SPY (stealth laptop intelligence via Telegram/WhatsApp).
Generate a complete new feature implementation based on the user's request.

The system architecture is:
- Handler method in agent/command_handler.py (add new method handle_{feature_name})
- Route entry in bot/command_router.py (elif command_name == "{feature_name}":)
- Whitelist entry in config/allowed_commands.yaml
- Alias in ai_module/fallback_parser.py COMMAND_MAP

You must respond with ONLY a JSON object:
{{
  "feature_name": "snake_case_name",
  "handler_code": "complete async def handle_<name> method code",
  "router_code": "the elif block for bot/command_router.py",
  "yaml_entry": "YAML entry for config/allowed_commands.yaml",
  "fallback_entry": "COMMAND_MAP entry line",
  "description": "Short description",
  "dependencies": ["list", "of", "pip", "packages"] or []
}}

RULES:
- Handler must follow existing patterns (async, self.auditor.log_event)
- Must be safe: no destructive commands, no shell injection
- Max 200 lines of code per feature
"""


class SelfFeatureEngine:
    def __init__(self):
        self.nim_api_key = os.environ.get("NVIDIA_NIM_API_KEY", "")
        self.nim_base = os.environ.get(
            "NVIDIA_NIM_BASE_URL",
            "https://integrate.api.nvidia.com/v1",
        )
        self.nim_model = os.environ.get("NVIDIA_NIM_MODEL", "meta/llama-3.1-70b-instruct")
        FEATURES_DIR.mkdir(parents=True, exist_ok=True)
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        self._load_registry()

    def _load_registry(self):
        if FEATURES_REGISTRY.exists():
            with open(FEATURES_REGISTRY) as f:
                self.registry = json.load(f)
        else:
            self.registry = {"features": [], "generated_count": 0}

    def _save_registry(self):
        FEATURES_DIR.mkdir(parents=True, exist_ok=True)
        with open(FEATURES_REGISTRY, "w") as f:
            json.dump(self.registry, f, indent=2)

    async def generate_feature(self, description: str) -> dict:
        existing_cmds = set()
        try:
            from ai_module.fallback_parser import FallbackParser
            existing_cmds = set(FallbackParser.COMMAND_MAP.keys())
        except Exception:
            pass

        result = await self._call_nim_generate(description)
        if not result:
            return {"error": "Gagal generate fitur dari AI."}

        errors = self._validate_generated(result)
        if errors:
            return {"error": f"Validasi gagal: {', '.join(errors)}"}

        cmd_name = f"!{result['feature_name']}"
        if cmd_name in existing_cmds:
            return {"error": f"Perintah `{cmd_name}` sudah ada."}

        return result

    async def _call_nim_generate(self, description: str) -> dict | None:
        headers = {
            "Authorization": f"Bearer {self.nim_api_key}",
            "Content-Type": "application/json",
        }
        try:
            async with httpx.AsyncClient(timeout=120) as client:
                resp = await client.post(
                    f"{self.nim_base}/chat/completions",
                    headers=headers,
                    json={
                        "model": self.nim_model,
                        "messages": [
                            {"role": "system", "content": FEATURE_GEN_PROMPT},
                            {"role": "user", "content": description[:1000]},
                        ],
                        "max_tokens": 4096,
                        "temperature": 0.2,
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                raw = data["choices"][0]["message"]["content"]
                json_match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', raw, re.DOTALL)
                if json_match:
                    raw = json_match.group(1)
                return json.loads(raw)
        except Exception as e:
            logger.error(f"Feature generation failed: {e}")
            return None

    def _validate_generated(self, result: dict) -> list[str]:
        errors = []
        for field in ["feature_name", "handler_code", "router_code", "yaml_entry"]:
            if field not in result:
                errors.append(f"Missing field: {field}")
        if not errors:
            handler = result.get("handler_code", "")
            if "async def handle_" not in handler:
                errors.append("Handler code must contain 'async def handle_'")
        return errors

    def backup_current_files(self) -> str:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = BACKUP_DIR / ts
        backup_path.mkdir(parents=True, exist_ok=True)
        files = [
            "agent/command_handler.py",
            "bot/command_router.py",
            "config/allowed_commands.yaml",
            "ai_module/fallback_parser.py",
        ]
        for rel in files:
            src = Path.cwd() / rel
            if src.exists():
                shutil.copy2(src, backup_path / rel)
        return str(backup_path)

    async def install_feature(self, feature_data: dict, user_id: str) -> str:
        backup_path = self.backup_current_files()
        self._inject_handler(feature_data["handler_code"])
        self._inject_router(feature_data["feature_name"], feature_data.get("router_code", ""))
        if feature_data.get("yaml_entry"):
            self._inject_yaml(feature_data["feature_name"], feature_data["yaml_entry"])
        if feature_data.get("fallback_entry"):
            self._inject_fallback(feature_data["fallback_entry"])

        self.registry["features"].append({
            "name": feature_data["feature_name"],
            "description": feature_data.get("description", ""),
            "installed_at": datetime.now().isoformat(),
            "backup": backup_path,
            "installed_by": user_id,
        })
        self.registry["generated_count"] += 1
        self._save_registry()

        try:
            subprocess.run(
                [sys.executable, "-m", "py_compile", "agent/command_handler.py"],
                capture_output=True, text=True, check=True, timeout=10,
            )
        except subprocess.CalledProcessError as e:
            return f"❌ Syntax error: {e.stderr[:500]}\nBackup: {backup_path}"

        return (
            f"✅ Fitur `{feature_data['feature_name']}` berhasil diinstal!\n"
            f"📝 {feature_data.get('description', '')}\n"
            f"🔙 Backup: {backup_path}\n"
            f"⚠️ Restart agent untuk mengaktifkan."
        )

    def _inject_handler(self, code: str):
        path = Path.cwd() / "agent" / "command_handler.py"
        content = path.read_text()
        lines = content.split("\n")
        last_method = 0
        for i, line in enumerate(lines):
            if line.strip().startswith("async def handle_"):
                last_method = i
        for i in range(last_method, len(lines)):
            if lines[i].strip() == "":
                last_method = i
                break
        indented = "\n".join(f"    {line}" if line.strip() else "" for line in code.split("\n"))
        lines.insert(last_method + 1, indented)
        path.write_text("\n".join(lines))
        logger.info(f"Handler injected: {len(code)} chars")

    def _inject_router(self, feature_name: str, code: str):
        path = Path.cwd() / "bot" / "command_router.py"
        content = path.read_text()
        marker = '            elif command_name == "help":'
        indented = "\n".join(f"            {line}" if line.strip() else "" for line in code.split("\n"))
        content = content.replace(marker, f"{indented}\n\n            {marker}")
        path.write_text(content)

    def _inject_yaml(self, feature_name: str, yaml_text: str):
        path = Path.cwd() / "config" / "allowed_commands.yaml"
        content = path.read_text()
        marker = "\nblocked_patterns:"
        entry = f"\n  {feature_name}:\n    description: \"Auto-generated\"\n    requires_confirmation: false\n    sandbox_required: false\n"
        content = content.replace(marker, entry + marker)
        path.write_text(content)

    def _inject_fallback(self, entry_text: str):
        path = Path.cwd() / "ai_module" / "fallback_parser.py"
        content = path.read_text()
        marker = "COMMAND_MAP = {"
        content = content.replace(marker, f"{marker}\n{entry_text},", 1)
        path.write_text(content)

    def list_features(self) -> list[dict]:
        return self.registry.get("features", [])


self_feature_engine = SelfFeatureEngine()
