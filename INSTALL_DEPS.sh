#!/bin/bash
set -e

echo "============================================"
echo "  RAV-SPY — Install Semua Dependencies"
echo "============================================"
echo ""

# ── 1. Python Packages ────────────────────────────────────────────
echo "▸ Menginstall Python packages yang belum ada..."

source venv/bin/activate 2>/dev/null || source .venv/bin/activate 2>/dev/null || true

pip install --quiet \
  edge-tts \
  google-api-python-client \
  google-auth-httplib2 \
  google-auth-oauthlib \
  pulsectl \
  pyaudio 2>/dev/null

echo "  ✔ Python packages selesai."
echo ""

# ── 2. System Packages ────────────────────────────────────────────
echo "▸ Menginstall system packages (butuh sudo)..."

# Core — wajib untuk fitur dasar
sudo apt install -y -qq \
  xdotool \
  wmctrl \
  x11-utils \
  wl-clipboard \
  xclip \
  xsel \
  ffmpeg \
  pandoc \
  openssh-client \
  brightnessctl \
  libnotify-bin \
  alsa-utils \
  util-linux \
  iproute2 \
  net-tools \
  lsof \
  iputils-ping \
  dbus-x11 2>/dev/null

# Media — screenshot, playback
sudo apt install -y -qq \
  gnome-screenshot \
  scrot \
  imagemagick \
  mpg123 \
  mpv \
  pulseaudio-utils \
  vlc-bin \
  speech-dispatcher \
  espeak 2>/dev/null

# Sistem — power, network, display
sudo apt install -y -qq \
  power-profiles-daemon \
  network-manager \
  x11-xserver-utils \
  flameshot 2>/dev/null

# Blue light filter (opsional)
sudo apt install -y -qq redshift gammastep 2>/dev/null || true

# Speedtest (opsional)
sudo apt install -y -qq speedtest-cli 2>/dev/null || true

# GStreamer untuk webcam (opsional)
sudo apt install -y -qq \
  gstreamer1.0-tools \
  gstreamer1.0-plugins-good \
  gstreamer1.0-plugins-bad \
  gstreamer1.0-libav 2>/dev/null || true

echo "  ✔ System packages selesai."
echo ""

# ── 3. rclone (mungkin gak ada di repo default) ───────────────────
if ! command -v rclone &>/dev/null; then
  echo "▸ Install rclone..."
  sudo -v
  curl -s https://rclone.org/install.sh | sudo bash 2>/dev/null || \
    sudo apt install -y rclone 2>/dev/null || \
    echo "  ⚠ rclone gagal diinstall, !sync gdrive mungkin gak jalan"
fi

echo ""
echo "============================================"
echo "  ✅ Semua dependencies selesai!"
echo "============================================"
echo ""
echo "Cek yang masih kurang:"
echo "  which xdotool wmctrl xrandr nmcli ffmpeg pandoc ssh \\"
echo "       notify-send brightnessctl powerprofilesctl rclone \\"
echo "       gnome-screenshot scrot import redshift rtcwake"
echo ""
