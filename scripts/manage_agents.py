#!/usr/bin/env python3
"""
CLI fleet & agent registry.

Registrasi agent tetap manual via `add` (dijalankan di hub).
Setup .env di komputer tambahan TIDAK perlu manual — pakai `init-agent`.

Usage:
  python scripts/manage_agents.py list
  python scripts/manage_agents.py add <agent_id> <host> <port> <api_key>
  python scripts/manage_agents.py remove <agent_id>

  # Hub — tampilkan kode pairing (salin ke komputer lain):
  python scripts/manage_agents.py pairing-code

  # Komputer tambahan — buat .env otomatis dari kode pairing:
  python scripts/manage_agents.py init-agent <SPY1.xxxxx>
"""
import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

load_dotenv()

from bot.agent_registry import registry
from bot.fleet_pairing import (
    build_agent_env,
    decode_pairing_code,
    detect_lan_ip,
    format_add_command,
    pairing_code_from_env,
    sanitize_agent_id,
    write_env_file,
)


def print_help():
    print("RAV-SPY Agent Manager")
    print()
    print("Registry (jalankan di HUB):")
    print("  python scripts/manage_agents.py list")
    print("  python scripts/manage_agents.py add <agent_id> <host> <port> <api_key>")
    print("  python scripts/manage_agents.py remove <agent_id>")
    print()
    print("Fleet — hindari setup .env manual:")
    print("  python scripts/manage_agents.py pairing-code          # hub: tampilkan kode SPY1.*")
    print("  python scripts/manage_agents.py init-agent <kode>     # agent: buat .env otomatis")
    print()
    print("Alur multi-komputer:")
    print("  1. Hub: setup + npm start")
    print("  2. Hub: pairing-code → salin kode")
    print("  3. Laptop lain: init-agent <kode> → npm start")
    print("  4. Hub: add <agent_id> <ip> <port> <api_key>  (perintah ditampilkan setelah init-agent)")


def cmd_list():
    agents = registry.get_all()
    if not agents:
        print("Belum ada agent terdaftar.")
        return
    print(f"Agent terdaftar ({len(agents)}):")
    for agent_id, data in agents.items():
        print(f"  [{agent_id}] → http://{data['host']}:{data['port']}")


def cmd_add(argv: list[str]):
    if len(argv) != 5:
        print("Usage: python scripts/manage_agents.py add <agent_id> <host> <port> <api_key>")
        sys.exit(1)
    _, agent_id, host, port_s, api_key = argv
    try:
        port = int(port_s)
    except ValueError:
        print("Error: port harus angka.")
        sys.exit(1)
    registry.add_agent(agent_id, host, port, api_key)
    print(f"✅ Agent '{agent_id}' terdaftar → http://{host}:{port}")


def cmd_remove(argv: list[str]):
    if len(argv) != 2:
        print("Usage: python scripts/manage_agents.py remove <agent_id>")
        sys.exit(1)
    agent_id = argv[1]
    if registry.remove_agent(agent_id):
        print(f"✅ Agent '{agent_id}' dihapus.")
    else:
        print(f"Agent '{agent_id}' tidak ditemukan.")
        sys.exit(1)


def cmd_pairing_code():
    if os.environ.get("RAV_MODE", "hub") == "agent":
        print("pairing-code hanya dijalankan di mesin hub.", file=sys.stderr)
        sys.exit(1)
    code = pairing_code_from_env()
    out_path = Path.cwd() / ".fleet-pairing-code"
    out_path.write_text(code + "\n")
    os.chmod(out_path, 0o600)
    print("Kode pairing (salin ke komputer tambahan):\n")
    print(code)
    print(f"\nDisimpan di: {out_path}")
    print("\nDi laptop lain:")
    print("  python scripts/manage_agents.py init-agent <kode-di-atas>")


def cmd_init_agent(argv: list[str]):
    if len(argv) != 2:
        print("Usage: python scripts/manage_agents.py init-agent <SPY1.xxxxx>")
        sys.exit(1)
    code = argv[1]
    try:
        pairing = decode_pairing_code(code)
    except Exception as e:
        print(f"Kode pairing tidak valid: {e}", file=sys.stderr)
        sys.exit(1)

    import platform

    agent_id = sanitize_agent_id(platform.node())
    env = build_agent_env(pairing, agent_id=agent_id)
    env_path = write_env_file(env)

    ip = detect_lan_ip()
    port = int(env["AGENT_PORT"])
    api_key = env["AGENT_API_KEY"]
    add_cmd = format_add_command(agent_id, api_key, ip, port)

    print(f"✅ .env agent dibuat: {env_path}")
    print(f"   Agent ID : {agent_id}")
    print(f"   IP lokal : {ip}")
    print(f"   API Key  : {api_key}")
    print()
    print("Langkah berikutnya:")
    print("  1. Di komputer ini : npm start")
    print("  2. Di HUB, jalankan:")
    print(f"     {add_cmd}")


def main():
    if len(sys.argv) < 2:
        print_help()
        sys.exit(1)

    command = sys.argv[1].lower()
    handlers = {
        "list": lambda: cmd_list(),
        "add": lambda: cmd_add(sys.argv),
        "remove": lambda: cmd_remove(sys.argv),
        "pairing-code": cmd_pairing_code,
        "pairing": cmd_pairing_code,
        "init-agent": lambda: cmd_init_agent(sys.argv),
        "init": lambda: cmd_init_agent(sys.argv),
        "help": print_help,
    }

    handler = handlers.get(command)
    if not handler:
        print_help()
        sys.exit(1)
    handler()


if __name__ == "__main__":
    main()
