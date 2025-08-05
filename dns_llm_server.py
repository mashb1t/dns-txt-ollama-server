#!/usr/bin/env python3
"""
DNS-TXT server in Python.

Features
----------
* UDP DNS server (port configurable).
* Rate-limiter stub (token bucket per IP).
* Streams an external LLM in a worker thread with configurable timeout.
* Caps answers at 500 chars and splits into ≤255-byte TXT strings.
"""

import json
import queue
import re
import socketserver
import threading
import time
from typing import List

import requests
from dnslib import DNSHeader, DNSRecord, QTYPE, RR, TXT

_oct_re = re.compile(r"\\(\d{3})")

# CONFIG
PORT = 53  # 53 requires root, pick 5353 for development
TTL = 60
MAX_CHARS = 500
DEADLINE_SECONDS = 4
DOMAIN = ".mashb1t.de"

# LLM CONFIG
LLM_MODEL = "llama3.2"  # Ollama model to use, ensure it's pulled locally
LLM_PROTOCOL = "http"
LLM_SERVER_IP = "127.0.0.1"
LLM_SERVER_PORT = 11434
LLM_DEADLINE_SECONDS = DEADLINE_SECONDS
CHUNK = 50

# RATE LIMITING (simple token bucket per IP)
TOKENS_PER_MIN = 60
_BUCKETS = {}  # ip -> (tokens, last_ts)


def rate_limit_allow(ip: str) -> bool:
    now = time.time()
    tokens, ts = _BUCKETS.get(ip, (TOKENS_PER_MIN, now))
    # Refill
    tokens = min(TOKENS_PER_MIN, tokens + (now - ts) * (TOKENS_PER_MIN / 60))
    if tokens < 1:
        _BUCKETS[ip] = (tokens, now)
        return False
    _BUCKETS[ip] = (tokens - 1, now)
    return True


def llm_stream(
        prompt: str,
        out_queue: queue.Queue,
        *,
        model: str = LLM_MODEL,
        protocol: str = LLM_PROTOCOL,
        host: str = LLM_SERVER_IP,
        port: int = LLM_SERVER_PORT,
        timeout_seconds: int = DEADLINE_SECONDS,
) -> None:
    """
    Stream tokens from a local Ollama model into out_q.
    Ends by putting `None` (sentinel) when the stream finishes or on error.
    """
    url = f"{protocol}://{host}:{port}/api/chat"
    payload = {
        "model": model,
        "stream": True,
        "messages": [{"role": "user", "content": prompt}],
    }

    try:
        with requests.post(url, json=payload, stream=True, timeout=timeout_seconds) as resp:
            resp.raise_for_status()
            for line in resp.iter_lines():
                if not line:
                    continue
                data = json.loads(line)
                if chunk := data.get("message", {}).get("content"):
                    out_queue.put(chunk)
                if data.get("done"):
                    break

    except Exception as err:
        out_queue.put(f"[llm error] {err}")

    finally:
        out_queue.put(None)


def dns_unescape(label: str) -> str:
    """
    Unescape DNS labels by converting \\DDD octal escapes to characters.
    """
    return _oct_re.sub(lambda m: chr(int(m.group(1))), label)


def dns_safe_prompt(raw_name: str) -> str:
    """
    Convert a DNS name to a safe prompt for the LLM.
    """
    name = raw_name.rstrip(".").removesuffix(DOMAIN)
    prompt = dns_unescape(name)
    return f"Answer in {MAX_CHARS} characters or less, no markdown formatting: {prompt}"


def split_txt(txt: str) -> List[str]:
    """
    Split into ≤255-byte chunks for TXT RDATA.
    """
    return [txt[i:i + 255] for i in range(0, len(txt), 255)] or [""]


class DNSHandler(socketserver.BaseRequestHandler):
    def handle(self) -> None:
        data, sock = self.request
        src_ip = self.client_address[0]

        if not rate_limit_allow(src_ip):
            return

        try:
            req = DNSRecord.parse(data)
        except Exception:
            return

        if not req.questions:
            return

        reply = DNSRecord(DNSHeader(id=req.header.id, qr=1, aa=1, ra=0))
        reply.add_question(req.questions[0])

        for q in req.questions:
            if QTYPE[q.qtype] != "TXT":
                continue

            prompt = dns_safe_prompt(str(q.qname))

            # Streaming thread & queue
            q_out: queue.Queue[str | None] = queue.Queue()
            th = threading.Thread(target=llm_stream, args=(prompt, q_out), daemon=True)
            th.start()

            response_chunks = []
            deadline = time.time() + DEADLINE_SECONDS
            done = False

            while time.time() < deadline and len("".join(response_chunks)) < MAX_CHARS:
                try:
                    item = q_out.get(timeout=deadline - time.time())
                except queue.Empty:
                    break
                if item is None:  # stream finished
                    done = True
                    break
                response_chunks.append(item)

            final = "".join(response_chunks)[:MAX_CHARS]
            if len(final) == MAX_CHARS and not done:
                final = final[:-3] + "..."

            if not final:
                final = "Request timed out"

            txt_rr = RR(
                rname=q.qname,
                rtype=QTYPE.TXT,
                rclass=1,
                ttl=TTL,
                rdata=TXT(split_txt(final)),
            )
            reply.add_answer(txt_rr)

        sock.sendto(reply.pack(), self.client_address)


def start_dns_server(port: int = PORT) -> None:
    with socketserver.ThreadingUDPServer(("0.0.0.0", port), DNSHandler) as srv:
        srv.daemon_threads = True
        print(f"DNS-TXT LLM server listening on UDP {port}")
        try:
            srv.serve_forever(poll_interval=0.5)
        except KeyboardInterrupt:
            print("\nShutting down DNS server...")
        finally:
            srv.shutdown()


if __name__ == "__main__":
    start_dns_server()
