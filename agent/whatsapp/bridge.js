const {
    makeWASocket,
    useMultiFileAuthState,
    DisconnectReason,
    downloadContentFromMessage,
} = require('@whiskeysockets/baileys');
const fs = require('fs');
const path = require('path');
const readline = require('readline');
const os = require('os');

const AUTH_DIR = path.join(os.homedir(), '.config', 'rav-spy', 'baileys_auth');
const MEDIA_DIR = path.join(os.homedir(), '.config', 'rav-spy', 'wa_media');
const FORWARD_FILE = path.join(os.homedir(), '.config', 'rav-spy', 'wa_forward.json');

let sock = null;
let connected = false;
let qrPending = false;
let subscribedJids = new Set();
let presenceCache = {};
let starting = false;
let intentionalDisconnect = false;
let forwardChats = new Set();

function send(obj) {
    process.stdout.write(JSON.stringify(obj) + '\n');
}

function log(msg) {
    process.stderr.write('[bridge] ' + msg + '\n');
}

function loadForwardConfig() {
    try {
        if (fs.existsSync(FORWARD_FILE)) {
            const data = JSON.parse(fs.readFileSync(FORWARD_FILE, 'utf-8'));
            forwardChats = new Set(data.chats || []);
            log('Loaded forward config: ' + forwardChats.size + ' chats');
        }
    } catch (e) {
        log('Failed to load forward config: ' + e.message);
    }
}

function saveForwardConfig() {
    try {
        const dir = path.dirname(FORWARD_FILE);
        if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
        fs.writeFileSync(FORWARD_FILE, JSON.stringify({ chats: [...forwardChats] }));
    } catch (e) {
        log('Failed to save forward config: ' + e.message);
    }
}

function extractMessageContent(msg) {
    if (!msg) return null;
    const full = msg.message || msg;
    if (full.conversation) return { type: 'text', text: full.conversation };
    if (full.extendedTextMessage?.text) return { type: 'text', text: full.extendedTextMessage.text };
    if (full.imageMessage) return { type: 'image', caption: full.imageMessage.caption || '', mimetype: full.imageMessage.mimetype };
    if (full.videoMessage) return { type: 'video', caption: full.videoMessage.caption || '', mimetype: full.videoMessage.mimetype };
    if (full.documentMessage) return { type: 'document', filename: full.documentMessage.fileName || 'file', mimetype: full.documentMessage.mimetype };
    if (full.audioMessage) return { type: 'audio', mimetype: full.audioMessage.mimetype };
    if (full.stickerMessage) return { type: 'sticker' };
    if (full.contactMessage) return { type: 'contact', text: full.contactMessage.displayName };
    if (full.locationMessage) return { type: 'location', degrees: full.locationMessage.degrees, minutes: full.locationMessage.minutes };
    if (full.buttonsResponseMessage) return { type: 'button', text: full.buttonsResponseMessage.selectedButtonId };
    if (full.listResponseMessage) return { type: 'list', text: full.listResponseMessage.singleSelectReply?.selectedRowId };
    return { type: 'unknown' };
}

async function downloadMedia(msg) {
    try {
        const content = msg.message || msg;
        let streamType = null;
        let fileExt = '.bin';

        if (content.imageMessage) { streamType = 'image'; fileExt = '.jpg'; }
        else if (content.videoMessage) { streamType = 'video'; fileExt = '.mp4'; }
        else if (content.audioMessage) { streamType = 'audio'; fileExt = '.ogg'; }
        else if (content.documentMessage) { streamType = 'document'; fileExt = path.extname(content.documentMessage.fileName || 'file') || '.bin'; }
        else if (content.stickerMessage) { streamType = 'image'; fileExt = '.webp'; }
        else return null;

        const stream = await downloadContentFromMessage(content, streamType);
        const chunks = [];
        for await (const chunk of stream) {
            chunks.push(chunk);
        }

        if (!fs.existsSync(MEDIA_DIR)) fs.mkdirSync(MEDIA_DIR, { recursive: true });
        const filePath = path.join(MEDIA_DIR, Date.now() + '_' + Math.random().toString(36).slice(2, 8) + fileExt);
        fs.writeFileSync(filePath, Buffer.concat(chunks));
        return filePath;
    } catch (e) {
        log('Download media error: ' + e.message);
        return null;
    }
}

