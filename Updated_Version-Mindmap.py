"""
journal_bot.py — Terminal-Based emotional journaling chatbot.

Usage:
    python journal_bot.py

Commands:
    /help                   Show help
    /log TEXT               Create a journal entry (or just type your entry)
    /today                  Show today's entries
    /last N                 Show last N entries (default 5)
    /search QUERY           Search entries by text or tag
    /tag ID TAG1 TAG2 ...   Add tags to entry ID
    /emotion ID             Show auto-detected emotions for entry ID
    /stats [DAYS]           Show emotion counts for last DAYS (default 7)
    /prompt                 Get a reflective prompt
    /summary [DAYS]         Short summary of entries in last DAYS (default 7)
    /save FILE              Save journal to FILE (json)
    /load FILE              Load journal from FILE (json)
    /export FILE            Export entries to plain text FILE
    /delete ID              Delete entry by ID
    /list                   List all entry IDs and dates
    /exit                   Quit
Notes:
 - Entries get auto-tagged with emotions based on keywords in descriptions.
 - All files are local. Keep them private.
"""

import json
import os
import re
import readline
from datetime import datetime, timedelta
from collections import Counter, defaultdict
from dataclasses import dataclass, asdict, field
from typing import List, Dict, Optional

# Data models

@dataclass
class Entry:
    id: int
    timestamp: str  # ISO format
    text: str
    tags: List[str] = field(default_factory=list)
    emotions: List[str] = field(default_factory=list)

class Journal:
    def __init__(self):
        self.entries: Dict[int, Entry] = {}
        self._next_id = 1

    def add(self, text: str, tags: Optional[List[str]] = None) -> Entry:
        eid = self._next_id
        self._next_id += 1
        ts = datetime.now().isoformat(timespec='seconds')
        entry = Entry(id=eid, timestamp=ts, text=text.strip(), tags=tags or [], emotions=[])
        self.entries[eid] = entry
        return entry

    def delete(self, eid: int) -> bool:
        if eid in self.entries:
            del self.entries[eid]
            return True
        return False

    def list_entries(self):
        return sorted(self.entries.values(), key=lambda e: e.id)

    def last_n(self, n=5):
        return sorted(self.entries.values(), key=lambda e: e.id)[-n:]

    def to_json(self):
        return json.dumps({
            "next_id": self._next_id,
            "entries": {str(k): asdict(v) for k, v in self.entries.items()}
        }, indent=2)

    @staticmethod
    def from_json(s: str) -> "Journal":
        data = json.loads(s)
        j = Journal()
        j._next_id = data.get("next_id", 1)
        for k, v in data.get("entries", {}).items():
            ent = Entry(id=int(v["id"]), timestamp=v["timestamp"], text=v["text"],
                        tags=v.get("tags", []), emotions=v.get("emotions", []))
            j.entries[int(k)] = ent
        return j

# List of emotions
EMOTION_KEYWORDS = {
    "happy": ["happy", "joy", "excited", "glad", "delighted", "cheerful", "good"],
    "sad": ["sad", "down", "depressed", "unhappy", "mourn", "tear"],
    "anxious": ["anxious", "anxiety", "nervous", "worried", "panic", "tense", "stressed"],
    "angry": ["angry", "mad", "furious", "irritat", "annoyed", "resent"],
    "relaxed": ["calm", "relaxed", "chill", "peaceful", "serene"],
    "lonely": ["lonely", "alone", "isolat", "ignored"],
    "grateful": ["grateful", "thankful", "blessed", "appreciat"],
    "confused": ["confused", "lost", "uncertain", "unsure"],
    "hopeful": ["hopeful", "optimis", "positive", "looking forward"]
}

def detect_emotions(text: str) -> List[str]:
    text_l = text.lower()
    scores = Counter()
    for emo, kws in EMOTION_KEYWORDS.items():
        for kw in kws:
            if kw in text_l:
                scores[emo] += text_l.count(kw)
    # returns emotions in an order by count desc, with threshold 1
    return [e for e, c in scores.most_common() if c > 0]
  
