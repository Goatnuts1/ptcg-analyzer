"""src.learn — the self-play learning data pipeline (Phase 1 of the learning engine).

See docs/LEARNING_ENGINE_PLAN.md. Phase 1 = a reproducible dataset + loader:
  encoder.py   frozen state-feature spec (acting-player POV)
  actions.py   fixed Action <-> id space (bounded policy head)
  selfplay.py  RecordingAgent + game generation -> (state, policy, value) records
  buffer.py    sharded, compressed, atomic rolling buffer + archive flush (USB-tolerant)
  dataset.py   reader/loader over shards
  config.py    paths (T7 archive / internal hot buffer), worker count, versions
  generate.py  CLI: fill the buffer from self-play

The deterministic engine stays the rules oracle; nothing here plays moves it didn't
certify legal. Every record carries its seed, so games are reproducible.
"""