async function start() {
    if (starting) {
        log('Already starting, skipping...');
        return;
    }
    starting = true;
    loadForwardConfig();

    let state, saveCreds;
    try {
        const result = await useMultiFileAuthState(AUTH_DIR);
        state = result.state;
        saveCreds = result.saveCreds;
    } catch (e) {
        log('Failed to load auth state: ' + e.message);
        starting = false;
        setTimeout(() => start(), 3000);
        return;
    }

    sock = makeWASocket({
        auth: state,
        printQRInTerminal: false,
        emitOwnEvents: true,
        syncFullHistory: false,
        defaultQueryTimeoutMs: 30000,
        markOnlineOnConnect: false,
        browser: ['RAV-SPY', 'Chrome', '120.0'],
    });

    sock.ev.on('creds.update', saveCreds);

    sock.ev.on('messages.upsert', async (update) => {
        const { messages, type } = update;
        if (!messages || messages.length === 0) return;

        for (const msg of messages) {
            try {
                const key = msg.key;
                const jid = key.remoteJid;
                const fromMe = key.fromMe;
                const pushName = msg.pushName || '';
                const sender = fromMe ? 'me' : (key.participant || jid).split('@')[0];
                const phone = jid.split('@')[0];

                const content = extractMessageContent(msg);
                if (!content) continue;

                let mediaPath = null;
                if (content.type === 'image' || content.type === 'video' || content.type === 'audio' || content.type === 'document') {
                    mediaPath = await downloadMedia(msg);
                }

                const messageData = {
                    type: 'message',
                    jid: jid,
                    phone: phone,
                    sender: sender,
                    pushName: pushName,
                    fromMe: fromMe,
                    content: content,
                    mediaPath: mediaPath,
                    timestamp: msg.messageTimestamp ? new Date(msg.messageTimestamp * 1000).toISOString() : new Date().toISOString(),
                    id: key.id,
                };

                send(messageData);

                // Auto-forward for watched chats
                const watchJid = jid.split('@')[0];
                if (!fromMe && (forwardChats.has(jid) || forwardChats.has(watchJid))) {
                    send({
                        type: 'forward',
                        data: messageData,
                    });
                }
            } catch (e) {
                log('Message upsert error: ' + e.message);
            }
        }
    });

    sock.ev.on('messages.update', (updates) => {
        for (const update of updates) {
            if (update.key) {
                send({
                    type: 'message_update',
                    jid: update.key.remoteJid,
                    id: update.key.id,
                    status: update.update?.status,
                });
            }
        }
    });

    sock.ev.on('connection.update', async (update) => {
        const { connection, lastDisconnect, qr } = update;

        if (qr) {
            qrPending = true;
            send({ type: 'qr', data: qr });
            return;
        }

        if (connection === 'open') {
            connected = true;
            qrPending = false;
            starting = false;
            send({ type: 'ready' });
            log('Connected to WhatsApp');

            if (subscribedJids.size > 0) {
                log('Re-subscribing to ' + subscribedJids.size + ' JIDs...');
                for (const jid of subscribedJids) {
                    try {
                        sock.presenceSubscribe(jid);
                    } catch (e) {
                        log('Re-subscribe failed for ' + jid + ': ' + e.message);
                    }
                }
            }
        }

        if (connection === 'close') {
            const wasConnected = connected;
            connected = false;
            starting = false;

            if (intentionalDisconnect) {
                log('Intentional disconnect, not restarting');
                return;
            }

            const reason = lastDisconnect?.error?.output?.statusCode || DisconnectReason.loggedOut;
            log('Disconnected, reason: ' + reason);

            if (reason === DisconnectReason.loggedOut) {
                clearAuth();
                send({ type: 'logged_out' });
                setTimeout(() => {
                    log('Restarting fresh after logout...');
                    start();
                }, 2000);
                return;
            }

            send({ type: 'disconnected', reason: reason });

            const restartDelay = wasConnected ? 3000 : 1000;
            setTimeout(() => {
                if (!wasConnected && !qrPending) {
                    log('Auth appears invalid (never connected, no QR shown), clearing...');
                    clearAuth();
                }
                log('Reconnecting...');
                start();
            }, restartDelay);
        }
    });

    sock.ev.on('presence.update', (update) => {
        const { id, presences } = update;
        if (!presences) return;

        for (const [jid, presence] of Object.entries(presences)) {
            const lkp = presence.lastKnownPresence || 'unavailable';
            const lastSeen = presence.lastSeen ? new Date(presence.lastSeen * 1000).toISOString() : null;

            const isOnline = lkp === 'available' || lkp === 'composing' || lkp === 'recording';

            presenceCache[jid] = {
                lastKnownPresence: lkp,
                lastSeen: presence.lastSeen,
            };

            send({
                type: 'presence',
                jid: jid.split('@')[0],
                fullJid: jid,
                status: isOnline ? 'online' : 'offline',
                last_seen: lastSeen,
                timestamp: new Date().toISOString(),
            });
        }
    });

    sock.ev.on('groups.update', (updates) => {
        for (const g of updates) {
            send({ type: 'group_update', jid: g.id, subject: g.subject || null });
        }
    });
}