# Utilities
def parse_command(raw: str):
    raw = raw.strip()
    if not raw:
        return None, None
    if raw.startswith("/"):
        parts = raw.split()
        cmd = parts[0].lower()
        args = parts[1:]
        return cmd, args
    # fallback: treat as /log
    return "/log", [raw]

def pretty_entry(e: Entry) -> str:
    ts = e.timestamp
    txt = e.text
    tags = f" [{', '.join(e.tags)}]" if e.tags else ""
    emos = f" {{{', '.join(e.emotions)}}}" if e.emotions else ""
    return f"ID {e.id} @ {ts}{tags}{emos}\n  {txt}"

def find_entries_by_text(j: Journal, query: str):
    q = query.lower()
    res = []
    for e in j.entries.values():
        if q in e.text.lower() or any(q in t.lower() for t in e.tags) or any(q in emo.lower() for emo in e.emotions):
            res.append(e)
    return sorted(res, key=lambda x: x.id)

def entries_in_last_days(j: Journal, days: int):
    cutoff = datetime.now() - timedelta(days=days)
    res = []
    for e in j.entries.values():
        try:
            t = datetime.fromisoformat(e.timestamp)
        except Exception:
            continue
        if t >= cutoff:
            res.append(e)
    return sorted(res, key=lambda x: x.id)

# Reflection prompts

PROMPTS = [
    "What is one small thing that made you smile this week?",
    "What was a challenge you faced recently, and what helped you through it?",
    "If you could give your past self one piece of advice today, what would it be?",
    "What are three things you’re grateful for right now?",
    "What can you do tomorrow to make your day a bit easier?",
    "Name a person who supports you — why are they important?",
    "What emotion have you felt most this week? Describe one moment that shows it."
]

