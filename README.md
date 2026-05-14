# anime-sub-ai
AI-powered tools and workflows for creating and managing anime subtitles.

## Getting Started
Install Python dependencies:

```bash
pip install -r requirements.txt
```

Install system tools:

- `mkvtoolnix` for `mkvmerge` and `mkvextract`
- `ffmpeg` for `ffprobe` and fallback extraction

Set your OpenAI key:

```bash
export OPENAI_API_KEY=...
```

Run the MVP pipeline:

```bash
python -m app translate "episode.mkv"
```

Use OpenAI:

```bash
python -m app translate "episode.mkv" --provider openai --model gpt-5
```

Use a local Ollama model:

```bash
ollama pull qwen2.5:14b
python -m app translate "episode.mkv" --provider ollama --model qwen2.5:14b
```

Use LM Studio:

1. Start LM Studio's local server.
2. Load a chat/instruct model.
3. Run:

```bash
python -m app translate "episode.mkv" --provider lmstudio --model local-model
```

The default LM Studio endpoint is `http://localhost:1234/v1`. Override it with:

```bash
set LMSTUDIO_BASE_URL=http://localhost:1234/v1
set LMSTUDIO_MODEL=local-model
```

Useful commands:

```bash
python -m app inspect "episode.mkv"
python -m app extract "episode.mkv"
python -m app validate "output/episode.vi.ass"
python -m app mux "episode.mkv" "output/episode.vi.ass"
```
