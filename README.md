# DNS TXT Ollama Server

A DNS server that responds to TXT queries with AI-generated content from a local Ollama instance. Ask questions via DNS queries and get AI responses back as TXT records!

This especially should work in
- DB ICE
- planes
- any public Wi-Fi network

without having to log in and without having to pay for their premium services.

## Features

- UDP DNS server responding to TXT queries
- Streams responses from local Ollama models
- Rate limiting per IP address
- Configurable timeouts and response limits
- Splits long responses into multiple TXT records (≤255 bytes each)
- Caps responses at 500 characters with truncation

## Prerequisites

- Python 3.12+
- [Ollama](https://ollama.ai/) running locally
- An Ollama model pulled (default: `llama3.2`)

## Installation

### Using uv (recommended)

```bash
# Clone or download the project
cd dns-txt-ollama-server

# Install dependencies with uv
uv sync

# Run the server
uv run python dns_llm_server.py
```

### Using pip

```bash
# Clone or download the project
cd dns-txt-ollama-server

# Create a virtual environment
python3.12 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -e .

# Run the server
python dns_llm_server.py
```

## Setup

1. **Install and start Ollama:**
   ```bash
   # Install Ollama (see https://ollama.ai/)
   ollama pull llama3.2  # or your preferred model
   ollama serve
   ```

2. **Configure the server** (optional):
   Edit the configuration variables at the top of `dns_llm_server.py`

3. **Run the DNS server:**
   ```bash
   # For development (non-privileged port)
   sudo python dns_llm_server.py
   
   # Or modify PORT = 5353 in the script for non-root usage
   ```

## Usage

Once running, you can query the DNS server using standard DNS tools:

### Using dig

```bash
# Ask a simple question
dig @localhost -p 5353 TXT "what is python?" +short

# Ask about programming
dig @localhost TXT "explain recursion" +short

# Get a joke
dig @localhost TXT "tell me a joke" +short
```

### Using nslookup

```bash
nslookup -type=TXT "what is ai?" localhost
```

### Example Response

```bash
$ dig @localhost TXT "explain dns"

;; ANSWER SECTION:
explain dns. 60 IN TXT "DNS (Domain Name System) translates human-readable domain names into IP addresses. It's like a phone book for the internet, allowing browsers to find websites using names instead of numerical addresses."
```

## Configuration

The server can be configured by modifying variables at the top of `dns_llm_server.py`:

### Server Settings

```python
PORT = 53                    # DNS port (53 requires root, use 5353 for dev)
TTL = 60                     # DNS record TTL in seconds
MAX_CHARS = 500              # Maximum response length
DEADLINE_SECONDS = 4         # Timeout for LLM responses
DOMAIN = ".example.test"     # Domain suffix to strip from queries
```

### LLM Settings

```python
LLM_MODEL = "llama3.2"       # Ollama model name
LLM_PROTOCOL = "http"        # Protocol for Ollama API
LLM_SERVER_IP = "127.0.0.1"  # Ollama server IP
LLM_SERVER_PORT = 11434      # Ollama server port
```

### Rate Limiting

```python
TOKENS_PER_MIN = 60          # Requests per minute per IP
```

## How It Works

1. **DNS Query Processing**: The server receives TXT queries and extracts the question from the domain name
2. **Domain Processing**: Strips the configured domain suffix and unescapes DNS encoding
3. **LLM Streaming**: Sends the question to Ollama and streams the response in real-time
4. **Response Formatting**: Caps responses at 500 characters and splits into ≤255 byte TXT records
5. **Rate Limiting**: Uses token bucket algorithm to limit requests per IP address

## Query Format

Questions are encoded in the domain name before your configured domain:

```
question-text.your-domain.com
```

Special characters are automatically DNS-escaped. The server will:
- Remove the domain suffix
- Unescape DNS encoding (like `\032` for spaces)
- Add instructions for concise, unformatted responses

## Troubleshooting

### Common Issues

- **Permission denied on port 53**: Run with `sudo` or change `PORT = 5353`
- **Ollama connection failed**: Ensure Ollama is running on the configured host/port
- **Model not found**: Pull the model with `ollama pull <model-name>`
- **Timeouts**: Increase `DEADLINE_SECONDS` for slower models/hardware

### Testing Ollama Connection

```bash
curl http://localhost:11434/api/chat \
  -d '{"model":"llama3.2","messages":[{"role":"user","content":"test"}],"stream":false}'
```

## Security Notes

- This server has basic rate limiting but minimal security features
- Intended for local/development use
- Consider firewall rules if exposing externally
- DNS queries are typically unencrypted

## License

MIT © 2025 Manuel Schmid — see [LICENSE](LICENSE).