# Chatbot
class JournalBot:
    def __init__(self):
        self.journal = Journal()
        self.running = True
        self.greet()

    def greet(self):
        print("Welcome to JournalBot — your low-key terminal journaling companion.")
        print("Type /help for commands. You can also just type your entry and press Enter to log it.")
        print("Privacy reminder: this stores files locally. If you're in crisis, seek professional help.")

    def repl(self):
        while self.running:
            try:
                raw = input("\n> ").rstrip()
            except (EOFError, KeyboardInterrupt):
                print("\nbye.")
                break
            if not raw:
                continue
            cmd, args = parse_command(raw)
            if cmd is None:
                continue
            # dispatch
            try:
                self.handle(cmd, args)
            except Exception as e:
                print("[!] Error:", e)

    def handle(self, cmd: str, args: List[str]):
        if cmd == "/help":
            print(__doc__)
        elif cmd == "/log":
            text = " ".join(args).strip()
            if not text:
                print("Usage: /log TEXT")
                return
            entry = self.journal.add(text)
            # auto-detect emotions and add as tags too
            emos = detect_emotions(text)
            entry.emotions = emos
            for em in emos:
                if em not in entry.tags:
                    entry.tags.append(em)
            print(f"[+] Logged entry ID {entry.id}. Detected emotions: {', '.join(emos) if emos else 'none'}")
            print(pretty_entry(entry))
        elif cmd == "/today":
            today = entries_in_last_days(self.journal, 1)
            if not today:
                print("[no entries today]")
            for e in today:
                print(pretty_entry(e))
        elif cmd == "/last":
            n = 5
            if args:
                try:
                    n = int(args[0])
                except:
                    pass
            for e in self.journal.last_n(n):
                print(pretty_entry(e))
        elif cmd == "/search":
            if not args:
                print("Usage: /search QUERY")
                return
            q = " ".join(args)
            results = find_entries_by_text(self.journal, q)
            if not results:
                print("[no matches]")
            for e in results:
                print(pretty_entry(e))
        elif cmd == "/tag":
            if len(args) < 2:
                print("Usage: /tag ID TAG1 TAG2 ...")
                return
            try:
                eid = int(args[0])
            except:
                print("Invalid ID")
                return
            if eid not in self.journal.entries:
                print("No such entry ID")
                return
            tags = args[1:]
            for t in tags:
                if t not in self.journal.entries[eid].tags:
                    self.journal.entries[eid].tags.append(t)
            print(f"[+] Tags added to ID {eid}: {', '.join(tags)}")
        elif cmd == "/emotion":
            if not args:
                print("Usage: /emotion ID")
                return
            try:
                eid = int(args[0])
            except:
                print("Invalid ID")
                return
            e = self.journal.entries.get(eid)
            if not e:
                print("No such entry")
                return
            print(f"Emotions for ID {eid}: {', '.join(e.emotions) if e.emotions else 'none detected'}")
        elif cmd == "/stats":
            days = 7
            if args:
                try:
                    days = int(args[0])
                except:
                    pass
            entries = entries_in_last_days(self.journal, days)
            counter = Counter()
            for e in entries:
                for emo in e.emotions:
                    counter[emo] += 1
            if not counter:
                print(f"[no emotions detected in last {days} days]")
            else:
                print(f"Emotion counts last {days} days:")
                for emo, cnt in counter.most_common():
                    print(f" - {emo}: {cnt}")
        elif cmd == "/prompt":
            import random
            print(random.choice(PROMPTS))
        elif cmd == "/summary":
            days = 7
            if args:
                try:
                    days = int(args[0])
                except:
                    pass
            entries = entries_in_last_days(self.journal, days)
            if not entries:
                print(f"[no entries in last {days} days]")
                return
            # A summary: most common emotions, frequent words
            emo_cnt = Counter()
            word_cnt = Counter()
            stop = set(["the","and","a","to","i","it","is","in","of","for","my","was","that","on","with","have","had"])
            for e in entries:
                for emo in e.emotions:
                    emo_cnt[emo] += 1
                words = re.findall(r"\w+", e.text.lower())
                for w in words:
                    if w in stop or len(w) < 3:
                        continue
                    word_cnt[w] += 1
            print(f"Summary (last {days} days):")
            if emo_cnt:
                print(" - Emotions:", ", ".join([f"{e}({c})" for e, c in emo_cnt.most_common()]))
            top_words = [w for w, c in word_cnt.most_common(8)]
            if top_words:
                print(" - Common themes/words:", ", ".join(top_words))
            print(f" - Entries: {len(entries)}")
        elif cmd == "/save":
            if not args:
                print("Usage: /save FILE")
                return
            fname = args[0]
            with open(fname, "w", encoding="utf8") as f:
                f.write(self.journal.to_json())
            print(f"[+] Saved to {fname}")
        elif cmd == "/load":
            if not args:
                print("Usage: /load FILE")
                return
            fname = args[0]
            if not os.path.exists(fname):
                print("[!] File not found")
                return
            with open(fname, "r", encoding="utf8") as f:
                s = f.read()
            self.journal = Journal.from_json(s)
            print(f"[+] Loaded {fname}")
        elif cmd == "/export":
            if not args:
                print("Usage: /export FILE")
                return
            fname = args[0]
            with open(fname, "w", encoding="utf8") as f:
                for e in sorted(self.journal.entries.values(), key=lambda x: x.id):
                    f.write(f"ID {e.id} @ {e.timestamp}\n")
                    if e.tags:
                        f.write(f"Tags: {', '.join(e.tags)}\n")
                    if e.emotions:
                        f.write(f"Emotions: {', '.join(e.emotions)}\n")
                    f.write(e.text + "\n\n")
            print(f"[+] Exported to {fname}")
        elif cmd == "/delete":
            if not args:
                print("Usage: /delete ID")
                return
            try:
                eid = int(args[0])
            except:
                print("Invalid ID")
                return
            if self.journal.delete(eid):
                print(f"[+] Deleted entry {eid}")
            else:
                print("[!] No such entry")
        elif cmd == "/list":
            for e in sorted(self.journal.entries.values(), key=lambda x: x.id):
                print(f"ID {e.id} — {e.timestamp} — tags: {', '.join(e.tags) if e.tags else '-'} — emos: {', '.join(e.emotions) if e.emotions else '-'}")
        elif cmd == "/exit":
            print("Take care — your journal is stored locally. Bye.")
            self.running = False
        else:
            print("Unknown command. Type /help.")

#Entry Point
def main():
    bot = JournalBot()
    bot.repl()

if __name__ == "__main__":
    main()
