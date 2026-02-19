import requests, time, threading, json, websocket, os, random, re, queue

# ==========================================
#          CONFIGURATION (MASTER)
# ==========================================
TOKEN = "TOKEN"
SERVER_ID = "732233585872076912"  
PROBOT_ID = "1218590092067733596"
REPORT_USER_ID = "1011869862416633857"
TARGET_NAME = "ncxdev" 

# --- Strategy & 1B Goal ---
MIN_BET, MAX_BET = 100, 2000
PROFIT_CAP = 1000000 
RECOVERY_AMT = 1000

TASKS = {
    "Bbless": {"interval": 300, "next": 0},
    "Bwork": {"interval": 3600, "next": 0},
    "Bdaily": {"interval": 86400, "next": 0},
    "DM_Audit": {"interval": 3600, "next": 0},
    "Slots_Session": {"interval": 900, "next": 0} 
}

STATS = {
    "wallet": 0, "bank": 0, "total_profit": 0, "rolls": 0,
    "current_bet": 100, "status": "Active 🟢", "room": "N/A", "logs": []
}

msg_queue = queue.Queue()
CURRENT_VC_ID = None
ws_global = None
BOT_STOPPED = False
READY_FOR_REPORT = False

# --- Visual Colors ---
G, R, Y, C, W, RE = "\033[1;32m", "\033[1;31m", "\033[1;33m", "\033[1;36m", "\033[1;37m", "\033[0m"

# ==========================================
#          CORE UTILITIES & UI
# ==========================================

def clean_int(val):
    try:
        clean = re.sub(r'[^\d]', '', str(val))
        return int(clean) if clean else 0
    except: return 0

def add_log(msg, color=W):
    STATS["logs"].append(f"{color}[{time.strftime('%H:%M:%S')}] {msg}{RE}")
    if len(STATS["logs"]) > 10: STATS["logs"].pop(0)

def draw_panel():
    while True:
        os.system('cls' if os.name == 'nt' else 'clear')
        progress = (STATS['total_profit'] / PROFIT_CAP) * 100
        print(f"{C}┌────────────────────────────────────────────────────────────┐{RE}")
        print(f"{C}│{G}         BABOO v177.0 - SOVEREIGN MASTER ENGINE            {C}│{RE}")
        print(f"{C}├────────────────────────────────────────────────────────────┤{RE}")
        print(f"{C}│ {W}WALLET: {Y}{STATS['wallet']:<15,}{W} BANK: {Y}{clean_int(STATS['bank']):<20,}{C}│{RE}")
        print(f"{C}│ {W}PROFIT: {G if STATS['total_profit'] >=0 else R}{STATS['total_profit']:<14,}{W} GOAL: {G}{progress:>6.4f}% to 1B{C}  │{RE}")
        print(f"{C}├────────────────────────────────────────────────────────────┤{RE}")
        print(f"{C}│ {W}TASK HUD:                                                  {C}│{RE}")
        for name, info in TASKS.items():
            rem = max(0, int(info['next'] - time.time()))
            print(f"{C}│ {W}> {name:<14} : {Y}{rem:>5}s {W}Wait  {W}Room: {C}{STATS['room']:<18}{C}│{RE}")
        print(f"{C}├────────────────────────────────────────────────────────────┤{RE}")
        print(f"{C}│ {W}OMNI-LOG FEED:                                             {C}│{RE}")
        for l in STATS["logs"]: print(f"{C}│ {l:<68} {C}│{RE}")
        print(f"{C}└────────────────────────────────────────────────────────────┘{RE}")
        time.sleep(1)

# ==========================================
#       SYNCED AUDIT REPORTING
# ==========================================

def send_synced_report():
    global READY_FOR_REPORT
    try:
        headers = {"Authorization": TOKEN, "Content-Type": "application/json"}
        ch_res = requests.post("https://discord.com/api/v9/users/@me/channels", headers=headers, json={"recipient_id": REPORT_USER_ID})
        if ch_res.status_code == 200:
            ch_id = ch_res.json()['id']
            prog = (STATS['total_profit'] / PROFIT_CAP) * 100
            report = (
                f"🛡️ **SOVEREIGN AUDIT REPORT v177.0** 🛡️\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"💰 **Wallet:** `{STATS['wallet']:,}` | **Bank:** `{STATS['bank']:,}`\n"
                f"🎲 **Rolls:** `{STATS['rolls']:,}` | **Profit:** `{STATS['total_profit']:,}`\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"📊 **Progress Target:** `{prog:.4f}%` to 1B Goal\n"
                f"📅 **Audit Sync Time:** `{time.strftime('%H:%M:%S')}`"
            )
            requests.post(f"https://discord.com/api/v9/channels/{ch_id}/messages", headers=headers, json={"content": report})
            add_log("REPORT: Synced audit dispatched.", G)
    except: add_log("REPORT: Sync failed.", R)
    finally: READY_FOR_REPORT = False

# ==========================================
#       CORE LOGIC & SEQUENCING
# ==========================================

