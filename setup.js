#!/usr/bin/env node
/**
 * Setup rav-spy — mode Hub (Telegram + bot) atau Agent (komputer tambahan).
 *
 * Usage:
 *   npm run setup              # wizard interaktif
 *   npm run setup:hub          # mode hub
 *   npm run setup:agent        # mode agent (paste kode pairing)
 *   node setup.js --agent --pair=SPY1.xxxxx
 */

const readline = require('readline');
const fs = require('fs');
const path = require('path');
const os = require('os');
const { execSync } = require('child_process');
const crypto = require('crypto');

const rl = readline.createInterface({ input: process.stdin, output: process.stdout });
const question = (q) => new Promise((resolve) => rl.question(q, resolve));

const PAIR_PREFIX = 'SPY1.';

function parseArgs(argv) {
  const args = { mode: null, pair: null };
  for (const a of argv) {
    if (a === '--hub') args.mode = 'hub';
    else if (a === '--agent') args.mode = 'agent';
    else if (a.startsWith('--pair=')) args.pair = a.slice('--pair='.length).trim();
  }
  return args;
}

function copyRecursiveSync(src, dest) {
  if (!fs.existsSync(src)) return;
  const stats = fs.statSync(src);
  if (stats.isDirectory()) {
    if (!fs.existsSync(dest)) fs.mkdirSync(dest, { recursive: true });
    for (const name of fs.readdirSync(src)) {
      copyRecursiveSync(path.join(src, name), path.join(dest, name));
    }
    return;
  }
  if (!['setup.js', 'package-lock.json'].includes(path.basename(src))) {
    fs.copyFileSync(src, dest);
  }
}

function parseEnvFile(content) {
  const env = {};
  content.split('\n').forEach((line) => {
    const match = line.match(/^\s*([\w.-]+)\s*=\s*(.*)?\s*$/);
    if (!match) return;
    let val = match[2] || '';
    if (val.startsWith('"') && val.endsWith('"')) val = val.slice(1, -1);
    env[match[1]] = val.trim();
  });
  return env;
}

function getLanIp() {
  const nets = os.networkInterfaces();
  for (const ifaces of Object.values(nets)) {
    for (const net of ifaces) {
      if (net.family === 'IPv4' && !net.internal) return net.address;
    }
  }
  return '127.0.0.1';
}

function sanitizeAgentId(name) {
  return (name || 'agent')
    .replace(/[^a-zA-Z0-9_-]/g, '-')
    .replace(/-+/g, '-')
    .slice(0, 32) || 'agent';
}

function generateBase32(len = 16) {
  const chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ234567';
  let out = '';
  for (let i = 0; i < len; i++) out += chars.charAt(Math.floor(Math.random() * chars.length));
  return out;
}

function encodePairingCode(payload) {
  return PAIR_PREFIX + Buffer.from(JSON.stringify(payload)).toString('base64url');
}

function decodePairingCode(code) {
  const trimmed = code.trim();
  if (!trimmed.startsWith(PAIR_PREFIX)) {
    throw new Error('Kode pairing harus diawali SPY1.');
  }
  const raw = trimmed.slice(PAIR_PREFIX.length);
  return JSON.parse(Buffer.from(raw, 'base64url').toString('utf8'));
}

function buildEnvLines(entries) {
  return Object.entries(entries)
    .map(([k, v]) => `${k}=${v ?? ''}`)
    .join('\n') + '\n';
}

async function questionWithDefault(prompt, defaultVal) {
  if (defaultVal && String(defaultVal).trim() !== '') {
    const display =
      String(defaultVal).length > 25
        ? `${String(defaultVal).slice(0, 5)}...${String(defaultVal).slice(-5)}`
        : defaultVal;
    const answer = await question(`${prompt.replace(/:\s*$/, '')} [Default: ${display}]: `);
    return answer.trim() === '' ? defaultVal : answer.trim();
  }
  return (await question(prompt)).trim();
}

async function chooseMode(cliMode) {
  if (cliMode) return cliMode;
  console.log('\nPilih mode instalasi:');
  console.log('  1) Hub     — komputer utama + Telegram Bot (PC pertama / server)');
  console.log('  2) Agent   — laptop/komputer tambahan (cukup paste kode pairing)\n');
  const choice = await question('Pilihan [1/2]: ');
  return choice.trim() === '2' ? 'agent' : 'hub';
}

