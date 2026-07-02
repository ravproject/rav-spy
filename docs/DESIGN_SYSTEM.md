# RAV-SPY Design System & Architecture

## 1. Overview
RAV-SPY is a high-performance stealth laptop intelligence system designed for Ubuntu (Wayland/X11). It prioritizes user comfort (Zero-Flash), system stability, and security.

## 2. Core Features

### 📸 Smart Screenshot
*   **Method**: Flameshot RAW + GSettings Animation Toggle.
*   **User Comfort**: 100% Zero-Flash. System animations are temporarily disabled during capture to eliminate the white flash effect.
*   **Compatibility**: Works seamlessly on Wayland and X11 sessions.
*   **Delivery**: Instant delivery as high-quality PNG.

### 📹 High-Quality Video Recording (LOCKED)
*   **Architecture**: Stability-First Hybrid Capture.
*   **Frequency**: 6 FPS (Frames Per Second) - Balanced for typing smoothness and CPU load.
*   **Resolution**: HD (1280x720) with standard YUV420P pixel format.
*   **Zero-Flash Technology**: Bypasses OS visual indicators by capturing frames silently at the system level.
*   **Playback**: Optimized for Telegram/Mobile with `+faststart` metadata (No buffering).
*   **Safety**: Automatic restoration of system animations after recording.

### 💻 Interactive Terminal Mode
*   **Engine**: Pseudo-Terminal (PTY) emulation.
*   **Performance**: Real-time polling with asynchronous I/O.
*   **Security**: Restricted command execution via Sandbox.

### 🖼️ Webcam & Media
*   **Webcam Photo**: Instant JPG capture using `v4l2`.
*   **Webcam Video**: Real-time GStreamer pipeline with hardware-optimized encoding.
*   **System Monitoring**: Real-time CPU, RAM, and Disk metrics via `psutil`.

## 3. Engineering Standards

### 🛡️ Security Layers
1.  **Input Sanitization**: All commands are whitelisted and sanitized before execution.
2.  **Auth Manager**: OTP-based login with JWT session tokens.
3.  **Watchdog**: Real-time anomaly detection for CPU/RAM spikes and brute-force attempts.
4.  **Audit Logger**: Every action is cryptographically logged for traceability.

### ⚙️ Performance Standards
*   **Unblocking Event Loop**: All heavy operations (Video/Media/Files) MUST use `asyncio.to_thread`.
*   **Context Efficiency**: Minimum data transfer for maximum speed.
*   **Standard Encoding**: Always use H.264 Main/Baseline profiles for universal mobile compatibility.

## 4. Operational Protocols (REBUILD_FEATURE.md)
*   **Audit First**: Never rebuild existing features without a thorough audit.
*   **In-Place Fixes**: Prioritize fixing existing logic over creating new variants.
*   **MIME Integrity**: Always specify explicit MIME types and filenames for media delivery.

---
*Last Updated: Sunday, June 14, 2026*
