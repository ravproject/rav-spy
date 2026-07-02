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

                // Forward status/story updates
                if (jid === 'status@broadcast' && !fromMe) {
                    send({
                        type: 'story_update',
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

        case 'reply': {
            if (!connected) { send({ type: 'error', message: 'Not connected' }); break; }
            const replyTarget = cmd.jid.includes('@') ? cmd.jid : cmd.jid + '@s.whatsapp.net';
            const replyMsgId = cmd.message_id;
            const replyText = cmd.text;
            if (!replyMsgId || !replyText) {
                send({ type: 'error', message: 'Usage: reply requires message_id and text' }); break;
            }
            try {
                await sock.sendMessage(replyTarget, {
                    text: replyText,
                    contextInfo: { stanzaId: replyMsgId, participant: replyTarget, quotedMessage: { conversation: cmd.quoted_text || '' } }
                });
                send({ type: 'result', data: { sent: true, jid: cmd.jid } });
            } catch (e) { send({ type: 'error', message: 'reply failed: ' + e.message }); }
            break;
        }

        case 'react': {
            if (!connected) { send({ type: 'error', message: 'Not connected' }); break; }
            const reactTarget = cmd.jid.includes('@') ? cmd.jid : cmd.jid + '@s.whatsapp.net';
            const reactMsgId = cmd.message_id;
            const emoji = cmd.emoji || '👍';
            if (!reactMsgId) {
                send({ type: 'error', message: 'Usage: react requires message_id' }); break;
            }
            try {
                await sock.sendMessage(reactTarget, {
                    react: { key: { remoteJid: reactTarget, fromMe: false, id: reactMsgId }, text: emoji }
                });
                send({ type: 'result', data: { reacted: true, jid: cmd.jid, emoji } });
            } catch (e) { send({ type: 'error', message: 'react failed: ' + e.message }); }
            break;
        }

        case 'send_media': {
            if (!connected) { send({ type: 'error', message: 'Not connected' }); break; }
            const mediaTarget = cmd.jid.includes('@') ? cmd.jid : cmd.jid + '@s.whatsapp.net';
            const mediaPath = cmd.file;
            const caption = cmd.caption || '';
            if (!mediaPath || !fs.existsSync(mediaPath)) {
                send({ type: 'error', message: 'File not found: ' + mediaPath }); break;
            }
            try {
                const mediaBuffer = fs.readFileSync(mediaPath);
                const mtype = cmd.media_type || 'image';
                const msgContent = {};
                if (mtype === 'image') {
                    msgContent.image = mediaBuffer;
                    msgContent.mimetype = cmd.mimetype || 'image/jpeg';
                } else if (mtype === 'video') {
                    msgContent.video = mediaBuffer;
                    msgContent.mimetype = cmd.mimetype || 'video/mp4';
                } else if (mtype === 'audio') {
                    msgContent.audio = mediaBuffer;
                    msgContent.mimetype = cmd.mimetype || 'audio/ogg; codecs=opus';
                } else if (mtype === 'document') {
                    msgContent.document = mediaBuffer;
                    msgContent.fileName = cmd.filename || 'file';
                    msgContent.mimetype = cmd.mimetype || 'application/octet-stream';
                } else if (mtype === 'sticker') {
                    msgContent.sticker = mediaBuffer;
                }
                if (caption) msgContent.caption = caption;
                await sock.sendMessage(mediaTarget, msgContent);
                send({ type: 'result', data: { sent: true, jid: cmd.jid, media_type: mtype } });
            } catch (e) { send({ type: 'error', message: 'send_media failed: ' + e.message }); }
            break;
        }

        case 'read': {
            if (!connected) { send({ type: 'error', message: 'Not connected' }); break; }
            const readTarget = cmd.jid.includes('@') ? cmd.jid : cmd.jid + '@s.whatsapp.net';
            try {
                const msgId = cmd.message_id;
                if (msgId) {
                    await sock.readMessages([{ remoteJid: readTarget, id: msgId }]);
                } else {
                    // Mark all as read: grab last messages and mark them
                    const recent = await sock.loadMessages(readTarget, 5);
                    const keys = (recent || []).filter(m => !m.key?.fromMe).map(m => m.key);
                    if (keys.length > 0) await sock.readMessages(keys);
                }
                send({ type: 'result', data: { read: true, jid: cmd.jid } });
            } catch (e) { send({ type: 'error', message: 'read failed: ' + e.message }); }
            break;
        }

        case 'typing': {
            if (!connected) { send({ type: 'error', message: 'Not connected' }); break; }
            const typingTarget = cmd.jid.includes('@') ? cmd.jid : cmd.jid + '@s.whatsapp.net';
            try {
                if (cmd.action === 'on') {
                    await sock.sendPresenceUpdate('composing', typingTarget);
                } else if (cmd.action === 'recording') {
                    await sock.sendPresenceUpdate('recording', typingTarget);
                } else {
                    await sock.sendPresenceUpdate('paused', typingTarget);
                }
                send({ type: 'result', data: { typing: cmd.action, jid: cmd.jid } });
            } catch (e) { send({ type: 'error', message: 'typing failed: ' + e.message }); }
            break;
        }

        case 'delete': {
            if (!connected) { send({ type: 'error', message: 'Not connected' }); break; }
            const deleteTarget = cmd.jid.includes('@') ? cmd.jid : cmd.jid + '@s.whatsapp.net';
            const deleteMsgId = cmd.message_id;
            if (!deleteMsgId) {
                send({ type: 'error', message: 'Usage: delete requires message_id' }); break;
            }
            try {
                const deleteKey = { remoteJid: deleteTarget, fromMe: cmd.from_me !== false, id: deleteMsgId };
                if (cmd.delete_for === 'everyone') {
                    await sock.sendMessage(deleteTarget, { delete: deleteKey });
                } else {
                    await sock.sendMessage(deleteTarget, { delete: deleteKey });
                }
                send({ type: 'result', data: { deleted: true, jid: cmd.jid } });
            } catch (e) { send({ type: 'error', message: 'delete failed: ' + e.message }); }
            break;
        }

        case 'group_add': {
            if (!connected) { send({ type: 'error', message: 'Not connected' }); break; }
            const gaGroup = cmd.jid.includes('@') ? cmd.jid : cmd.jid + '@g.us';
            const gaParticipants = cmd.participants || [];
            if (gaParticipants.length === 0) {
                send({ type: 'error', message: 'Usage: group_add requires participants array' }); break;
            }
            try {
                const res = await sock.groupParticipantsUpdate(gaGroup, gaParticipants, 'add');
                send({ type: 'result', data: { added: true, jid: cmd.jid, result: res } });
            } catch (e) { send({ type: 'error', message: 'group_add failed: ' + e.message }); }
            break;
        }

        case 'group_remove': {
            if (!connected) { send({ type: 'error', message: 'Not connected' }); break; }
            const grGroup = cmd.jid.includes('@') ? cmd.jid : cmd.jid + '@g.us';
            const grParticipants = cmd.participants || [];
            if (grParticipants.length === 0) {
                send({ type: 'error', message: 'Usage: group_remove requires participants array' }); break;
            }
            try {
                const res = await sock.groupParticipantsUpdate(grGroup, grParticipants, 'remove');
                send({ type: 'result', data: { removed: true, jid: cmd.jid, result: res } });
            } catch (e) { send({ type: 'error', message: 'group_remove failed: ' + e.message }); }
            break;
        }

        case 'group_promote': {
            if (!connected) { send({ type: 'error', message: 'Not connected' }); break; }
            const gpGroup = cmd.jid.includes('@') ? cmd.jid : cmd.jid + '@g.us';
            const gpParticipants = cmd.participants || [];
            if (gpParticipants.length === 0) {
                send({ type: 'error', message: 'Usage: group_promote requires participants array' }); break;
            }
            try {
                const res = await sock.groupParticipantsUpdate(gpGroup, gpParticipants, 'promote');
                send({ type: 'result', data: { promoted: true, jid: cmd.jid, result: res } });
            } catch (e) { send({ type: 'error', message: 'group_promote failed: ' + e.message }); }
            break;
        }

        case 'group_demote': {
            if (!connected) { send({ type: 'error', message: 'Not connected' }); break; }
            const gdGroup = cmd.jid.includes('@') ? cmd.jid : cmd.jid + '@g.us';
            const gdParticipants = cmd.participants || [];
            if (gdParticipants.length === 0) {
                send({ type: 'error', message: 'Usage: group_demote requires participants array' }); break;
            }
            try {
                const res = await sock.groupParticipantsUpdate(gdGroup, gdParticipants, 'demote');
                send({ type: 'result', data: { demoted: true, jid: cmd.jid, result: res } });
            } catch (e) { send({ type: 'error', message: 'group_demote failed: ' + e.message }); }
            break;
        }

        case 'group_subject': {
            if (!connected) { send({ type: 'error', message: 'Not connected' }); break; }
            const gsGroup = cmd.jid.includes('@') ? cmd.jid : cmd.jid + '@g.us';
            const newSubject = cmd.subject;
            if (!newSubject) {
                send({ type: 'error', message: 'Usage: group_subject requires subject' }); break;
            }
            try {
                await sock.groupUpdateSubject(gsGroup, newSubject);
                send({ type: 'result', data: { subject_changed: true, jid: cmd.jid, subject: newSubject } });
            } catch (e) { send({ type: 'error', message: 'group_subject failed: ' + e.message }); }
            break;
        }

        case 'group_desc': {
            if (!connected) { send({ type: 'error', message: 'Not connected' }); break; }
            const gdGroup = cmd.jid.includes('@') ? cmd.jid : cmd.jid + '@g.us';
            const newDesc = cmd.description || '';
            try {
                await sock.groupUpdateDescription(gdGroup, newDesc);
                send({ type: 'result', data: { desc_changed: true, jid: cmd.jid } });
            } catch (e) { send({ type: 'error', message: 'group_desc failed: ' + e.message }); }
            break;
        }

        case 'group_invite': {
            if (!connected) { send({ type: 'error', message: 'Not connected' }); break; }
            const giGroup = cmd.jid.includes('@') ? cmd.jid : cmd.jid + '@g.us';
            try {
                const code = await sock.groupInviteCode(giGroup);
                send({ type: 'result', data: { jid: cmd.jid, invite_code: code, link: 'https://chat.whatsapp.com/' + code } });
            } catch (e) { send({ type: 'error', message: 'group_invite failed: ' + e.message }); }
            break;
        }

        case 'group_leave': {
            if (!connected) { send({ type: 'error', message: 'Not connected' }); break; }
            const glGroup = cmd.jid.includes('@') ? cmd.jid : cmd.jid + '@g.us';
            try {
                await sock.groupLeave(glGroup);
                send({ type: 'result', data: { left: true, jid: cmd.jid } });
            } catch (e) { send({ type: 'error', message: 'group_leave failed: ' + e.message }); }
            break;
        }

        case 'group_members': {
            if (!connected) { send({ type: 'error', message: 'Not connected' }); break; }
            const gmGroup = cmd.jid.includes('@') ? cmd.jid : cmd.jid + '@g.us';
            try {
                const meta = await sock.groupMetadata(gmGroup);
                const participants = (meta.participants || []).map(p => ({
                    jid: p.id.split('@')[0],
                    admin: p.admin || null,
                    name: p.name || ''
                }));
                send({ type: 'result', data: { jid: cmd.jid, subject: meta.subject, participants, count: participants.length } });
            } catch (e) { send({ type: 'error', message: 'group_members failed: ' + e.message }); }
            break;
        }

        case 'contacts': {
            if (!connected) { send({ type: 'error', message: 'Not connected' }); break; }
            try {
                const contacts = sock.store?.contacts;
                const results = [];
                if (contacts) {
                    for (const [jid, contact] of contacts) {
                        if (!jid.endsWith('@s.whatsapp.net')) continue;
                        results.push({
                            jid: jid.split('@')[0],
                            name: contact.name || contact.notify || contact.pushname || '',
                            verifiedName: contact.verifiedName || ''
                        });
                    }
                }
                results.sort((a, b) => (a.name || a.jid).localeCompare(b.name || b.jid));
                send({ type: 'result', data: { contacts: results, count: results.length } });
            } catch (e) { send({ type: 'error', message: 'contacts failed: ' + e.message }); }
            break;
        }

        case 'block': {
            if (!connected) { send({ type: 'error', message: 'Not connected' }); break; }
            const blockJid = cmd.jid.includes('@') ? cmd.jid : cmd.jid + '@s.whatsapp.net';
            try {
                await sock.updateBlockStatus(blockJid, 'block');
                send({ type: 'result', data: { blocked: true, jid: cmd.jid } });
            } catch (e) { send({ type: 'error', message: 'block failed: ' + e.message }); }
            break;
        }

        case 'unblock': {
            if (!connected) { send({ type: 'error', message: 'Not connected' }); break; }
            const unblockJid = cmd.jid.includes('@') ? cmd.jid : cmd.jid + '@s.whatsapp.net';
            try {
                await sock.updateBlockStatus(unblockJid, 'unblock');
                send({ type: 'result', data: { unblocked: true, jid: cmd.jid } });
            } catch (e) { send({ type: 'error', message: 'unblock failed: ' + e.message }); }
            break;
        }

        case 'profile': {
            if (!connected) { send({ type: 'error', message: 'Not connected' }); break; }
            const profileJid = cmd.jid.includes('@') ? cmd.jid : cmd.jid + '@s.whatsapp.net';
            try {
                const [pic, status] = await Promise.allSettled([
                    sock.profilePictureUrl(profileJid),
                    sock.fetchStatus(profileJid).catch(() => null)
                ]);
                send({
                    type: 'result',
                    data: {
                        jid: cmd.jid,
                        picture: pic.status === 'fulfilled' ? pic.value : null,
                        status: status.status === 'fulfilled' ? (status.value?.status || '') : '',
                        setAt: status.status === 'fulfilled' ? (status.value?.setAt ? new Date(status.value.setAt * 1000).toISOString() : '') : ''
                    }
                });
            } catch (e) { send({ type: 'error', message: 'profile failed: ' + e.message }); }
            break;
        }

        case 'search_messages': {
            if (!connected) { send({ type: 'error', message: 'Not connected' }); break; }
            const searchKeyword = cmd.keyword;
            if (!searchKeyword) { send({ type: 'error', message: 'Usage: search_messages requires keyword' }); break; }
            try {
                const chats = sock.store?.chats || {};
                const results = [];
                for (const [jid] of chats) {
                    const msgs = sock.store?.messages?.get(jid) || [];
                    for (const msg of msgs) {
                        const text = msg.message?.conversation || msg.message?.extendedTextMessage?.text || '';
                        if (text.toLowerCase().includes(searchKeyword.toLowerCase())) {
                            results.push({
                                jid: jid.split('@')[0],
                                id: msg.key?.id,
                                fromMe: msg.key?.fromMe || false,
                                text: text.slice(0, 200),
                                timestamp: msg.messageTimestamp ? new Date(msg.messageTimestamp * 1000).toISOString() : null,
                            });
                            if (results.length >= (cmd.limit || 50)) break;
                        }
                    }
                    if (results.length >= (cmd.limit || 50)) break;
                }
                send({ type: 'result', data: { keyword: searchKeyword, results, count: results.length } });
            } catch (e) { send({ type: 'error', message: 'search_messages failed: ' + e.message }); }
            break;
        }

        case 'poll_create': {
            if (!connected) { send({ type: 'error', message: 'Not connected' }); break; }
            const pollTarget = cmd.jid.includes('@') ? cmd.jid : cmd.jid + '@s.whatsapp.net';
            const pollQuestion = cmd.question;
            const pollOptions = cmd.options || [];
            if (!pollQuestion || pollOptions.length < 2) {
                send({ type: 'error', message: 'Usage: poll_create requires question and at least 2 options' }); break;
            }
            try {
                await sock.sendMessage(pollTarget, {
                    poll: { name: pollQuestion, values: pollOptions, selectableCount: cmd.selectable_count || 1 }
                });
                send({ type: 'result', data: { sent: true, jid: cmd.jid, question: pollQuestion } });
            } catch (e) { send({ type: 'error', message: 'poll_create failed: ' + e.message }); }
            break;
        }

        case 'broadcast': {
            if (!connected) { send({ type: 'error', message: 'Not connected' }); break; }
            const targets = cmd.jids || [];
            if (targets.length === 0) { send({ type: 'error', message: 'Usage: broadcast requires jids array' }); break; }
            let sent = 0, failed = 0;
            for (const raw of targets) {
                const t = raw.includes('@') ? raw : raw + '@s.whatsapp.net';
                try {
                    await sock.sendMessage(t, { text: cmd.text || '' });
                    sent++;
                } catch (e) { failed++; log('Broadcast failed to ' + t + ': ' + e.message); }
            }
            send({ type: 'result', data: { sent, failed, total: targets.length } });
            break;
        }

        case 'toggle_disappearing': {
            if (!connected) { send({ type: 'error', message: 'Not connected' }); break; }
            const discTarget = cmd.jid.includes('@') ? cmd.jid : cmd.jid + '@s.whatsapp.net';
            const expiration = cmd.expiration || 0; // 0=off, 86400=24h, 604800=7d, 7776000=90d
            try {
                await sock.sendMessage(discTarget, { disappearingMessagesInChat: expiration });
                send({ type: 'result', data: { jid: cmd.jid, expiration } });
            } catch (e) { send({ type: 'error', message: 'toggle_disappearing failed: ' + e.message }); }
            break;
        }

        case 'export_chat': {
            if (!connected) { send({ type: 'error', message: 'Not connected' }); break; }
            const exportJid = cmd.jid.includes('@') ? cmd.jid : cmd.jid + '@s.whatsapp.net';
            const exportLimit = cmd.limit || 200;
            try {
                const msgs = await sock.loadMessages(exportJid, exportLimit);
                const results = (msgs || []).map(msg => ({
                    id: msg.key?.id,
                    fromMe: msg.key?.fromMe || false,
                    sender: msg.key?.participant?.split('@')[0] || msg.key?.remoteJid?.split('@')[0],
                    pushName: msg.pushName || '',
                    content: extractMessageContent(msg),
                    timestamp: msg.messageTimestamp ? new Date(msg.messageTimestamp * 1000).toISOString() : null,
                }));
                send({ type: 'result', data: { jid: cmd.jid, messages: results, count: results.length } });
            } catch (e) { send({ type: 'error', message: 'export_chat failed: ' + e.message }); }
            break;
        }

        case 'group_settings': {
            if (!connected) { send({ type: 'error', message: 'Not connected' }); break; }
            const gsJid = cmd.jid.includes('@') ? cmd.jid : cmd.jid + '@g.us';
            const setting = cmd.setting; // 'announcement'|'not_announcement'|'locked'|'not_locked'
            if (!setting) { send({ type: 'error', message: 'Usage: group_settings requires setting (announcement/not_announcement/locked/not_locked)' }); break; }
            try {
                await sock.groupSettingUpdate(gsJid, setting);
                send({ type: 'result', data: { jid: cmd.jid, setting_changed: setting } });
            } catch (e) { send({ type: 'error', message: 'group_settings failed: ' + e.message }); }
            break;
        }

        case 'mute': {
            if (!connected) { send({ type: 'error', message: 'Not connected' }); break; }
            const muteJid = cmd.jid.includes('@') ? cmd.jid : cmd.jid + '@s.whatsapp.net';
            const duration = cmd.duration !== undefined ? cmd.duration : 8 * 60 * 60; // default 8 hours
            try {
                await sock.chatModify({ jid: muteJid, mute: duration });
                send({ type: 'result', data: { muted: true, jid: cmd.jid, duration } });
            } catch (e) { send({ type: 'error', message: 'mute failed: ' + e.message }); }
            break;
        }

        case 'unmute': {
            if (!connected) { send({ type: 'error', message: 'Not connected' }); break; }
            const unmuteJid = cmd.jid.includes('@') ? cmd.jid : cmd.jid + '@s.whatsapp.net';
            try {
                await sock.chatModify({ jid: unmuteJid, mute: null });
                send({ type: 'result', data: { unmuted: true, jid: cmd.jid } });
            } catch (e) { send({ type: 'error', message: 'unmute failed: ' + e.message }); }
            break;
        }

        case 'pin': {
            if (!connected) { send({ type: 'error', message: 'Not connected' }); break; }
            const pinJid = cmd.jid.includes('@') ? cmd.jid : cmd.jid + '@s.whatsapp.net';
            try {
                await sock.chatModify({ jid: pinJid, pin: Math.floor(Date.now() / 1000) });
                send({ type: 'result', data: { pinned: true, jid: cmd.jid } });
            } catch (e) { send({ type: 'error', message: 'pin failed: ' + e.message }); }
            break;
        }

        case 'unpin': {
            if (!connected) { send({ type: 'error', message: 'Not connected' }); break; }
            const unpinJid = cmd.jid.includes('@') ? cmd.jid : cmd.jid + '@s.whatsapp.net';
            try {
                await sock.chatModify({ jid: unpinJid, pin: null });
                send({ type: 'result', data: { unpinned: true, jid: cmd.jid } });
            } catch (e) { send({ type: 'error', message: 'unpin failed: ' + e.message }); }
            break;
        }

        case 'star': {
            if (!connected) { send({ type: 'error', message: 'Not connected' }); break; }
            const starJid = cmd.jid.includes('@') ? cmd.jid : cmd.jid + '@s.whatsapp.net';
            const starMsgId = cmd.message_id;
            if (!starMsgId) { send({ type: 'error', message: 'Usage: star requires message_id' }); break; }
            const starFromMe = cmd.from_me !== false;
            try {
                await sock.chatModify({
                    jid: starJid,
                    star: { messages: [{ id: starMsgId, fromMe: starFromMe }], star: true }
                });
                send({ type: 'result', data: { starred: true, jid: cmd.jid, message_id: starMsgId } });
            } catch (e) { send({ type: 'error', message: 'star failed: ' + e.message }); }
            break;
        }

        case 'unstar': {
            if (!connected) { send({ type: 'error', message: 'Not connected' }); break; }
            const unstarJid = cmd.jid.includes('@') ? cmd.jid : cmd.jid + '@s.whatsapp.net';
            const unstarMsgId = cmd.message_id;
            if (!unstarMsgId) { send({ type: 'error', message: 'Usage: unstar requires message_id' }); break; }
            try {
                await sock.chatModify({
                    jid: unstarJid,
                    star: { messages: [{ id: unstarMsgId, fromMe: true }], star: false }
                });
                send({ type: 'result', data: { unstarred: true, jid: cmd.jid, message_id: unstarMsgId } });
            } catch (e) { send({ type: 'error', message: 'unstar failed: ' + e.message }); }
            break;
        }

        case 'group_revoke': {
            if (!connected) { send({ type: 'error', message: 'Not connected' }); break; }
            const revokeJid = cmd.jid.includes('@') ? cmd.jid : cmd.jid + '@g.us';
            try {
                const code = await sock.groupRevokeInviteCode(revokeJid);
                send({ type: 'result', data: { jid: cmd.jid, invite_code: code, link: 'https://chat.whatsapp.com/' + code } });
            } catch (e) { send({ type: 'error', message: 'group_revoke failed: ' + e.message }); }
            break;
        }

        case 'blocklist': {
            if (!connected) { send({ type: 'error', message: 'Not connected' }); break; }
            try {
                const list = await sock.fetchBlocklist();
                const contacts = (list || []).map(j => ({ jid: j.split('@')[0], fullJid: j }));
                send({ type: 'result', data: { contacts, count: contacts.length } });
            } catch (e) { send({ type: 'error', message: 'blocklist failed: ' + e.message }); }
            break;
        }

        case 'edit': {
            if (!connected) { send({ type: 'error', message: 'Not connected' }); break; }
            const editJid = cmd.jid.includes('@') ? cmd.jid : cmd.jid + '@s.whatsapp.net';
            const editMsgId = cmd.message_id;
            const editText = cmd.text;
            if (!editMsgId || !editText) {
                send({ type: 'error', message: 'Usage: edit requires message_id and text' }); break;
            }
            try {
                await sock.sendMessage(editJid, {
                    text: editText,
                    edit: { remoteJid: editJid, fromMe: cmd.from_me !== false, id: editMsgId }
                });
                send({ type: 'result', data: { edited: true, jid: cmd.jid, message_id: editMsgId } });
            } catch (e) { send({ type: 'error', message: 'edit failed: ' + e.message }); }
            break;
        }

        case 'archive': {
            if (!connected) { send({ type: 'error', message: 'Not connected' }); break; }
            const archiveJid = cmd.jid.includes('@') ? cmd.jid : cmd.jid + '@s.whatsapp.net';
            try {
                await sock.chatModify({ jid: archiveJid, archive: true });
                send({ type: 'result', data: { archived: true, jid: cmd.jid } });
            } catch (e) { send({ type: 'error', message: 'archive failed: ' + e.message }); }
            break;
        }

        case 'unarchive': {
            if (!connected) { send({ type: 'error', message: 'Not connected' }); break; }
            const unarchiveJid = cmd.jid.includes('@') ? cmd.jid : cmd.jid + '@s.whatsapp.net';
            try {
                await sock.chatModify({ jid: unarchiveJid, archive: false });
                send({ type: 'result', data: { unarchived: true, jid: cmd.jid } });
            } catch (e) { send({ type: 'error', message: 'unarchive failed: ' + e.message }); }
            break;
        }

        case 'react_remove': {
            if (!connected) { send({ type: 'error', message: 'Not connected' }); break; }
            const reactRmJid = cmd.jid.includes('@') ? cmd.jid : cmd.jid + '@s.whatsapp.net';
            const reactRmMsgId = cmd.message_id;
            if (!reactRmMsgId) { send({ type: 'error', message: 'Usage: react_remove requires message_id' }); break; }
            try {
                await sock.sendMessage(reactRmJid, {
                    react: { key: { remoteJid: reactRmJid, fromMe: false, id: reactRmMsgId }, text: '' }
                });
                send({ type: 'result', data: { reaction_removed: true, jid: cmd.jid } });
            } catch (e) { send({ type: 'error', message: 'react_remove failed: ' + e.message }); }
            break;
        }

        case 'list_message': {
            if (!connected) { send({ type: 'error', message: 'Not connected' }); break; }
            const listJid = cmd.jid.includes('@') ? cmd.jid : cmd.jid + '@s.whatsapp.net';
            try {
                await sock.sendMessage(listJid, {
                    text: cmd.text || 'Pilih opsi:',
                    footer: cmd.footer || '',
                    title: cmd.title || '',
                    buttonText: cmd.button_text || 'Lihat',
                    sections: cmd.sections || []
                });
                send({ type: 'result', data: { list_sent: true, jid: cmd.jid } });
            } catch (e) { send({ type: 'error', message: 'list_message failed: ' + e.message }); }
            break;
        }

        case 'location': {
            if (!connected) { send({ type: 'error', message: 'Not connected' }); break; }
            const locJid = cmd.jid.includes('@') ? cmd.jid : cmd.jid + '@s.whatsapp.net';
            const lat = cmd.latitude;
            const lng = cmd.longitude;
            if (lat === undefined || lng === undefined) {
                send({ type: 'error', message: 'Usage: location requires latitude and longitude' }); break;
            }
            try {
                await sock.sendMessage(locJid, {
                    location: { degreesLatitude: lat, degreesLongitude: lng }
                });
                send({ type: 'result', data: { location_sent: true, jid: cmd.jid, lat, lng } });
            } catch (e) { send({ type: 'error', message: 'location failed: ' + e.message }); }
            break;
        }

        case 'story_list': {
            if (!connected) { send({ type: 'error', message: 'Not connected' }); break; }
            try {
                const statusMsgs = sock.store?.messages?.get('status@broadcast') || [];
                const results = statusMsgs.slice(-(cmd.limit || 30)).map(msg => {
                    const content = extractMessageContent(msg);
                    const sender = msg.key?.participant?.split('@')[0] || msg.key?.remoteJid?.split('@')[0] || '?';
                    return {
                        id: msg.key?.id,
                        sender: sender,
                        pushName: msg.pushName || '',
                        content: content,
                        timestamp: msg.messageTimestamp ? new Date(msg.messageTimestamp * 1000).toISOString() : null,
                    };
                });
                // Also try loading fresh statuses
                try {
                    const fresh = await sock.loadMessages('status@broadcast', cmd.limit || 30);
                    if (fresh && fresh.length > 0) {
                        const freshResults = fresh.map(msg => {
                            const content = extractMessageContent(msg);
                            const sender = msg.key?.participant?.split('@')[0] || msg.key?.remoteJid?.split('@')[0] || '?';
                            return {
                                id: msg.key?.id,
                                sender: sender,
                                pushName: msg.pushName || '',
                                content: content,
                                timestamp: msg.messageTimestamp ? new Date(msg.messageTimestamp * 1000).toISOString() : null,
                            };
                        });
                        send({ type: 'result', data: { stories: freshResults, count: freshResults.length } });
                        break;
                    }
                } catch (_) { /* fallback to store */ }
                send({ type: 'result', data: { stories: results, count: results.length } });
            } catch (e) { send({ type: 'error', message: 'story_list failed: ' + e.message }); }
            break;
        }

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
