#!/usr/bin/env node
/**
 * Unified Runner for rav-spy (Agent & Bots)
 */

const fs = require('fs');
const path = require('path');
const { spawn } = require('child_process');

const envPath = path.join(process.cwd(), '.env');

function logSystem(msg) {
  console.log(`\x1b[33m[System]\x1b[0m ${msg}`);
}

function logSystemError(msg) {
  console.error(`\x1b[31m[System Error]\x1b[0m ${msg}`);
}

async function quickDepCheck() {
  const scriptsDir = path.join(__dirname, 'scripts');
  const checkScript = path.join(scriptsDir, 'check_deps.js');
  if (!fs.existsSync(checkScript)) return;
  try {
    require('child_process').execSync(`node "${checkScript}"`, { stdio: 'inherit', timeout: 120000 });
  } catch {
    logSystemError('Beberapa dependency bermasalah. Jalankan "npm run check-deps" untuk detail.');
  }
}

async function main() {
  await quickDepCheck();

  if (!fs.existsSync(envPath)) {
    logSystem("File .env tidak ditemukan. Memulai setup interaktif...");
    const setupScript = path.join(__dirname, 'setup.js');
    if (!fs.existsSync(setupScript)) {
      logSystemError(`setup.js tidak ditemukan di ${setupScript}`);
      process.exit(1);
    }
    const setup = spawn('node', [setupScript], { stdio: 'inherit' });
    setup.on('close', (code) => {
      if (code === 0) {
        logSystem("Setup selesai. Menjalankan aplikasi...");
        // Check if .env was created in process.cwd()
        if (fs.existsSync(envPath)) {
          startApp();
        } else {
          logSystem("Setup selesai. Silakan masuk ke direktori instalasi Anda dan jalankan kembali command.");
          process.exit(0);
        }
      } else {
        logSystemError("Setup gagal.");
        process.exit(code);
      }
    });
  } else {
    startApp();
  }
}

function startApp() {
  logSystem("Memulai komponen rav-spy...");

  // Load environment variables using dotenv
  try {
    require('dotenv').config();
  } catch (err) {
    logSystem("dotenv tidak ditemukan, mencoba membaca .env secara manual...");
  }

  const pythonPath = process.platform === 'win32'
    ? path.join(process.cwd(), 'venv', 'Scripts', 'python.exe')
    : path.join(process.cwd(), 'venv', 'bin', 'python');

  if (!fs.existsSync(pythonPath)) {
    logSystemError(`Virtual environment tidak ditemukan di ${pythonPath}. Silakan jalankan setup terlebih dahulu.`);
    process.exit(1);
  }

  const processes = [];
  let isShuttingDown = false;

  function cleanShutdown() {
    if (isShuttingDown) return;
    isShuttingDown = true;
    logSystem("Menghentikan semua komponen...");
    processes.forEach((p) => {
      try {
        if (!p.killed) {
          p.kill('SIGINT');
        }
      } catch (err) {
        // ignore
      }
    });
    setTimeout(() => {
      process.exit(0);
    }, 1000);
  }

  process.on('SIGINT', cleanShutdown);
  process.on('SIGTERM', cleanShutdown);

  function startProcess(name, cmd, args, prefixColor) {
    logSystem(`Memulai ${name}...`);
    const p = spawn(cmd, args, { 
      cwd: process.cwd(),
      env: process.env
    });
    processes.push(p);

    const prefix = `${prefixColor}[${name}]\x1b[0m`;

    p.stdout.on('data', (data) => {
      if (isShuttingDown) return;
      const lines = data.toString().trim().split('\n');
      lines.forEach((line) => {
        if (line) console.log(`${prefix} ${line}`);
      });
    });

    p.stderr.on('data', (data) => {
      if (isShuttingDown) return;
      const lines = data.toString().trim().split('\n');
      lines.forEach((line) => {
        if (line) console.error(`${prefix} \x1b[31m${line}\x1b[0m`);
      });
    });

    p.on('error', (err) => {
      logSystemError(`Gagal memulai ${name}: ${err.message}`);
      cleanShutdown();
    });

    p.on('close', (code) => {
      if (!isShuttingDown) {
        logSystemError(`${name} berhenti dengan kode keluar ${code}`);
        cleanShutdown();
      }
    });
  }

  // Start Agent
  startProcess('Agent', pythonPath, ['-m', 'agent.main'], '\x1b[36m');

  const ravMode = (process.env.RAV_MODE || 'hub').toLowerCase();

  if (ravMode === 'agent') {
    logSystem(`Mode Agent — hub: ${process.env.HUB_URL || '(belum dikonfigurasi)'}`);
    logSystem('Agent akan mendaftar otomatis ke hub saat startup.');
    return;
  }

  // Start Telegram Bot if token is configured (hub mode)
  const botToken = process.env.TELEGRAM_BOT_TOKEN;
  if (botToken && botToken !== 'your_telegram_bot_token_here' && botToken.trim() !== '') {
    startProcess('Telegram Bot', pythonPath, ['-m', 'bot.telegram_bot'], '\x1b[35m');
  } else {
    logSystem("TELEGRAM_BOT_TOKEN belum dikonfigurasi atau masih default. Telegram Bot tidak dijalankan.");
  }

  // Start WhatsApp Bot if flag --whatsapp or -wa is passed
  const runWhatsApp = process.argv.includes('--whatsapp') || process.argv.includes('-wa');
  if (runWhatsApp) {
    // Check if node_modules is installed
    if (!fs.existsSync(path.join(process.cwd(), 'node_modules'))) {
      logSystem("Menginstal dependensi Node.js untuk WhatsApp...");
      try {
        require('child_process').execSync('npm install', { stdio: 'inherit' });
      } catch (err) {
        logSystemError("Gagal menginstal dependensi Node.js.");
      }
    }
    startProcess('WhatsApp Bot', 'node', [path.join('bot', 'whatsapp_bot.js')], '\x1b[32m');
  }
}

main();