function clearAuth() {
    try {
        if (fs.existsSync(AUTH_DIR)) {
            fs.rmSync(AUTH_DIR, { recursive: true, force: true });
            log('Auth directory cleared');
        }
    } catch (e) {
        log('Failed to clear auth: ' + e.message);
    }
}

async function handleCommand(cmd) {
    if (!sock) {
        send({ type: 'error', message: 'Socket not initialized' });
        return;
    }

    switch (cmd.type) {
        case 'connect':
            if (connected) {
                send({ type: 'result', data: 'already_connected' });
            } else {
                send({ type: 'result', data: 'connecting' });
            }
            break;

        case 'qr_status':
            send({ type: 'result', data: { qrPending, connected } });
            break;

        case 'check': {
            if (!connected) {
                send({ type: 'error', message: 'Not connected to WhatsApp' });
                break;
            }
            const jid = cmd.jid.includes('@') ? cmd.jid : cmd.jid + '@s.whatsapp.net';
            try {
                await sock.presenceSubscribe(jid);
                subscribedJids.add(jid);

                await new Promise(r => setTimeout(r, 3000));

                const presenceData = presenceCache[jid];
                if (presenceData) {
                    const lkp = presenceData.lastKnownPresence || 'unavailable';
                    const isOnline = lkp === 'available' || lkp === 'composing' || lkp === 'recording';
                    const status = isOnline ? 'online' : 'offline';
                    const lastSeen = presenceData.lastSeen
                        ? new Date(presenceData.lastSeen * 1000).toISOString()
                        : null;
                    send({
                        type: 'result',
                        data: {
                            jid: cmd.jid,
                            status,
                            last_seen: lastSeen,
                            timestamp: new Date().toISOString(),
                        },
                    });
                } else {
                    send({
                        type: 'result',
                        data: {
                            jid: cmd.jid,
                            status: 'offline',
                            last_seen: null,
                            timestamp: new Date().toISOString(),
                        },
                    });
                }
            } catch (e) {
                send({ type: 'error', message: 'Check failed: ' + e.message });
            }
            break;
        }

        case 'subscribe': {
            if (!connected) {
                send({ type: 'error', message: 'Not connected' });
                break;
            }
            const jid = cmd.jid.includes('@') ? cmd.jid : cmd.jid + '@s.whatsapp.net';
            try {
                await sock.presenceSubscribe(jid);
                subscribedJids.add(jid);
                send({ type: 'result', data: { jid: cmd.jid, subscribed: true } });
            } catch (e) {
                send({ type: 'error', message: 'Subscribe failed: ' + e.message });
            }
            break;
        }

        case 'get_messages': {
            if (!connected) {
                send({ type: 'error', message: 'Not connected' });
                break;
            }
            const jid = cmd.jid.includes('@') ? cmd.jid : cmd.jid + '@s.whatsapp.net';
            const limit = cmd.limit || 20;
            try {
                const msgs = await sock.loadMessages(jid, limit);
                const results = [];
                for (const msg of msgs || []) {
                    const content = extractMessageContent(msg);
                    results.push({
                        id: msg.key?.id,
                        fromMe: msg.key?.fromMe || false,
                        sender: msg.key?.participant?.split('@')[0] || msg.key?.remoteJid?.split('@')[0],
                        pushName: msg.pushName || '',
                        content: content,
                        timestamp: msg.messageTimestamp ? new Date(msg.messageTimestamp * 1000).toISOString() : null,
                    });
                }
                send({ type: 'result', data: { jid: cmd.jid, messages: results } });
            } catch (e) {
                log('loadMessages error: ' + e.message);
                // Fallback: sock.store might have messages
                try {
                    const msgs = sock.store?.messages?.get(jid)?.slice(-limit) || [];
                    const results = msgs.map(msg => ({
                        id: msg.key?.id,
                        fromMe: msg.key?.fromMe || false,
                        sender: msg.key?.participant?.split('@')[0] || msg.key?.remoteJid?.split('@')[0],
                        pushName: msg.pushName || '',
                        content: extractMessageContent(msg),
                        timestamp: msg.messageTimestamp ? new Date(msg.messageTimestamp * 1000).toISOString() : null,
                    }));
                    send({ type: 'result', data: { jid: cmd.jid, messages: results } });
                } catch (e2) {
                    send({ type: 'error', message: 'get_messages failed: ' + e.message });
                }
            }
            break;
        }

        case 'get_groups': {
            if (!connected) {
                send({ type: 'error', message: 'Not connected' });
                break;
            }
            try {
                const groups = await sock.groupFetchAllParticipating();
                const results = Object.entries(groups || {}).map(([jid, g]) => ({
                    jid: jid,
                    subject: g.subject || '?',
                    size: g.participants?.length || 0,
                    owner: g.owner?.split('@')[0] || '?',
                    desc: g.desc?.toString()?.slice(0, 200) || '',
                }));
                send({ type: 'result', data: { groups: results } });
            } catch (e) {
                send({ type: 'error', message: 'get_groups failed: ' + e.message });
            }
            break;
        }

        case 'send_message': {
            if (!connected) {
                send({ type: 'error', message: 'Not connected' });
                break;
            }
            const target = cmd.jid.includes('@') ? cmd.jid : cmd.jid + '@s.whatsapp.net';
            try {
                await sock.sendMessage(target, { text: cmd.text });
                send({ type: 'result', data: { sent: true, jid: cmd.jid } });
            } catch (e) {
                send({ type: 'error', message: 'send_message failed: ' + e.message });
            }
            break;
        }

        case 'forward_status': {
            const chatJid = cmd.jid.includes('@') ? cmd.jid : (cmd.jid ? cmd.jid + '@s.whatsapp.net' : null);
            if (cmd.action === 'on' && chatJid) {
                forwardChats.add(chatJid);
                saveForwardConfig();
                send({ type: 'result', data: { forwarding: true, jid: cmd.jid } });
            } else if (cmd.action === 'off' && chatJid) {
                forwardChats.delete(chatJid);
                saveForwardConfig();
                send({ type: 'result', data: { forwarding: false, jid: cmd.jid } });
            } else if (cmd.action === 'status') {
                send({ type: 'result', data: { chats: [...forwardChats], count: forwardChats.size } });
            } else {
                send({ type: 'error', message: 'Usage: forward_status on/off/status [jid]' });
            }
            break;
        }

        case 'disconnect':
            try {
                intentionalDisconnect = true;
                sock.end();
                connected = false;
                send({ type: 'result', data: 'disconnected' });
            } catch (e) {
                send({ type: 'error', message: e.message });
            }
            break;

        case 'reset':
            clearAuth();
            send({ type: 'result', data: 'auth_cleared' });
            log('Auth cleared, exiting for restart...');
            setTimeout(() => process.exit(0), 200);
            break;

        default:
            send({ type: 'error', message: 'Unknown command: ' + cmd.type });
    }
}

const rl = readline.createInterface({ input: process.stdin });
rl.on('line', (line) => {
    try {
        const cmd = JSON.parse(line);
        handleCommand(cmd);
    } catch (e) {
        send({ type: 'error', message: 'Invalid JSON: ' + e.message });
    }
});

start();
send({ type: 'ready', status: 'initializing' });

process.on('SIGINT', () => {
    intentionalDisconnect = true;
    if (sock) sock.end();
    process.exit(0);
});
process.on('SIGTERM', () => {
    intentionalDisconnect = true;
    if (sock) sock.end();
    process.exit(0);
});

process.on('uncaughtException', (err) => {
    log('Uncaught exception: ' + (err?.message || err));
    send({ type: 'error', message: 'Bridge crashed: ' + (err?.message || err) });
    setTimeout(() => process.exit(1), 200);
});

process.on('unhandledRejection', (err) => {
    log('Unhandled rejection: ' + (err?.message || err));
});
