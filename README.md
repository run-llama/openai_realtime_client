# OpenAI Realtime API Client for Python

This is an experimental OpenAI Realtime API client for Python and LlamaIndex. It integrates with LlamaIndex's tools, allowing you to quickly build custom voice assistants.

Include two examples that run directly in the terminal -- using both manual and Server VAD mode (i.e. allowing you to interrupt the chatbot).

## Installation

Install system deps:

```bash
brew install ffmpeg
```

Install python deps:

```bash
git clone https://github.com/run-llama/openai_realtime_client.git
cd openai_realtime_client
pip install -e .
```

Set your openai key:

```bash
export OPENAI_API_KEY="sk-..."
```

## Usage

Run the interactive CLI with manual VAD (try asking for your phone number to see function calling in action):

```bash
python ./examples/manual_cli.py
```

Or to use streaming mode (which allows you to interrupt the chatbot):

```bash
python ./examples/streaming_cli.py
```

**NOTE:** Streaming mode can be a little janky, best to use headphones in a quiet environment.