async function setupHub(absoluteTargetDir, existingEnv) {
  console.log('\n--- Setup Hub (Komputer Utama) ---\n');

  const botToken = await questionWithDefault('Telegram Bot Token (@BotFather): ', existingEnv.TELEGRAM_BOT_TOKEN);
  const userIds = await questionWithDefault('Telegram User ID (@userinfobot): ', existingEnv.ALLOWED_USER_IDS);

  const defaultAi = existingEnv.AI_MODE_ENABLED === 'true' ? 'y' : existingEnv.AI_MODE_ENABLED === 'false' ? 'n' : 'n';
  const enableAi = (await questionWithDefault('Aktifkan AI NVIDIA NIM? (y/n): ', defaultAi)).toLowerCase() === 'y';
  let nimApiKey = existingEnv.NVIDIA_NIM_API_KEY || '';
  if (enableAi) {
    nimApiKey = await questionWithDefault('NVIDIA NIM API Key: ', nimApiKey);
  }

  const otpSecret = existingEnv.OTP_SECRET_KEY || generateBase32();
  const isNewOtp = !existingEnv.OTP_SECRET_KEY;
  if (isNewOtp) {
    console.log(`\n🔐 OTP Secret (Google Authenticator): \x1b[32m${otpSecret}\x1b[0m`);
    await question('Tekan Enter setelah disimpan di Authenticator...');
  }

  const jwtSecret = existingEnv.JWT_SECRET_KEY || crypto.randomBytes(32).toString('hex');
  const encryptionKey = existingEnv.ENCRYPTION_KEY || crypto.randomBytes(32).toString('base64url');
  const fleetPairingKey = existingEnv.FLEET_PAIRING_KEY || crypto.randomBytes(24).toString('base64url');
  const agentApiKey = existingEnv.AGENT_API_KEY || crypto.randomBytes(32).toString('base64url');
  const agentId = existingEnv.AGENT_ID || sanitizeAgentId(os.hostname());
  const lanIp = getLanIp();
  const hubUrl = existingEnv.HUB_URL || `http://${lanIp}:8765`;

  const env = {
    RAV_MODE: 'hub',
    TELEGRAM_BOT_TOKEN: botToken,
    WHATSAPP_SESSION_PATH: './sessions/wa_session',
    OTP_SECRET_KEY: otpSecret,
    JWT_SECRET_KEY: jwtSecret,
    ALLOWED_USER_IDS: userIds,
    ENCRYPTION_KEY: encryptionKey,
    FLEET_PAIRING_KEY: fleetPairingKey,
    HUB_URL: hubUrl,
    AGENT_ID: agentId,
    AGENT_HOST: 'localhost',
    AGENT_PORT: '8765',
    AGENT_BIND_HOST: '0.0.0.0',
    AGENT_API_KEY: agentApiKey,
    NVIDIA_NIM_API_KEY: nimApiKey,
    AI_MODE_ENABLED: enableAi ? 'true' : 'false',
    MAX_COMMANDS_PER_MINUTE: '10',
    MAX_FILE_SIZE_MB: '50',
    LOG_LEVEL: 'INFO',
    LOG_FILE: './logs/audit.log',
  };

  const pairingPayload = {
    v: 1,
    hub: hubUrl,
    fk: fleetPairingKey,
    otp: otpSecret,
    jwt: jwtSecret,
    enc: encryptionKey,
    uid: userIds,
  };
  const pairingCode = encodePairingCode(pairingPayload);

  return { env, pairingCode, agentId };
}

async function setupAgent(absoluteTargetDir, existingEnv, cliPair) {
  console.log('\n--- Setup Agent (Komputer Tambahan) ---\n');
  console.log('Salin kode pairing dari komputer Hub (ditampilkan saat setup hub).\n');

  let pairCode = cliPair;
  if (!pairCode) {
    pairCode = await question('Paste kode pairing (SPY1....): ');
  }

  let payload;
  try {
    payload = decodePairingCode(pairCode);
  } catch (err) {
    throw new Error(`Kode pairing tidak valid: ${err.message}`);
  }

  const agentId = existingEnv.AGENT_ID || sanitizeAgentId(os.hostname());
  const agentApiKey = existingEnv.AGENT_API_KEY || crypto.randomBytes(32).toString('base64url');

  const env = {
    RAV_MODE: 'agent',
    TELEGRAM_BOT_TOKEN: '',
    WHATSAPP_SESSION_PATH: './sessions/wa_session',
    OTP_SECRET_KEY: payload.otp,
    JWT_SECRET_KEY: payload.jwt,
    ALLOWED_USER_IDS: payload.uid,
    ENCRYPTION_KEY: payload.enc,
    FLEET_PAIRING_KEY: payload.fk,
    HUB_URL: payload.hub,
    AGENT_ID: agentId,
    AGENT_HOST: 'localhost',
    AGENT_PORT: '8765',
    AGENT_BIND_HOST: '0.0.0.0',
    AGENT_API_KEY: agentApiKey,
    NVIDIA_NIM_API_KEY: existingEnv.NVIDIA_NIM_API_KEY || '',
    AI_MODE_ENABLED: existingEnv.AI_MODE_ENABLED || 'false',
    MAX_COMMANDS_PER_MINUTE: '10',
    MAX_FILE_SIZE_MB: '50',
    LOG_LEVEL: 'INFO',
    LOG_FILE: './logs/audit.log',
  };

  return { env, agentId, hubUrl: payload.hub };
}

