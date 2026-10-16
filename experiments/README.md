# Experiments

Scripts that are NOT part of the app. `agent.py` and `compare.py` are old and not
maintained. `agent.py` opens `jarvis.db` in whatever folder you run it from, so do not
run it from the project root.

- `agent.py`       terminal version of the assistant (first version, before the dashboard)
- `compare.py`     compares models on a few tool-calling questions (it became the
                   model evaluation suite)
- `crypto_lab.py`  small encryption experiments for learning, before encrypted backups
                   (`python experiments/crypto_lab.py 1`). Never touches `jarvis.db`.
