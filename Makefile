.PHONY: restart-agent restart-bot restart-all status-agent status-bot status log-agent log-bot log install

AGENT_SERVICE = rav-spy-agent.service
BOT_SERVICE = rav-spy-bot.service

restart-agent:
	systemctl --user restart $(AGENT_SERVICE)

restart-bot:
	systemctl --user restart $(BOT_SERVICE)

restart-all: restart-agent restart-bot

stop-all:
	systemctl --user stop $(AGENT_SERVICE) $(BOT_SERVICE)

start-all:
	systemctl --user start $(AGENT_SERVICE) $(BOT_SERVICE)

status-agent:
	systemctl --user status $(AGENT_SERVICE)

status-bot:
	systemctl --user status $(BOT_SERVICE)

status:
	@echo "=== Agent ==="
	@systemctl --user is-active $(AGENT_SERVICE)
	@echo "=== Bot ==="
	@systemctl --user is-active $(BOT_SERVICE)

log-agent:
	journalctl --user -u $(AGENT_SERVICE) -n 50 -f

log-bot:
	journalctl --user -u $(BOT_SERVICE) -n 50 -f

log:
	journalctl --user -u $(AGENT_SERVICE) -u $(BOT_SERVICE) -n 50 -f

install:
	cp deploy/rav-spy-agent.service deploy/rav-spy-bot.service ~/.config/systemd/user/
	systemctl --user daemon-reload
	@echo "Done. Run: systemctl --user enable rav-spy-agent rav-spy-bot"