def track_result(message_data):
    global STATS, BOT_STOPPED, READY_FOR_REPORT
    if BOT_STOPPED: return
    flat = (message_data.get('content', '') + str(message_data.get('embeds', []))).lower()
    if TARGET_NAME not in flat: return

    wal_match = re.search(r'wallet:?\D*`?([\d,]+)`?', flat)
    if wal_match:
        new_val = clean_int(wal_match.group(1))
        
        # Recovery Trigger
        if new_val == 0:
            add_log("RECOVERY: Wallet empty! Pulling 1k...", Y)
            msg_queue.put(f"bwith {RECOVERY_AMT}")
        
        if STATS["wallet"] != 0:
            change = new_val - STATS["wallet"]
            if change != 0: 
                STATS["total_profit"] += change
                add_log(f"SYNC: Profit updated ({'+' if change > 0 else ''}{change:,})", C)
            
            # Goal Check
            if STATS["total_profit"] >= PROFIT_CAP:
                BOT_STOPPED = True; STATS["status"] = "1B REACHED 🏁"; return
            
            # Smart Scaling Logic
            if STATS["total_profit"] < 0: STATS["current_bet"] = MIN_BET
            elif 0 <= STATS["total_profit"] <= 2000: STATS["current_bet"] = 250
            else: 
                STATS["current_bet"] = min(MAX_BET, int(STATS["current_bet"] * 1.5))
                add_log(f"STRAT: Profit up! Bet scaling to {STATS['current_bet']}", G)
        
        STATS["wallet"] = new_val
        if STATS["wallet"] >= 10000: 
            add_log("BANKING: Wallet high, depositing 5k.", Y)
            msg_queue.put("bdep 5000")

    bnk_match = re.search(r'bank:?\D*`?([\d,]+)`?', flat)
    if bnk_match: STATS["bank"] = clean_int(bnk_match.group(1))
    
    if READY_FOR_REPORT: send_synced_report()

def jump_room():
    global CURRENT_VC_ID
    if BOT_STOPPED: return
    try:
        res = requests.get(f"https://discord.com/api/v9/guilds/{SERVER_ID}/channels", headers={"Authorization": TOKEN})
        vcs = [c for c in res.json() if c['type'] == 2]
        if vcs:
            target = random.choice(vcs)
            CURRENT_VC_ID = target['id']
            STATS["room"] = target['name']
            if ws_global:
                ws_global.send(json.dumps({"op": 4, "d": {"guild_id": SERVER_ID, "channel_id": CURRENT_VC_ID, "self_mute": False, "self_deaf": False}}))
                add_log(f"VC: Hopped to {target['name']}", C)
    except: pass

def message_sequencer():
    while True:
        cmd = msg_queue.get()
        if CURRENT_VC_ID:
            headers = {"Authorization": TOKEN, "Content-Type": "application/json"}
            res = requests.post(f"https://discord.com/api/v9/channels/{CURRENT_VC_ID}/messages", headers=headers, json={"content": cmd}, timeout=5)
            if res.status_code == 200:
                mid = res.json()['id']
                add_log(f"SENT: {cmd}")
                time.sleep(1) # Ghost delete
                requests.delete(f"https://discord.com/api/v9/channels/{CURRENT_VC_ID}/messages/{mid}", headers=headers)
                add_log(f"GHOST: {cmd} deleted.", W)
            time.sleep(random.randint(10, 20))
        msg_queue.task_done()

def task_scheduler(name, interval):
    TASKS[name]["next"] = time.time() + random.randint(5, 15)
    while True:
        if time.time() >= TASKS[name]["next"]:
            if name == "DM_Audit":
                global READY_FOR_REPORT
                READY_FOR_REPORT = True
                add_log("AUDIT: Triggering sync for report.", C)
                msg_queue.put("bbal")
            elif name == "Slots_Session":
                num = random.randint(1, 20)
                add_log(f"SESSION: Starting burst of {num} rolls.", Y)
                for _ in range(num):
                    msg_queue.put(f"Bslots {STATS['current_bet']}")
                    STATS["rolls"] += 1
                msg_queue.put("bbal")
                jump_room()
                TASKS[name]["next"] = time.time() + random.randint(60, 1800)
                continue
            else:
                msg_queue.put(name)
            TASKS[name]["next"] = time.time() + interval + random.randint(20, 60)
        time.sleep(1)

def start_bot():
    ws_url = "wss://gateway.discord.gg/?v=9&encoding=json"
    def on_open(ws):
        global ws_global; ws_global = ws
        ws.send(json.dumps({"op": 2, "d": {"token": TOKEN, "properties": {"$os": "linux", "$browser": "chrome"}}}))
    def on_message(ws, msg):
        d = json.loads(msg)
        if d['op'] == 10:
            threading.Thread(target=lambda: [ (time.sleep(d['d']['heartbeat_interval']/1000), ws.send(json.dumps({"op": 1, "d": None}))) for _ in iter(int, 1) if ws.sock ], daemon=True).start()
        elif d.get('t') == 'READY':
            jump_room()
            threading.Thread(target=message_sequencer, daemon=True).start()
            for n in TASKS: threading.Thread(target=task_scheduler, args=(n, TASKS[n]["interval"]), daemon=True).start()
        elif d.get('t') == 'MESSAGE_CREATE':
            if d['d'].get('author', {}).get('id') == PROBOT_ID: track_result(d['d'])

    websocket.WebSocketApp(ws_url, on_open=on_open, on_message=on_message).run_forever()

if __name__ == "__main__":
    threading.Thread(target=draw_panel, daemon=True).start()
    start_bot()