function installPythonDeps(absoluteTargetDir) {
  console.log('\n⏳ Menginstal dependensi Python...');
  process.chdir(absoluteTargetDir);
  const pipCmd = process.platform === 'win32' ? 'venv\\Scripts\\pip' : 'venv/bin/pip';
  const pythonCmd = process.platform === 'win32' ? 'venv\\Scripts\\python' : 'venv/bin/python';

  execSync('python3 -m venv venv', { stdio: 'inherit' });
  execSync(`${pipCmd} install -r requirements.txt`, { stdio: 'inherit' });
  console.log('✅ Dependensi Python selesai.');
  return pythonCmd;
}

function registerLocalAgent(pythonCmd, absoluteTargetDir) {
  try {
    execSync(`"${pythonCmd}" scripts/fleet_helper.py register-local`, {
      cwd: absoluteTargetDir,
      stdio: 'inherit',
      env: { ...process.env, ...parseEnvFile(fs.readFileSync(path.join(absoluteTargetDir, '.env'), 'utf8')) },
    });
  } catch {
    console.warn('⚠️ Registrasi agent lokal gagal — akan dicoba lagi saat npm start.');
  }
}

async function main() {
  const cli = parseArgs(process.argv.slice(2));

  console.log('===========================================');
  console.log('🚀 RAV-SPY Setup');
  console.log('===========================================');

  const targetFolder =
    (await question('\nFolder instalasi (Enter = folder ini): ')) || '.';
  const absoluteTargetDir = path.resolve(process.cwd(), targetFolder);
  if (!fs.existsSync(absoluteTargetDir)) fs.mkdirSync(absoluteTargetDir, { recursive: true });

  const envPath = path.join(absoluteTargetDir, '.env');
  const existingEnv = fs.existsSync(envPath) ? parseEnvFile(fs.readFileSync(envPath, 'utf8')) : {};

  console.log(`\n⏳ Menyiapkan file di ${absoluteTargetDir}...`);
  const sourceDir = __dirname;
  for (const item of [
    'agent', 'bot', 'ai_module', 'security', 'config', 'docker', 'tests', 'scripts',
    'requirements.txt', 'package.json', 'README.md', 'docs', 'run.js',
  ]) {
    copyRecursiveSync(path.join(sourceDir, item), path.join(absoluteTargetDir, item));
  }
  console.log('✅ File aplikasi siap.');

  const mode = await chooseMode(cli.mode);
  let result;

  if (mode === 'agent') {
    result = await setupAgent(absoluteTargetDir, existingEnv, cli.pair);
    fs.writeFileSync(envPath, buildEnvLines(result.env));
    console.log('\n✅ Agent dikonfigurasi.');
    console.log(`   ID   : ${result.agentId}`);
    console.log(`   Hub  : ${result.hubUrl}`);
    console.log('\nSaat npm start, agent siap menerima perintah dari hub.');
    console.log('\n📌 Di HUB, daftarkan agent ini (manual via manage_agents.py):');
    const { execSync: exec } = require('child_process');
    let addCmd = `python scripts/manage_agents.py add ${result.agentId} <IP_LAPTOP_INI> 8765 ${result.env.AGENT_API_KEY}`;
    try {
      const ip = getLanIp();
      addCmd = `python scripts/manage_agents.py add ${result.agentId} ${ip} 8765 ${result.env.AGENT_API_KEY}`;
    } catch { /* ignore */ }
    console.log(`   ${addCmd}\n`);
  } else {
    result = await setupHub(absoluteTargetDir, existingEnv);
    fs.writeFileSync(envPath, buildEnvLines(result.env));

    const pairingPath = path.join(absoluteTargetDir, '.fleet-pairing-code');
    fs.writeFileSync(pairingPath, result.pairingCode + '\n', { mode: 0o600 });

    console.log('\n✅ Hub dikonfigurasi.');
    console.log(`   Agent lokal: ${result.agentId}`);

    let pythonCmd;
    try {
      pythonCmd = installPythonDeps(absoluteTargetDir);
      registerLocalAgent(pythonCmd, absoluteTargetDir);
    } catch {
      console.error('❌ Gagal install Python. Jalankan ulang npm run setup setelah memperbaiki Python.');
    }

    console.log('\n===========================================');
    console.log('📋 KODE PAIRING — untuk komputer tambahan');
    console.log('===========================================');
    console.log(`\n${result.pairingCode}\n`);
    console.log('Simpan kode ini. Di laptop lain:');
    console.log('  python scripts/manage_agents.py init-agent <kode>');
    console.log('  npm start');
    console.log('  (lalu jalankan perintah add yang ditampilkan, di hub)\n');
    console.log(`Kode juga disimpan di: ${pairingPath}`);
  }

  if (mode === 'agent') {
    try {
      installPythonDeps(absoluteTargetDir);
    } catch {
      console.error('❌ Gagal install Python. Perbaiki Python 3.11+ lalu jalankan npm run setup -- --agent lagi.');
    }
  }

  console.log('\n===========================================');
  console.log('🎉 Setup selesai!');
  console.log('===========================================');
  console.log(`\ncd ${targetFolder === '.' ? '.' : targetFolder}`);
  console.log('npm start\n');

  rl.close();
}

main().catch((err) => {
  console.error(`\n❌ Setup gagal: ${err.message}`);
  rl.close();
  process.exit(1);
});
