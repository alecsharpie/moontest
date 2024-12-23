# Run Tests
```bash
uv run pytest tests/test_scenarios.py -v
```

# Todo
Download Model
Initialize with local model path. Can also read .mf.gz files, but we recommend decompressing
up-front to avoid decompression overhead every time the model is initialized.