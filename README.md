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

Useful commands:

```bash
python -m app inspect "episode.mkv"
python -m app extract "episode.mkv"
python -m app validate "output/episode.vi.ass"
python -m app mux "episode.mkv" "output/episode.vi.ass"
```
